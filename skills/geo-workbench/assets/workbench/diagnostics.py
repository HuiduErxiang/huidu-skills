"""Local, structured diagnostic events. Never collect browser credentials or page dumps."""
import hashlib
import json
import platform
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VERSION = '0.3.1'
STAGES = {
    'service_start': '启动工作台', 'task_created': '创建任务',
    'executor_start': '聊天接手', 'browser_connect': '连接浏览器',
    'page_open': '打开平台页面', 'login_check': '检查登录或验证',
    'keyword_input': '输入关键词', 'suggestion_read': '读取搜索联想',
    'question_confirm': '确认用户填写的 AI 主设问', 'ai_submit': '提交 AI 问题',
    'ai_read': '读取 AI 回答', 'result_save': '保存采集结果',
    'report_generate': '生成报告', 'user_resume': '请求继续',
    'user_pause': '请求暂停', 'client_request': '工作台请求',
}
# title, next action for the colleague, investigation for the helper.
CODES = {
    'GEO_LOGIN_REQUIRED': ('页面要求登录', '在执行端当前使用的浏览器和标签页完成登录，再回聊天说“继续研究”。', '核对登录页面与采集页面是否属于同一浏览器会话；读取页面重新核验。'),
    'GEO_VERIFICATION_REQUIRED': ('页面要求安全验证', '在当前平台页面手动完成验证，再回聊天说“继续研究”。', '确认真实页面是否仍显示验证；不得绕过平台验证。'),
    'GEO_BROWSER_UNAVAILABLE': ('浏览器控制暂不可用', '保留当前页面，回聊天要求重新连接浏览器并重新读取页面。无需因这个错误重复登录。', '核对原始工具错误、浏览器是否存在、目标标签页是否有效；浏览器读取失败可尝试桌面 Computer Use。'),
    'GEO_PERMISSION_DENIED': ('浏览器或桌面操作权限被拒绝', '根据工具的原生提示处理权限；若没有提示，把排障信息发给负责人。', '核对具体被拒操作及工具权限；网页中的继续按钮不能代替原生授权。'),
    'GEO_PAGE_TIMEOUT': ('页面加载或读取超时', '确认平台页面能正常显示，稍后回聊天重试当前步骤。', '检查页面加载、网络和工具响应；不能仅凭超时判断账号掉线。'),
    'GEO_UI_CHANGED': ('未定位到预期页面元素', '保留当前页面，把排障信息交给负责人检查页面适配。', '查看最新页面结构或截图，确认搜索框和联想区域；不要复用旧元素索引。'),
    'GEO_NO_SUGGESTIONS': ('本次未观察到下拉联想', '确认已在搜索框输入关键词且出现候选区域；仍无结果时保留此记录。', '区分无联想、读取失败和平台不提供联想；搜索结果标题不能当作联想。'),
    'GEO_RATE_LIMITED': ('页面明确提示访问受限', '按平台提示等待后再继续，避免连续重试。', '记录页面可见限制提示和时间；仅在有明确证据时使用这个错误码。'),
    'GEO_SERVICE_UNREACHABLE': ('本地工作台无法连接', '回聊天说“检查并恢复 GEO 工作台”；服务恢复后继续原任务。', '检查本地服务进程、端口 8790 和启动错误；用离线诊断命令导出已有日志。'),
    'GEO_SERVICE_START_FAILED': ('本地工作台启动失败', '把启动错误交给负责人；已有任务数据请保留。', '根据原始启动错误检查端口占用、数据库读写或依赖；不要据此要求平台重新登录。'),
    'GEO_WRITE_FAILED': ('采集结果保存失败', '保留已取得的结果，回聊天要求先恢复保存，再继续采集。', '检查原始保存错误、磁盘和数据库；恢复前先核对现有记录，避免重复提交外部问题。'),
    'GEO_REPORT_FAILED': ('报告生成失败', '保留当前任务，回聊天要求重新生成报告。', '检查报告渲染或写入错误；采集数据应继续保留。'),
    'GEO_EXECUTOR_STALE': ('近期没有收到执行进度', '回原聊天说“继续研究，并检查浏览器控制状态”。', '这是进度更新超时，不能证明浏览器断开；核对最后一步日志和工具真实报错。'),
    'GEO_API_INVALID': ('工作台请求参数不正确', '复制排障信息交给负责人。', '核对请求接口、错误详情和执行端提交的字段。'),
    'GEO_UNKNOWN': ('当前步骤未完成，原因未确认', '复制排障信息交给负责人，并在原聊天要求输出具体工具错误。', '现有证据不足；先查原始错误和最后成功步骤，不推断为登录、权限或网络问题。'),
}
SENSITIVE = re.compile(r'cookie|authorization|password|passwd|token|secret|api[_-]?key|csrf', re.I)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def safe_url(value):
    try:
        p = urlsplit(str(value))
        if p.scheme not in ('http', 'https') or not p.hostname:
            return '[URL omitted]'
        # Origin is sufficient to identify the platform, without account/session IDs.
        host = p.hostname
        if ':' in host:
            host = '[' + host + ']'
        if p.port:
            host += ':' + str(p.port)
        return urlunsplit((p.scheme, host, '', '', ''))
    except ValueError:
        return '[URL omitted]'


def clean(value, limit=4000):
    text = str(value or '')[:12000]
    text = re.sub(r'https?://[^\s<>"\x27]+', lambda m: safe_url(m[0]), text)
    text = re.sub(r'(?im)^.*(?:cookie|authorization|set-cookie)["\x27]?\s*[:=].*$', '[credential omitted]', text)
    text = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [redacted]', text)
    text = re.sub(r'(?i)([\w-]*(?:token|password|passwd|secret|api[_-]?key|csrf)[\w-]*\s*["\x27]?\s*[:=]\s*)["\x27]?[^\s,;"\x27}]+', r'\1[redacted]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{8,}', '[key omitted]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email omitted]', text)
    text = re.sub(r'(?:/Users/|/home/)[^/\s]+', '~', text)
    text = re.sub(r'[A-Za-z]:\\Users\\[^\\\s]+', '~', text)
    return text[:limit]


def normalize(data):
    """Keep a bounded allowlist, preserving observations without inventing a root cause."""
    if not isinstance(data, dict):
        raise ValueError('diagnostic 必须是对象')
    code = data.get('code', 'GEO_UNKNOWN')
    stage = data.get('stage', 'client_request')
    if code not in CODES or stage not in STAGES:
        raise ValueError('未知诊断错误码或阶段')
    certainty = data.get('certainty', 'unknown')
    if certainty not in ('confirmed', 'suspected', 'unknown'):
        raise ValueError('certainty 必须为 confirmed/suspected/unknown')
    observation = clean(data.get('observation', '执行端没有提供具体失败证据。'))
    if certainty == 'confirmed' and not data.get('observation'):
        raise ValueError('确认原因必须提供实际观察证据')
    result = dict(code=code, stage=stage, stage_label=STAGES[stage],
                  certainty=certainty, observation=observation)
    for key in ('error_type', 'error_message', 'tool', 'browser', 'method', 'evidence'):
        if key in data:
            if not isinstance(data[key], str):
                raise ValueError(key + ' 必须是文本')
            result[key] = clean(data[key], 4000 if key == 'error_message' else 600)
    if data.get('page_url'):
        result['page_url'] = safe_url(data['page_url'])
    if 'duration_ms' in data:
        result['duration_ms'] = max(0, min(int(data['duration_ms']), 86400000))
    title, user_action, helper_action = CODES[code]
    result.update(title=title, user_action=user_action, helper_action=helper_action)
    return result


def init(c):
    c.execute('CREATE TABLE IF NOT EXISTS diagnostic_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, body TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS diagnostic_run_idx ON diagnostic_events(run_id,seq)')


def emit(c, run_id='', task_id='', platform_name='', stage='client_request', status='ok',
         diagnostic=None, attempt=0, request_id='', **fields):
    if stage not in STAGES or status not in ('start', 'ok', 'error', 'wait', 'cancelled'):
        raise ValueError('日志阶段或状态不正确')
    record = dict(time=timestamp(), run_id=run_id, task_id=task_id,
                  platform=clean(platform_name, 100), stage=stage, stage_label=STAGES[stage],
                  status=status, attempt=attempt, request_id=request_id)
    if diagnostic:
        record['diagnostic'] = normalize(diagnostic)
    for key in ('tool', 'browser', 'method', 'observation', 'duration_ms'):
        if key in fields:
            record[key] = clean(fields[key], 1000)
    cursor = c.execute('INSERT INTO diagnostic_events(run_id,body) VALUES(?,?)',
                       (run_id, json.dumps(record, ensure_ascii=False)))
    record['seq'] = cursor.lastrowid
    return record


def history(c, run_id, limit=2000):
    try:
        rows = c.execute('SELECT seq,body FROM diagnostic_events WHERE run_id=? ORDER BY seq DESC LIMIT ?', (run_id, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(json.loads(row[1]), seq=row[0]) for row in reversed(rows)]


def executor_snapshot(executor):
    if executor is None:
        return dict(state='unknown', detail='离线导出无法判断当前聊天是否活跃。')
    last = executor.get('last_seen', 0)
    age = round(max(0, time.time() - last), 1) if last else None
    active = age is not None and age < 120
    return dict(state='recent' if active else 'no_recent_progress', last_update_seconds_ago=age,
                active_run=executor.get('active_run'),
                detail='120 秒内收到过进度。' if active else '近期未收到进度更新；不代表浏览器连接已断开。')


def service_output(root):
    """Only read bounded tails of this service's own logs, not arbitrary user files."""
    output = {}
    for name in ('service.stdout.log', 'service.stderr.log'):
        path = Path(root) / 'data' / name
        try:
            with path.open('rb') as source:
                source.seek(0, 2)
                size = source.tell()
                source.seek(max(0, size - 16384))
                if size > 16384:
                    source.readline() # Drop a partial first line whose credential key may be missing.
                output[name] = dict(tail=clean(source.read().decode('utf-8', errors='replace'), 8000), truncated=size > 16384)
        except OSError:
            output[name] = dict(available=False)
    return output


def bundle(c, run, root, executor=None, service_error=''):
    run = run or dict(id='', status='unknown', tasks=[])
    run_id = run['id']
    logs = history(c, run_id) if c and run_id else []
    service_logs = history(c, '', 100) if c else []
    tasks = []
    for t in run.get('tasks', []):
        entry = {k: t.get(k) for k in ('id', 'kind', 'platform', 'status', 'updated', 'attempt')}
        if t.get('diagnostic'):
            entry['diagnostic'] = normalize(t['diagnostic'])
        elif t.get('status') in ('failed', 'needs_user'):
            entry['diagnostic'] = normalize(dict(observation=clean(t.get('notice') or '旧记录缺少结构化错误信息，无法确认原因。')))
        tasks.append(entry)
    failures = [t for t in tasks if t.get('diagnostic') and t.get('status') in ('failed', 'needs_user')]
    if run.get('report_diagnostic'):
        failures.append(dict(id='',kind='report',platform='报告生成',status='failed',diagnostic=normalize(run['report_diagnostic'])))
    last_ok = next((l for l in reversed(logs) if l['status'] == 'ok'), None)
    fingerprint = hashlib.sha256()
    for name in ('server.py', 'diagnostics.py', 'index.html', 'chat_agent.py', 'report.py'):
        path = Path(root) / name
        if path.is_file():
            fingerprint.update(path.read_bytes())
    runtime = dict(skill_version=VERSION, source_fingerprint=fingerprint.hexdigest()[:16],
                   python=platform.python_version(), os=platform.system(), os_release=platform.release())
    result = dict(schema_version=1, exported_at=timestamp(), run_id=run_id, run_status=run['status'],
                  runtime=runtime, executor=executor_snapshot(executor), tasks=tasks,
                  last_successful_step=last_ok, events=logs, service_events=service_logs, service_output=service_output(root),
                  current_failures=failures, truncated=len(logs) >= 2000,
                  privacy='不包含 Cookie、Token、登录信息、页面全文或 AI 回答；工具错误已尽力脱敏，转发前仍请检查。',
                  evidence_note='日志仅包含服务自动记录的步骤和聊天实际回写的工具操作；缺失步骤不代表已执行。')
    lines = ['GEO 排障信息', '版本：' + VERSION, '任务编号：' + (run_id or '未知'),
             '任务状态：' + run['status'], '执行器：' + result['executor']['detail']]
    if last_ok:
        lines.append('最近成功步骤：' + last_ok['stage_label'] + ' · ' + last_ok.get('platform', ''))
    for t in failures:
        d = t['diagnostic']
        lines += ['', t['platform'] + ' / ' + d['stage_label'] + ' / ' + d['code'],
                  '提示：' + d['title'], '原因确认程度：' + d['certainty'],
                  '实际观察：' + d['observation'], '工具错误：' + d.get('error_message', '未回写'),
                  '同事操作：' + d['user_action'], '负责人排查：' + d['helper_action']]
    if not run_id:
        lines.append('当前没有对应的研究任务；服务事件与启动输出见诊断日志。')
    elif not failures:
        lines.append('当前没有结构化失败记录；如已卡住，请检查最后一步工具报错并补写诊断。')
    if service_error:
        result['service_error'] = normalize(dict(code='GEO_SERVICE_UNREACHABLE', stage='client_request',
                                               certainty='confirmed', observation='本次访问在线诊断接口失败，具体原因见错误消息。', error_message=service_error))
        lines += ['', '在线诊断请求失败，已改用离线记录；请根据错误区分权限、端口或版本问题。', clean(service_error)]
    lines += ['', '请附上导出的诊断 JSON；没有记录的根因保持未知。']
    result['summary'] = '\n'.join(lines)
    return result

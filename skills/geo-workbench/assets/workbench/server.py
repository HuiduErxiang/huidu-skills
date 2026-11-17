"""Local GEO workbench and durable queue for a Computer Use skill runner."""
import csv, io, json, re, sqlite3, threading, uuid, sys, time, traceback
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, quote
from report import render as render_report, write_report
import diagnostics as diag
ROOT=Path(__file__).resolve().parent
DB=ROOT/'data/workbench.db'
SEARCH=['抖音','快手','小红书','百度']
AI=['豆包','DeepSeek','千问','元宝','ChatGPT']
URLS={'抖音':'https://www.douyin.com/','快手':'https://www.kuaishou.com/','小红书':'https://www.xiaohongshu.com/explore','百度':'https://www.baidu.com/','豆包':'https://www.doubao.com/chat/','DeepSeek':'https://chat.deepseek.com/','千问':'https://www.qianwen.com/','元宝':'https://yuanbao.tencent.com/','ChatGPT':'https://chatgpt.com/'}
LOCK=threading.RLock()
RUNNER=None
CHAT_EXECUTOR={'last_seen':0,'active_run':None}
def now():return datetime.now().astimezone().isoformat()
def connect():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 ROOT.joinpath('data').mkdir(exist_ok=True)
 with connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, body TEXT)')
  c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT)")
  diag.init(c)
  diag.emit(c,stage='service_start',observation='工作台服务启动，版本 '+diag.VERSION)
  if not c.execute('SELECT 1 FROM runs LIMIT 1').fetchone():
   p=ROOT.parent/'geo-pilot/2026-11-15'; tasks=[]
   if (p/'jobs.json').exists():
    jobs=json.loads((p/'jobs.json').read_text())
    for j in jobs:
     prefix='doubao' if j['platform']=='豆包' else 'deepseek';suffix=j['question_id'] if j['mode']=='answer' else 'followup';f=p/'raw'/f'{prefix}-{suffix}-ax.txt'
     if not f.exists():continue
     raw=f.read_text();mark='文本 '+j['prompt'];start=raw.find(mark)
     section=raw[start+len(mark):] if start>=0 else raw
     lines=[]
     for line in section.splitlines():
      if '文本输入区' in line:break
      m=re.match(r'\s*\d+ (?:文本|text) (.*)',line)
      if m:lines.append(m[1])
     response='\n'.join(lines)
     tasks.append(dict(id=str(uuid.uuid4()),kind=j['mode'],platform=j['platform'],question=j['prompt'],status='done',response=response,evidence=str(f),mentions=('莱博雷生' in response) if j['mode']=='answer' else None,updated=now()))
    suggestions=[]
    if (p/'search-suggestions.csv').exists():
     with (p/'search-suggestions.csv').open() as source:suggestions=list(csv.DictReader(source))
    r=dict(id='pilot-20261115',product='莱博雷生',keyword='失眠',searches=['百度','小红书'],ais=['豆包','DeepSeek'],limit=3,status='completed',created=now(),questions=['失眠吃什么药好','失眠怎么调理','失眠是什么原因'],tasks=tasks,suggestions=suggestions,events=[dict(time=now(),text='导入此前真实试跑：8次提交完成。未做引用核验。')],imported=True)
    c.execute('INSERT INTO runs VALUES(?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
def read(c,ident):
 row=c.execute('SELECT body FROM runs WHERE id=?',(ident,)).fetchone()
 if not row:raise ValueError('任务不存在')
 return json.loads(row[0])
def save(c,r):
 c.execute('INSERT OR REPLACE INTO runs VALUES(?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
 if r.get('status')=='completed':
  try:
   write_report(r,ROOT/'data/reports');r.pop('report_diagnostic',None)
   diag.emit(c,r['id'],stage='report_generate',status='ok')
  except Exception as exc:
   r['report_diagnostic']=diag.normalize(dict(code='GEO_REPORT_FAILED',stage='report_generate',certainty='confirmed',observation='采集数据已保存，但生成报告失败。',error_type=type(exc).__name__,error_message=str(exc)))
   diag.emit(c,r['id'],stage='report_generate',status='error',diagnostic=r['report_diagnostic'])
  c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(r,ensure_ascii=False),r['id']))
def event(r,text):r['events'].append(dict(time=now(),text=text))
def task(kind,platform,question=''):return dict(id=str(uuid.uuid4()),kind=kind,platform=platform,question=question,status='queued',response='',evidence='',mentions=None,updated=now())
def validate_questions(qs):
 if not isinstance(qs,list) or not 1<=len(qs)<=20 or any(not isinstance(q,str) or not q.strip() or len(q)>4000 for q in qs):raise ValueError('请填写 1～20 条 AI 主设问，每条不超过 4000 字')
 qs=[q.strip() for q in qs]
 if len(set(qs))!=len(qs):raise ValueError('AI 主设问不能重复')
 return qs
def add_ai_tasks(r,qs):
 r['questions']=validate_questions(qs);r['question_source']='user';r['limit']=len(r['questions'])
 for platform in r['ais']:
  r['tasks'] += [task('answer',platform,q) for q in r['questions']]
  r['tasks'].append(task('clarification',platform,'用户的问题是：“'+r['questions'][0]+'”。为了进一步了解用户需求，请直接向用户提出3个澄清问题，每个问题单独列出；本轮只提问，不回答原问题。'))
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def failure(self,exc,code='GEO_UNKNOWN',stage='client_request',run_id='',status=500):
  request_id=getattr(self,'request_id',str(uuid.uuid4()))
  detail=diag.normalize(dict(code=code,stage=stage,certainty='confirmed',observation='本地工作台处理此步骤时发生异常。',error_type=type(exc).__name__,error_message=str(exc)))
  record=dict(time=diag.timestamp(),request_id=request_id,run_id=run_id,diagnostic=detail,stack=diag.clean(traceback.format_exc()))
  print(json.dumps(record,ensure_ascii=False),file=sys.stderr,flush=True)
  try:
   with LOCK,connect() as c:diag.emit(c,run_id,stage=stage,status='error',diagnostic=detail,request_id=request_id)
  except Exception:pass # Database failures still have a sanitized stderr record.
  return self.reply(dict(error=detail['title'],diagnostic=detail,request_id=request_id),status)
 def reply(self,data,status=200,ctype='application/json; charset=utf-8',download=None):
  body=(json.dumps(data,ensure_ascii=False) if ctype.startswith('application/json') else data).encode();self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');
  if download:self.send_header('Content-Disposition',"attachment; filename="+('geo-diagnostics.json' if download.endswith('.json') else 'geo-report.html')+"; filename*=UTF-8''"+quote(download,safe=''))
  self.end_headers();self.wfile.write(body)
 def do_GET(self):
  self.request_id=str(uuid.uuid4())
  path=urlparse(self.path).path
  if path=='/':return self.reply((ROOT/'index.html').read_text(),ctype='text/html; charset=utf-8')
  if path=='/api/diagnostics':
   with connect() as c:payload=diag.bundle(c,None,ROOT,CHAT_EXECUTOR)
   payload['service']={'online':True};return self.reply(payload)
  if path=='/api/config':return self.reply(dict(version=diag.VERSION,searches=SEARCH,ais=AI,urls=URLS,platform_checks=json.loads((ROOT/'platform-status.json').read_text()) if (ROOT/'platform-status.json').exists() else {},runner={'mode':'current-chat','active':time.time()-CHAT_EXECUTOR['last_seen']<120,'active_run':CHAT_EXECUTOR['active_run'],**diag.executor_snapshot(CHAT_EXECUTOR)}))
  if path=='/api/runs':
   with connect() as c:return self.reply([json.loads(row[0]) for row in c.execute('SELECT body FROM runs ORDER BY rowid DESC')])
  if path.startswith('/api/runs/'):
   ident=path.split('/')[3]
   try:
    with connect() as c:r=read(c,ident)
    if path.endswith('/diagnostics') or path.endswith('/diagnostics/download'):
     with connect() as c:payload=diag.bundle(c,r,ROOT,CHAT_EXECUTOR)
     return self.reply(payload,download=('GEO-'+ident+'-diagnostics.json') if path.endswith('/download') else None)
    if path.endswith('/report') or path.endswith('/report/download'):
     if r.get('status')!='completed':return self.reply(dict(error='请等待全部采集完成后生成报告'),409)
     try:
      with LOCK,connect() as c:
       report_path=write_report(r,ROOT/'data/reports');r.pop('report_diagnostic',None)
       c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(r,ensure_ascii=False),ident))
       diag.emit(c,ident,stage='report_generate',status='ok',request_id=self.request_id)
     except Exception as exc:return self.failure(exc,'GEO_REPORT_FAILED','report_generate',ident)
     return self.reply(report_path.read_text(),ctype='text/html; charset=utf-8',download=(r['product']+'_GEO研究报告.html') if path.endswith('/download') else None)
    if path.endswith('/export'):return self.reply(r)
    return self.reply(r)
   except ValueError as e:return self.reply(dict(error=str(e)),404)
   except Exception as e:return self.failure(e,'GEO_UNKNOWN',run_id=ident)
  return self.reply(dict(error='未找到页面'),404)
 def do_POST(self):
  self.request_id=str(uuid.uuid4());run_id=''
  # Same-origin JSON mutations only. Bound to loopback, never exposed on LAN.
  if self.headers.get('Origin') and self.headers['Origin'] not in ('http://127.0.0.1:8790','http://localhost:8790'):return self.reply(dict(error='来源不允许'),403)
  try:
   n=int(self.headers.get('Content-Length',0))
   if not 0<n<=2000000:raise ValueError('请求大小不正确')
   if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('需要JSON请求')
   d=json.loads(self.rfile.read(n));path=urlparse(self.path).path
   with LOCK,connect() as c:
    if path=='/api/executor':
     if d.get('run_id'):read(c,d['run_id'])
     CHAT_EXECUTOR.update(last_seen=time.time() if d.get('active',True) else 0,active_run=d.get('run_id'))
     diag.emit(c,d.get('run_id') or '',stage='executor_start',status='start' if d.get('active',True) else 'wait',request_id=self.request_id)
     c.commit();return self.reply({'ok':True})
    if path=='/api/runs':
     product=d.get('product','').strip();keyword=d.get('keyword','').strip();searches=d.get('searches',[]);ais=d.get('ais',[])
     if not product or not keyword or not searches or not ais:raise ValueError('请填写产品、关键词，并选择搜索与AI平台')
     if len(product)>100 or len(keyword)>100 or any(x not in SEARCH for x in searches) or any(x not in AI for x in ais):raise ValueError('参数不正确')
     qs=validate_questions(d.get('questions'))
     r=dict(id=str(uuid.uuid4()),input_schema=2,product=product,keyword=keyword,searches=list(dict.fromkeys(searches)),ais=list(dict.fromkeys(ais)),status='waiting_chat',created=now(),questions=[],suggestions=[],tasks=[task('search',x,keyword) for x in dict.fromkeys(searches)],events=[])
     add_ai_tasks(r,qs)
     event(r,'任务已保存：关键词用于搜索联想；用户填写的主设问仅用于 AI 平台，两路任务独立。若聊天已结束，请回聊天说“继续研究”。')
     diag.emit(c,r['id'],stage='task_created',request_id=self.request_id)
     diag.emit(c,r['id'],stage='question_confirm',request_id=self.request_id,observation='用户已填写 '+str(len(qs))+' 条 AI 主设问；来源不是搜索联想。')
     save(c,r);c.commit();return self.reply(r,201)
    parts=path.strip('/').split('/')
    if len(parts)!=4 or parts[:2]!=['api','runs']:raise ValueError('接口不存在')
    r=read(c,parts[2]);run_id=r['id'];action=parts[3]
    if action=='log':
     if r['status'] in ('paused','completed'):raise ValueError('任务已暂停或完成，不能继续写入采集步骤')
     t=next((x for x in r['tasks'] if x['id']==d.get('task_id')),None)
     if d.get('task_id') and not t:raise ValueError('子任务不存在')
     record=diag.emit(c,run_id,task_id=t['id'] if t else '',platform_name=t['platform'] if t else '',stage=d.get('stage','client_request'),status=d.get('status','ok'),diagnostic=d.get('diagnostic'),attempt=t.get('attempt',0) if t else 0,request_id=self.request_id,**{k:d[k] for k in ('tool','browser','method','observation','duration_ms') if k in d})
     CHAT_EXECUTOR.update(last_seen=time.time(),active_run=run_id)
     c.commit();return self.reply(record,201)
    if action=='questions':
     if r['status'] in ('paused','completed'):raise ValueError('任务已暂停或完成')
     if any(t['kind'] in ('answer','clarification') for t in r['tasks']):raise ValueError('已生成 AI 任务，不能覆盖主设问；请新建研究使用其他问题')
     add_ai_tasks(r,d.get('questions'))
     r['status']='waiting_chat';event(r,'用户已填写 AI 主设问，AI 任务已就绪，无需等待搜索联想完成。')
     diag.emit(c,run_id,stage='question_confirm',request_id=self.request_id)
    elif action=='control':
     op=d.get('action')
     if op=='pause':
      r['status']='paused';event(r,'已请求暂停。当前聊天会在下一步操作前检查并停止。')
      diag.emit(c,run_id,stage='user_pause',status='cancelled',request_id=self.request_id)
      if RUNNER:RUNNER.interrupt(r['id'])
     elif op=='resume':
      r['status']='waiting_chat'
      for t in r['tasks']:
       if t['status'] in ('needs_user','failed'):t['status']='queued'
      event(r,'已标记可以继续。当前聊天执行时会重新检查页面；若聊天已结束，请回聊天说“继续研究”。')
      diag.emit(c,run_id,stage='user_resume',status='wait',request_id=self.request_id)
     else:raise ValueError('操作不支持')
    elif action=='task':
     if r['status'] in ('paused','completed'):raise ValueError('任务已暂停或完成')
     t=next((x for x in r['tasks'] if x['id']==d.get('task_id')),None)
     if not t:raise ValueError('子任务不存在')
     status=d.get('status')
     if status not in ('running','needs_user','failed','done'):raise ValueError('状态不正确')
     if status=='done' and not str(d.get('response','')).strip():raise ValueError('完成前必须保存真实采集内容')
     if status=='running' and t['status']!='running':
      t['attempt']=t.get('attempt',0)+1;t.pop('diagnostic',None);t.pop('notice',None)
     if status in ('failed','needs_user'):
      detail=diag.normalize(d.get('diagnostic') or dict(observation=d.get('notice') or '执行端未回写具体错误，原因未确认。'))
      if detail['code'] in ('GEO_LOGIN_REQUIRED','GEO_VERIFICATION_REQUIRED') and detail['certainty']!='confirmed':raise ValueError('登录或验证提示必须有真实页面证据')
      t['diagnostic']=detail
      diag.emit(c,run_id,task_id=t['id'],platform_name=t['platform'],stage=detail['stage'],status='wait' if status=='needs_user' else 'error',diagnostic=detail,attempt=t.get('attempt',0),request_id=self.request_id)
     elif status=='done':t.pop('diagnostic',None);t.pop('notice',None)
     for k in ('response','evidence','notice','session_url','visible_model','web_search_state'):
      if k in d:
       if not isinstance(d[k],str):raise ValueError('字段需要文本')
       t[k]=d[k]
     t['status']=status;t['updated']=now()
     CHAT_EXECUTOR.update(last_seen=time.time(),active_run=r['id'])
     if status=='done':t['mentions']=r['product'] in t['response'] if t['kind']=='answer' else None
     if t['kind']=='search' and status=='done':
      terms=d.get('suggestions',[])
      if not terms or any(not isinstance(x,str) or not x.strip() for x in terms):raise ValueError('采集必须包含真实联想列表')
      r['suggestions']=[s for s in r['suggestions'] if s.get('platform')!=t['platform']]
      r['suggestions'] += [dict(platform=t['platform'],text=x,rank=i+1,collected_at=now(),evidence=t.get('evidence','')) for i,x in enumerate(terms)]
     r['status']='needs_user' if any(x['status']=='needs_user' for x in r['tasks']) else 'running'
     if all(x['status']=='done' for x in r['tasks']):r['status']='completed' if r['questions'] else 'select_questions'
     if status in ('running','done'):diag.emit(c,run_id,task_id=t['id'],platform_name=t['platform'],stage='result_save' if status=='done' else 'executor_start',status='ok' if status=='done' else 'start',attempt=t.get('attempt',0),request_id=self.request_id)
     event(r,t['platform']+' · '+{'search':'联想采集','answer':'回答测试','clarification':'追问探索'}[t['kind']]+' · '+status)
    else:raise ValueError('操作不支持')
    save(c,r);c.commit();return self.reply(r)
  except (ValueError,TypeError,KeyError,StopIteration) as e:return self.failure(e,'GEO_API_INVALID',run_id=run_id,status=400)
  except sqlite3.Error as e:return self.failure(e,'GEO_WRITE_FAILED',stage='result_save',run_id=run_id)
  except Exception as e:return self.failure(e,'GEO_UNKNOWN',run_id=run_id)
if __name__=='__main__':
 try:
  init()
  service=ThreadingHTTPServer(('127.0.0.1',8790),Handler)
  print('GEO workbench '+diag.VERSION+': http://127.0.0.1:8790 · 当前聊天执行模式',flush=True)
  service.serve_forever()
 except KeyboardInterrupt:pass
 except Exception as exc:
  detail=diag.normalize(dict(code='GEO_SERVICE_START_FAILED',stage='service_start',certainty='confirmed',observation='启动或运行本地工作台服务时发生异常。',error_type=type(exc).__name__,error_message=str(exc)))
  print(json.dumps(dict(time=diag.timestamp(),diagnostic=detail),ensure_ascii=False),file=sys.stderr,flush=True)
  try:
   with connect() as c:diag.emit(c,stage='service_start',status='error',diagnostic=detail)
  except Exception:pass
  sys.exit(1)

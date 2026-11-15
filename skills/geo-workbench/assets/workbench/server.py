"""Local GEO workbench and durable queue for a Computer Use skill runner."""
import csv, io, json, re, sqlite3, threading, uuid, sys, time
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, quote
from report import render as render_report, write_report
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
 if r.get('status')=='completed':write_report(r,ROOT/'data/reports')
 c.execute('INSERT OR REPLACE INTO runs VALUES(?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
def event(r,text):r['events'].append(dict(time=now(),text=text))
def task(kind,platform,question=''):return dict(id=str(uuid.uuid4()),kind=kind,platform=platform,question=question,status='queued',response='',evidence='',mentions=None,updated=now())
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,data,status=200,ctype='application/json; charset=utf-8',download=None):
  body=(json.dumps(data,ensure_ascii=False) if ctype.startswith('application/json') else data).encode();self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');
  if download:self.send_header('Content-Disposition',"attachment; filename=geo-report.html; filename*=UTF-8''"+quote(download,safe=''))
  self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/':return self.reply((ROOT/'index.html').read_text(),ctype='text/html; charset=utf-8')
  if path=='/api/config':return self.reply(dict(searches=SEARCH,ais=AI,urls=URLS,platform_checks=json.loads((ROOT/'platform-status.json').read_text()) if (ROOT/'platform-status.json').exists() else {},runner={'mode':'current-chat','active':time.time()-CHAT_EXECUTOR['last_seen']<120,'active_run':CHAT_EXECUTOR['active_run']}))
  if path=='/api/runs':
   with connect() as c:return self.reply([json.loads(row[0]) for row in c.execute('SELECT body FROM runs ORDER BY rowid DESC')])
  if path.startswith('/api/runs/'):
   ident=path.split('/')[3]
   try:
    with connect() as c:r=read(c,ident)
    if path.endswith('/report') or path.endswith('/report/download'):
     if r.get('status')!='completed':return self.reply(dict(error='请等待全部采集完成后生成报告'),409)
     with LOCK:report_path=write_report(r,ROOT/'data/reports')
     return self.reply(report_path.read_text(),ctype='text/html; charset=utf-8',download=(r['product']+'_GEO研究报告.html') if path.endswith('/download') else None)
    if path.endswith('/export'):return self.reply(r)
    return self.reply(r)
   except ValueError as e:return self.reply(dict(error=str(e)),404)
  return self.reply(dict(error='未找到页面'),404)
 def do_POST(self):
  # Same-origin JSON mutations only. Bound to loopback, never exposed on LAN.
  if self.headers.get('Origin') and self.headers['Origin'] not in ('http://127.0.0.1:8790','http://localhost:8790'):return self.reply(dict(error='来源不允许'),403)
  try:
   n=int(self.headers.get('Content-Length',0))
   if not 0<n<=2000000:raise ValueError('请求大小不正确')
   if not self.headers.get('Content-Type','').startswith('application/json'):raise ValueError('需要JSON请求')
   d=json.loads(self.rfile.read(n));path=urlparse(self.path).path
   with LOCK,connect() as c:
    if path=='/api/executor':
     CHAT_EXECUTOR.update(last_seen=time.time() if d.get('active',True) else 0,active_run=d.get('run_id'));return self.reply({'ok':True})
    if path=='/api/runs':
     product=d.get('product','').strip();keyword=d.get('keyword','').strip();searches=d.get('searches',[]);ais=d.get('ais',[])
     if not product or not keyword or not searches or not ais:raise ValueError('请填写产品、关键词，并选择搜索与AI平台')
     if len(product)>100 or len(keyword)>100 or any(x not in SEARCH for x in searches) or any(x not in AI for x in ais):raise ValueError('参数不正确')
     r=dict(id=str(uuid.uuid4()),product=product,keyword=keyword,searches=list(dict.fromkeys(searches)),ais=list(dict.fromkeys(ais)),limit=3,status='waiting_chat',created=now(),questions=[],suggestions=[],tasks=[task('search',x,keyword) for x in dict.fromkeys(searches)],events=[])
     event(r,'任务已保存。调用技能后正在等待的当前聊天会接手执行；若聊天已结束，请回聊天说“继续研究”。进度在本页显示。');save(c,r);return self.reply(r,201)
    parts=path.strip('/').split('/')
    if len(parts)!=4 or parts[:2]!=['api','runs']:raise ValueError('接口不存在')
    r=read(c,parts[2]);action=parts[3]
    if action=='questions':
     qs=d.get('questions',[])
     if len(qs)!=3 or any(not isinstance(q,str) or not q.strip() for q in qs) or len(set(q.strip() for q in qs))!=3:raise ValueError('请填写3个不同的入口问题')
     if any(t['kind']=='answer' for t in r['tasks']):raise ValueError('已生成AI任务，不能覆盖入口')
     if any(t['kind']=='search' and t['status']!='done' for t in r['tasks']):raise ValueError('请先完成所选搜索平台的采集')
     r['questions']=[q.strip() for q in qs]
     for platform in r['ais']:
      r['tasks'] += [task('answer',platform,q) for q in r['questions']]
      r['tasks'].append(task('clarification',platform,'用户的问题是：“'+r['questions'][0]+'”。为了进一步了解用户需求，请直接向用户提出3个澄清问题，每个问题单独列出；本轮只提问，不回答原问题。'))
     r['status']='waiting_chat';event(r,'3个入口已确认，等待当前聊天继续AI测试。')
    elif action=='control':
     op=d.get('action')
     if op=='pause':
      r['status']='paused';event(r,'已请求暂停。当前聊天会在下一步操作前检查并停止。')
      if RUNNER:RUNNER.interrupt(r['id'])
     elif op=='resume':
      r['status']='waiting_chat'
      for t in r['tasks']:
       if t['status'] in ('needs_user','failed'):t['status']='queued'
      event(r,'已标记可以继续。当前聊天执行时会重新检查页面；若聊天已结束，请回聊天说“继续研究”。')
     else:raise ValueError('操作不支持')
    elif action=='task':
     if r['status'] in ('paused','completed'):raise ValueError('任务已暂停或完成')
     t=next((x for x in r['tasks'] if x['id']==d.get('task_id')),None)
     if not t:raise ValueError('子任务不存在')
     status=d.get('status')
     if status not in ('running','needs_user','failed','done'):raise ValueError('状态不正确')
     if status=='done' and not str(d.get('response','')).strip():raise ValueError('完成前必须保存真实采集内容')
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
     event(r,t['platform']+' · '+{'search':'联想采集','answer':'回答测试','clarification':'追问探索'}[t['kind']]+' · '+status)
    else:raise ValueError('操作不支持')
    save(c,r);return self.reply(r)
  except (ValueError,TypeError,KeyError,StopIteration) as e:return self.reply(dict(error=str(e) or '输入不正确'),400)
if __name__=='__main__':
 init()
 print('GEO workbench: http://127.0.0.1:8790 · 当前聊天执行模式',flush=True)
 ThreadingHTTPServer(('127.0.0.1',8790),Handler).serve_forever()

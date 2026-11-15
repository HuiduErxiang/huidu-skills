"""Small local API client used by the current chat to report real work."""
import argparse,json,urllib.request
p=argparse.ArgumentParser();p.add_argument('action',choices=['get','start','idle','resume','task','questions','next','collect']);p.add_argument('--run');p.add_argument('--task');p.add_argument('--status');p.add_argument('--file');a=p.parse_args()
path='runs';body=None
if a.action in ('next','collect'):
 with urllib.request.urlopen('http://127.0.0.1:8790/api/runs/'+a.run) as response:r=json.load(response)
 candidates=[t for t in r['tasks'] if t['status'] in (('queued',) if a.action=='next' else ('running',)) and t['platform']==a.task]
 if not candidates:raise SystemExit('没有匹配的待执行任务')
 t=candidates[0];a.task=t['id'];a.status='running' if a.action=='next' else 'done';a.action='task'
if a.action in ('start','idle'):path='executor';body={'active':a.action=='start','run_id':a.run}
elif a.action=='resume':path='runs/'+a.run+'/control';body={'action':'resume'}
elif a.action=='task':
 path='runs/'+a.run+'/task';body=json.load(open(a.file)) if a.file else {};body.update(task_id=a.task,status=a.status)
elif a.action=='questions':path='runs/'+a.run+'/questions';body=json.load(open(a.file))
req=urllib.request.Request('http://127.0.0.1:8790/api/'+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as response:result=json.load(response)
if a.action=='get':
 for r in result:
  if a.run and r['id']!=a.run:continue
  print(json.dumps({**r,'events':r['events'][-3:],'tasks':[{k:v for k,v in t.items() if k!='response'} for t in r['tasks']]},ensure_ascii=False))
else:print(json.dumps({'status':result.get('status','ok'),'tasks':[{k:t[k] for k in ('id','kind','platform','status')} for t in result.get('tasks',[])]},ensure_ascii=False))

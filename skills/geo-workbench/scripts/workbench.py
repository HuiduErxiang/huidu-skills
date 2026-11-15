"""Locate the personal workbench, check readiness, and wait for a UI-created run."""
import argparse,json,time,urllib.request,urllib.error,os
from pathlib import Path
URL='http://127.0.0.1:8790'
ROOT=Path(os.environ.get('GEO_WORKBENCH_ROOT',str(Path(__file__).resolve().parents[1]/'assets/workbench')))
def get(path):
 with urllib.request.urlopen(URL+'/api/'+path,timeout=4) as response:return json.load(response)
p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','wait']);p.add_argument('--after',default='');p.add_argument('--timeout',type=int,default=45);a=p.parse_args()
if a.action=='prepare':
 try:
  config=get('config')
  if not isinstance(config.get('runner'),dict) or config['runner'].get('mode')!='current-chat':raise ValueError('端口被其他服务占用，或运行了旧版服务')
  runs=get('runs');print(json.dumps(dict(status='ready',url=URL,app_root=str(ROOT),newest_run=runs[0]['id'] if runs else ''),ensure_ascii=False))
 except (urllib.error.URLError,TimeoutError,ConnectionError):
  if not (ROOT/'server.py').is_file():raise SystemExit('找不到工作台程序：'+str(ROOT))
  print(json.dumps(dict(status='needs_start',command=['python3',str(ROOT/'server.py')],cwd=str(ROOT),url=URL),ensure_ascii=False))
else:
 deadline=time.monotonic()+min(max(a.timeout,1),50)
 while time.monotonic()<deadline:
  runs=get('runs')
  # Only a newly created, ready task. Do not silently resume old paused research.
  baseline=next((i for i,r in enumerate(runs) if r['id']==a.after),None)
  if a.after and baseline is None:raise SystemExit('打开前的任务基线不存在，请重新prepare，避免误接手旧任务')
  new_runs=runs[:baseline] if baseline is not None else runs
  candidate=next((r for r in new_runs if r['status']=='waiting_chat' and not r.get('imported')),None)
  if candidate:
   print(json.dumps(dict(status='created',run_id=candidate['id'],product=candidate['product'],keyword=candidate['keyword'],searches=candidate['searches'],ais=candidate['ais']),ensure_ascii=False));break
  time.sleep(1)
 else:print(json.dumps(dict(status='waiting',url=URL)))

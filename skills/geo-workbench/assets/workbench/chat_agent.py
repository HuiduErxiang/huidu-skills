"""Report real browser operations, errors, and results from the active chat."""
import argparse
import json
import sys
import urllib.error
import urllib.request
import diagnostics as diag

p=argparse.ArgumentParser()
p.add_argument('action',choices=['get','start','idle','resume','task','questions','next','collect','log','diagnose'])
for name in ('run','task','status','file','stage','code','observation','error-type','error-message','tool','browser','method','page-url','evidence'):
    p.add_argument('--'+name)
p.add_argument('--certainty',choices=['confirmed','suspected','unknown'],default='unknown')
p.add_argument('--duration-ms',type=int)
a=p.parse_args()
URL='http://127.0.0.1:8790/api/'


def request(path,body=None):
    req=urllib.request.Request(URL+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response)


def main():
    if a.action!='get' and not a.run:
        p.error('此操作需要 --run')
    path='runs';body=None
    if a.action in ('next','collect'):
        r=request('runs/'+a.run)
        candidates=[t for t in r['tasks'] if t['status'] in (('queued',) if a.action=='next' else ('running',)) and t['platform']==a.task]
        if not candidates:
            raise ValueError('没有匹配的待执行任务')
        t=candidates[0];a.task=t['id'];a.status='running' if a.action=='next' else 'done';a.action='task'
    payload=json.load(sys.stdin if a.file=='-' else open(a.file,encoding='utf-8')) if a.file else {}
    detail={k:getattr(a,k) for k in ('code','stage','observation','error_type','error_message','tool','browser','method','page_url','evidence','duration_ms') if getattr(a,k) is not None}
    if a.code:
        detail['certainty']=a.certainty
        detail=diag.normalize(detail)
    if a.action in ('start','idle'):
        path='executor';body={'active':a.action=='start','run_id':a.run}
    elif a.action=='resume':
        path='runs/'+a.run+'/control';body={'action':'resume'}
    elif a.action=='task':
        path='runs/'+a.run+'/task';body=payload;body.update(task_id=a.task,status=a.status)
        if a.code:body['diagnostic']=detail
    elif a.action=='log':
        path='runs/'+a.run+'/log';body=payload
        body.update(task_id=a.task,stage=a.stage or 'client_request',status=a.status or 'ok')
        for k in ('tool','browser','method','observation','duration_ms'):
            if getattr(a,k) is not None:body[k]=getattr(a,k)
        if a.code:body['diagnostic']=detail
    elif a.action=='questions':
        path='runs/'+a.run+'/questions';body=payload
    elif a.action=='diagnose':
        path='runs/'+a.run+'/diagnostics'
    result=request(path,body)
    if a.action=='get':
        for r in result:
            if a.run and r['id']!=a.run:continue
            print(json.dumps({**r,'events':r['events'][-3:],'tasks':[{k:v for k,v in t.items() if k!='response'} for t in r['tasks']]},ensure_ascii=False))
    elif a.action=='diagnose':
        print(result['summary'])
    elif a.action=='log':
        print(json.dumps(result,ensure_ascii=False))
    else:
        print(json.dumps({'status':result.get('status','ok'),'tasks':[{k:t[k] for k in ('id','kind','platform','status')} for t in result.get('tasks',[])]},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except urllib.error.HTTPError as exc:
        try:message=json.load(exc)
        except Exception:message={'error':str(exc)}
        print(json.dumps(message,ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
    except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
        print(json.dumps(diag.normalize(dict(code='GEO_SERVICE_UNREACHABLE',stage='client_request',observation='向本地工作台发起请求失败。',error_type=type(exc).__name__,error_message=str(exc))),ensure_ascii=False),file=sys.stderr)
        print('请运行技能 scripts/workbench.py diagnose --run '+str(a.run or 'latest')+'，输出离线排障信息。',file=sys.stderr)
        sys.exit(1)
    except (ValueError,OSError) as exc:
        print(diag.clean(str(exc)),file=sys.stderr)
        sys.exit(1)

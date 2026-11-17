"""Locate the workbench, wait for a UI-created run, or export online/offline diagnostics."""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

URL='http://127.0.0.1:8790'
BUNDLED=Path(__file__).resolve().parents[1]/'assets/workbench'
ROOT=Path(os.environ.get('GEO_WORKBENCH_ROOT',str(BUNDLED)))
sys.path.insert(0,str(BUNDLED))
import diagnostics as diag


def get(path):
    with urllib.request.urlopen(URL+'/api/'+path,timeout=4) as response:
        return json.load(response)


p=argparse.ArgumentParser()
p.add_argument('action',choices=['prepare','start','wait','diagnose'])
p.add_argument('--after',default='')
p.add_argument('--timeout',type=int,default=45)
p.add_argument('--run',default='latest')
p.add_argument('--output',help='诊断 JSON 输出路径；- 表示标准输出。不指定时只显示摘要。')
a=p.parse_args()


def diagnose():
    online_error=''
    try:
        runs=get('runs')
        run=next((r for r in runs if a.run=='latest' or r['id']==a.run),None)
        if not run:
            result=get('diagnostics')
            if a.run!='latest':
                result['requested_run_missing']=True
                result['summary']+='\n指定的任务不存在，但本地服务可连接。'
            return result
        return get('runs/'+run['id']+'/diagnostics')
    except (urllib.error.URLError,TimeoutError,ConnectionError,ValueError) as exc:
        online_error=str(exc)
    c=None
    try:
        db=ROOT/'data/workbench.db'
        if db.is_file():
            c=sqlite3.connect('file:'+quote(str(db),safe='/')+'?mode=ro',uri=True)
            if a.run=='latest':
                row=c.execute('SELECT body FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
            else:
                row=c.execute('SELECT body FROM runs WHERE id=?',(a.run,)).fetchone()
            run=json.loads(row[0]) if row else None
        else:
            run=None
        result=diag.bundle(c,run,ROOT,service_error=online_error)
        if not run:
            result['summary']+='\n未找到该任务的本地记录，不能还原当时浏览器错误。'
        result['offline']=True
        result['service']={'online':False}
        return result
    except (sqlite3.Error,ValueError,OSError) as exc:
        result=diag.bundle(None,None,ROOT,service_error=online_error)
        result['offline']=True
        result['service']={'online':False}
        result['offline_read_error']=diag.clean(str(exc))
        result['summary']+='\n离线记录读取失败：'+diag.clean(str(exc))
        return result
    finally:
        if c:c.close()


def start():
    """Keep the HTTP service separate from the lifetime of the launching shell."""
    try:
        config=get('config')
    except urllib.error.HTTPError as exc:
        raise ValueError('端口 8790 有服务响应，但不是可用的 GEO 服务：'+str(exc))
    except (urllib.error.URLError,TimeoutError,ConnectionError):
        config=None
    if config is not None:
        if config.get('runner',{}).get('mode')!='current-chat':
            raise ValueError('端口 8790 被其他服务占用；不重复启动')
        return dict(status='ready',url=URL,version=config.get('version','legacy'),reused=True)
    if not (ROOT/'server.py').is_file():
        raise ValueError('找不到工作台程序：'+str(ROOT))
    data=ROOT/'data';data.mkdir(parents=True,exist_ok=True)
    stdout=data/'service.stdout.log';stderr=data/'service.stderr.log'
    command=[sys.executable,'-B',str(ROOT/'server.py')]
    if sys.platform=='darwin':
        label='com.huidu.geo-workbench'
        target='gui/'+str(os.getuid())+'/'+label
        existing=subprocess.run(['launchctl','print',target],capture_output=True,text=True)
        launch=['launchctl','kickstart',target] if existing.returncode==0 else ['launchctl','submit','-l',label,'-o',str(stdout),'-e',str(stderr),'--',*command]
        result=subprocess.run(launch,capture_output=True,text=True)
        if result.returncode:
            raise ValueError('后台服务启动失败：'+diag.clean(result.stderr or result.stdout))
        mode='macos-launchd'
    else:
        kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP}
        with stdout.open('ab') as out,stderr.open('ab') as err:
            subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=err,close_fds=True,**kwargs)
        mode='detached-process'
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        try:
            config=get('config')
            if config.get('runner',{}).get('mode')!='current-chat':
                raise ValueError('端口响应不属于 GEO 工作台')
            return dict(status='ready',url=URL,version=config.get('version','legacy'),launch_mode=mode,stdout=str(stdout),stderr=str(stderr))
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            time.sleep(0.2)
    raise ValueError('后台服务尚不可连接。请输出服务日志：'+str(stderr))


try:
    if a.action=='diagnose':
        result=diagnose()
        if a.output=='-':
            print(json.dumps(result,ensure_ascii=False,indent=2))
        elif a.output:
            path=Path(a.output).expanduser().resolve()
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(result['summary']);print('\n诊断日志：'+str(path))
        else:
            print(result['summary'])
            print('\n可加 --output /绝对路径/diagnostics.json 导出日志供负责人排查。')
    elif a.action=='start':
        print(json.dumps(start(),ensure_ascii=False))
    elif a.action=='prepare':
        try:
            config=get('config')
            if not isinstance(config.get('runner'),dict) or config['runner'].get('mode')!='current-chat':
                raise ValueError('端口被其他服务占用，或运行了旧版服务')
            runs=get('runs')
            print(json.dumps(dict(status='ready',url=URL,version=config.get('version','legacy'),app_root=str(ROOT),newest_run=runs[0]['id'] if runs else ''),ensure_ascii=False))
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if not (ROOT/'server.py').is_file():
                raise ValueError('找不到工作台程序：'+str(ROOT))
            print(json.dumps(dict(status='needs_start',command=[sys.executable,'-B',str(Path(__file__).resolve()),'start'],cwd=str(ROOT),url=URL,log_files=[str(ROOT/'data/service.stdout.log'),str(ROOT/'data/service.stderr.log')]),ensure_ascii=False))
    else:
        deadline=time.monotonic()+min(max(a.timeout,1),50)
        while time.monotonic()<deadline:
            runs=get('runs')
            baseline=next((i for i,r in enumerate(runs) if r['id']==a.after),None)
            if a.after and baseline is None:
                raise ValueError('打开前的任务基线不存在，请重新 prepare，避免误接手旧任务')
            new_runs=runs[:baseline] if baseline is not None else runs
            candidate=next((r for r in new_runs if r['status']=='waiting_chat' and not r.get('imported')),None)
            if candidate:
                print(json.dumps(dict(status='created',run_id=candidate['id'],product=candidate['product'],keyword=candidate['keyword'],questions=candidate.get('questions',[]),question_source=candidate.get('question_source','legacy_unknown'),searches=candidate['searches'],ais=candidate['ais']),ensure_ascii=False));break
            time.sleep(1)
        else:
            print(json.dumps(dict(status='waiting',url=URL)))
except (urllib.error.URLError,TimeoutError,ConnectionError,ValueError,OSError) as exc:
    print(json.dumps(dict(status='failed',error=diag.clean(str(exc)),next_action='运行 scripts/workbench.py diagnose 输出诊断信息；不要把请求失败直接归因为登录失效。'),ensure_ascii=False),file=sys.stderr)
    sys.exit(1)

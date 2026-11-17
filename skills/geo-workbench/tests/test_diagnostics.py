"""Behavioral checks without real browser access, accounts, or on-disk test data."""
import contextlib
import io
import json
import runpy
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'assets/workbench'))
import diagnostics as diag
import server


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.uri='file:geo-test-'+str(uuid.uuid4())+'?mode=memory&cache=shared'
        self.anchor=sqlite3.connect(self.uri,uri=True)
        def connect():
            c=sqlite3.connect(self.uri,uri=True);c.row_factory=sqlite3.Row;return c
        self.connect_patch=patch.object(server,'connect',connect);self.connect_patch.start()
        self.report_patch=patch.object(server,'write_report',return_value=ROOT/'SKILL.md');self.report_patch.start()
        with connect() as c:
            c.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,body TEXT)')
            diag.init(c)
            diag.emit(c,stage='service_start')
        server.CHAT_EXECUTOR.update(last_seen=0,active_run=None)

    def tearDown(self):
        self.report_patch.stop();self.connect_patch.stop();self.anchor.close()

    def request(self,path,body=None):
        h=object.__new__(server.Handler)
        h.path='/api/'+path
        payload=json.dumps(body,ensure_ascii=False).encode() if body is not None else b''
        h.headers={'Content-Type':'application/json','Content-Length':str(len(payload))}
        h.rfile=io.BytesIO(payload)
        response={}
        def reply(data,status=200,**kw):response.update(data=data,status=status,**kw)
        h.reply=reply
        with contextlib.redirect_stderr(io.StringIO()):
            (h.do_POST if body is not None else h.do_GET)()
        return response['status'],response['data']

    def create(self):
        status,r=self.request('runs',dict(product='ExampleProduct',keyword='example',questions=['q1','q2','q3'],searches=['小红书'],ais=['豆包']))
        self.assertEqual(status,201)
        return r['id'],r['tasks'][0]['id']

    def task(self,run,task,status,**fields):
        return self.request('runs/'+run+'/task',dict(task_id=task,status=status,**fields))

    def diagnosis(self,run):
        status,d=self.request('runs/'+run+'/diagnostics');self.assertEqual(status,200);return d

    def test_browser_failure_has_evidence_and_actionable_export(self):
        r,t=self.create();self.task(r,t,'running')
        self.request('runs/'+r+'/log',dict(task_id=t,stage='page_open',status='ok',tool='browser',observation='页面可读取'))
        detail=dict(code='GEO_BROWSER_UNAVAILABLE',stage='suggestion_read',certainty='confirmed',observation='读取联想时工具明确返回会话不存在',error_message='No session; access_token=private-token',tool='browser',page_url='https://example.com/private/chat/123?token=secret')
        self.assertEqual(self.task(r,t,'failed',diagnostic=detail)[0],200)
        d=self.diagnosis(r);raw=json.dumps(d,ensure_ascii=False)
        self.assertIn('GEO_BROWSER_UNAVAILABLE',d['summary'])
        self.assertIn('同事操作',d['summary']);self.assertIn('负责人排查',d['summary'])
        self.assertEqual(d['last_successful_step']['stage'],'page_open')
        self.assertNotIn('private-token',raw);self.assertNotIn('/private/chat/',raw)
        self.assertEqual(d['current_failures'][0]['diagnostic']['page_url'],'https://example.com')

    def test_login_cannot_be_confirmed_without_observation(self):
        r,t=self.create()
        status,error=self.task(r,t,'needs_user',diagnostic=dict(code='GEO_LOGIN_REQUIRED',stage='login_check',certainty='confirmed'))
        self.assertEqual(status,400);self.assertIn('request_id',error)
        self.assertEqual(self.diagnosis(r)['tasks'][0]['status'],'queued')

    def test_legacy_failure_is_unknown_not_assumed_login(self):
        r,t=self.create();self.task(r,t,'needs_user',notice='旧版待复查')
        d=self.diagnosis(r)['current_failures'][0]['diagnostic']
        self.assertEqual(d['code'],'GEO_UNKNOWN');self.assertEqual(d['certainty'],'unknown')

    def test_retry_preserves_events_but_clears_current_error(self):
        r,t=self.create();self.task(r,t,'running');self.task(r,t,'failed',notice='missing tool details')
        self.request('runs/'+r+'/control',dict(action='resume'));self.task(r,t,'running')
        self.task(r,t,'done',response='实际采集说明',suggestions=['真实联想'])
        d=self.diagnosis(r)
        self.assertEqual(d['current_failures'],[]);self.assertEqual(d['tasks'][0]['attempt'],2)
        self.assertTrue(any(e['status']=='error' for e in d['events']))
        self.assertNotIn('实际采集说明',json.dumps(d,ensure_ascii=False))

    def test_paused_run_rejects_browser_log_and_task(self):
        r,t=self.create();self.request('runs/'+r+'/control',dict(action='pause'))
        self.assertEqual(self.request('runs/'+r+'/log',dict(task_id=t,stage='keyword_input',status='ok'))[0],400)
        self.assertEqual(self.task(r,t,'running')[0],400)
        self.assertEqual(self.diagnosis(r)['run_status'],'paused')

    def test_no_recent_progress_does_not_claim_disconnection(self):
        state=diag.executor_snapshot(dict(last_seen=time.time()-150,active_run='run'))
        self.assertEqual(state['state'],'no_recent_progress')
        self.assertIn('不代表',state['detail']);self.assertNotIn('code',state)
        self.assertEqual(diag.executor_snapshot(None)['state'],'unknown')

    def test_report_failure_preserves_all_collected_answers(self):
        r,t=self.create();self.task(r,t,'done',response='search result',suggestions=['query'])
        _,run=self.request('runs/'+r)
        server.write_report.side_effect=OSError('disk not writable')
        for task in run['tasks'][1:]:
            self.assertEqual(self.task(r,task['id'],'done',response='private answer '+task['id'])[0],200)
        status,saved=self.request('runs/'+r)
        self.assertEqual(status,200);self.assertEqual(saved['status'],'completed')
        self.assertTrue(all(t['status']=='done' for t in saved['tasks']))
        self.assertEqual(saved['report_diagnostic']['code'],'GEO_REPORT_FAILED')
        d=self.diagnosis(r)
        self.assertIn('GEO_REPORT_FAILED',d['summary'])
        self.assertNotIn('private answer',json.dumps(d))

    def test_unknown_task_log_does_not_create_browser_success(self):
        r,t=self.create()
        self.assertEqual(self.request('runs/'+r+'/log',dict(task_id='wrong',stage='page_open',status='ok'))[0],400)
        self.assertFalse(any(e['stage']=='page_open' for e in self.diagnosis(r)['events']))

    def test_invalid_success_does_not_create_save_event(self):
        r,t=self.create();self.assertEqual(self.task(r,t,'done',response='no suggestions')[0],400)
        d=self.diagnosis(r)
        self.assertEqual(d['tasks'][0]['status'],'queued')
        self.assertFalse(any(e['stage']=='result_save' and e['status']=='ok' for e in d['events']))

    def test_invalid_payload_has_correlatable_structured_error(self):
        r,t=self.create()
        status,error=self.task(r,t,'failed',diagnostic=dict(code='made_up',stage='page_open'))
        self.assertEqual(status,400);self.assertEqual(error['diagnostic']['code'],'GEO_API_INVALID')
        self.assertTrue(any(e['request_id']==error['request_id'] for e in self.diagnosis(r)['events']))

    def test_report_retry_clears_active_error(self):
        r,t=self.create()
        with server.connect() as c:
            run=server.read(c,r);run['status']='completed';run['report_diagnostic']=diag.normalize(dict(code='GEO_REPORT_FAILED',stage='report_generate'))
            c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(run),r))
        self.assertEqual(self.request('runs/'+r+'/report')[0],200)
        self.assertNotIn('report_diagnostic',self.request('runs/'+r)[1])

    def test_commit_failure_cannot_be_reported_as_success(self):
        r,t=self.create()
        connect=server.connect
        class CommitFailure:
            def __init__(self):self.c=connect()
            def __enter__(self):return self
            def __exit__(self,*args):self.c.rollback();self.c.close()
            def execute(self,*args):return self.c.execute(*args)
            def commit(self):raise sqlite3.OperationalError('disk full')
        with patch.object(server,'connect',CommitFailure):
            status,error=self.task(r,t,'running')
        self.assertEqual(status,500);self.assertEqual(error['diagnostic']['code'],'GEO_WRITE_FAILED')
        self.assertEqual(self.diagnosis(r)['tasks'][0]['status'],'queued')

    def test_offline_export_reads_saved_events_without_starting_service(self):
        import urllib.error
        r,t=self.create();self.task(r,t,'failed',notice='缺少真实工具错误')
        c=server.connect()
        original_is_file=Path.is_file
        output=io.StringIO()
        with patch.object(sys,'argv',['workbench.py','diagnose','--run',r,'--output','-']),patch('urllib.request.urlopen',side_effect=urllib.error.URLError('connection refused')),patch('sqlite3.connect',return_value=c) as connection,patch.object(Path,'is_file',lambda p:True if p.name=='workbench.db' else original_is_file(p)),contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/workbench.py'),run_name='__main__')
        result=json.loads(output.getvalue())
        self.assertTrue(result['offline']);self.assertEqual(result['run_id'],r)
        self.assertIn('GEO_UNKNOWN',result['summary']);self.assertTrue(result['events'])
        self.assertIn('mode=ro',connection.call_args.args[0])
        self.assertNotIn('ExampleProduct',output.getvalue())

    def test_main_questions_are_user_input_independent_of_searches(self):
        qs=['常规的定制问题是什么？','ExampleProduct 的相关问题？']
        status,r=self.request('runs',dict(product='ExampleProduct',keyword='种子词',questions=qs,searches=['小红书','抖音'],ais=['豆包','DeepSeek']))
        self.assertEqual(status,201);self.assertEqual(r['questions'],qs);self.assertEqual(r['question_source'],'user')
        searches=[t for t in r['tasks'] if t['kind']=='search']
        self.assertTrue(all(t['question']=='种子词' and t['status']=='queued' for t in searches))
        for platform in r['ais']:
            self.assertEqual([t['question'] for t in r['tasks'] if t['kind']=='answer' and t['platform']==platform],qs)
        clarifications=[t for t in r['tasks'] if t['kind']=='clarification']
        self.assertEqual(len(clarifications),2);self.assertTrue(all(t['platform'] in r['ais'] for t in clarifications))
        self.assertTrue(all(qs[0] in t['question'] for t in clarifications))
        self.task(r['id'],searches[0]['id'],'needs_user',notice='等待处理搜索平台')
        answer=next(t for t in r['tasks'] if t['kind']=='answer')
        self.assertEqual(self.task(r['id'],answer['id'],'running')[0],200)
        self.assertEqual(self.task(r['id'],answer['id'],'done',response='AI 的真实回答')[0],200)
        saved=self.request('runs/'+r['id'])[1]
        self.assertEqual(saved['questions'],qs);self.assertEqual(saved['keyword'],'种子词')
        self.assertEqual([t['status'] for t in saved['tasks'] if t['kind']=='search'],['needs_user','queued'])

    def test_question_count_is_variable_and_invalid_input_creates_no_task(self):
        for qs in (['只问一个问题？'],['q1','q2','q3','q4']):
            status,r=self.request('runs',dict(product='p',keyword='k',questions=qs,searches=['百度'],ais=['豆包']))
            self.assertEqual(status,201);self.assertEqual(len(r['tasks']),1+len(qs)+1)
        existing=len(self.request('runs')[1])
        for qs in (None,[],[' '],['重复','重复'],['q']*21,['x'*4001],'不是数组'):
            status,_=self.request('runs',dict(product='p',keyword='k',questions=qs,searches=['百度'],ais=['豆包']))
            self.assertEqual(status,400)
        self.assertEqual(len(self.request('runs')[1]),existing)

    def test_legacy_task_accepts_manual_questions_before_search_done(self):
        r,t=self.create()
        with server.connect() as c:
            run=server.read(c,r);run['questions']=[];run.pop('question_source');run.pop('input_schema')
            run['tasks']=[x for x in run['tasks'] if x['kind']=='search']
            c.execute('UPDATE runs SET body=? WHERE id=?',(json.dumps(run),r))
        status,saved=self.request('runs/'+r+'/questions',dict(questions=['用户指定的问题？']))
        self.assertEqual(status,200);self.assertEqual(saved['question_source'],'user')
        self.assertEqual(saved['tasks'][0]['status'],'queued');self.assertEqual(len(saved['tasks']),3)
        self.assertEqual(self.request('runs/'+r+'/questions',dict(questions=['不覆盖现有任务']))[0],400)

    def test_report_separates_main_questions_from_search_suggestions(self):
        import report
        r,t=self.create();self.task(r,t,'done',response='已读取搜索下拉',suggestions=['q1','联想问题'])
        run=self.request('runs/'+r)[1]
        html=report.render(run)
        self.assertIn('来源：用户自行填写，仅用于 AI 平台；不由搜索联想生成。',html)
        self.assertNotIn('原文匹配来源',html);self.assertNotIn('从搜索联想，到入口问题',html)
        self.assertIn('搜索平台：关键词与真实联想',html)
        self.assertIn('AI 平台：主设问',html)
        run.pop('question_source')
        self.assertIn('历史记录未保存主设问的输入来源',report.render(run))

    def test_no_runs_has_online_service_diagnostics_without_false_failure(self):
        status,result=self.request('diagnostics')
        self.assertEqual(status,200);self.assertTrue(result['service']['online'])
        self.assertNotIn('service_error',result);self.assertEqual(result['events'],[])
        self.assertIsNone(result['last_successful_step']);self.assertTrue(result['service_events'])
        output=io.StringIO()
        def online(url,**kwargs):
            data=[] if str(url).endswith('/runs') else result
            return io.BytesIO(json.dumps(data).encode())
        with patch.object(sys,'argv',['workbench.py','diagnose','--output','-']),patch('urllib.request.urlopen',side_effect=online),contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/workbench.py'),run_name='__main__')
        exported=json.loads(output.getvalue())
        self.assertTrue(exported['service']['online']);self.assertNotIn('offline',exported)
        self.assertNotIn('service_error',exported)

    def test_prepare_returns_background_launcher_without_starting_it(self):
        import urllib.error
        output=io.StringIO()
        with patch.object(sys,'argv',['workbench.py','prepare']),patch('urllib.request.urlopen',side_effect=urllib.error.URLError('refused')),patch('subprocess.run') as launch,contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/workbench.py'),run_name='__main__')
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'needs_start');self.assertEqual(result['command'][-1],'start')
        self.assertEqual(len(result['log_files']),2);launch.assert_not_called()

    def test_start_reuses_service_instead_of_launching_duplicate(self):
        output=io.StringIO()
        config=dict(version=diag.VERSION,runner=dict(mode='current-chat'))
        with patch.object(sys,'argv',['workbench.py','start']),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(config).encode())),patch('subprocess.run') as launch,patch('subprocess.Popen') as detached,contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/workbench.py'),run_name='__main__')
        result=json.loads(output.getvalue())
        self.assertEqual(result['status'],'ready');self.assertTrue(result['reused'])
        launch.assert_not_called();detached.assert_not_called()

    def test_macos_start_uses_launchd_and_persists_log_paths(self):
        import urllib.error
        output=io.StringIO()
        config=dict(version=diag.VERSION,runner=dict(mode='current-chat'))
        absent=subprocess.CompletedProcess([],1,'','not found')
        submitted=subprocess.CompletedProcess([],0,'','')
        with patch.object(sys,'argv',['workbench.py','start']),patch.object(sys,'platform','darwin'),patch('os.getuid',return_value=501),patch('urllib.request.urlopen',side_effect=[urllib.error.URLError('refused'),io.BytesIO(json.dumps(config).encode())]),patch.object(Path,'mkdir'),patch('subprocess.run',side_effect=[absent,submitted]) as launch,contextlib.redirect_stdout(output):
            runpy.run_path(str(ROOT/'scripts/workbench.py'),run_name='__main__')
        result=json.loads(output.getvalue())
        self.assertEqual(result['launch_mode'],'macos-launchd')
        command=launch.call_args.args[0]
        self.assertEqual(command[:2],['launchctl','submit'])
        self.assertIn(str(ROOT/'assets/workbench/data/service.stderr.log'),command)
        self.assertIn('-B',command)


class SanitizationTests(unittest.TestCase):
    def test_service_log_tails_are_bounded_and_redacted(self):
        text='Cookie: privatecookie\nhttps://example.com/private?token=private-url\naccess_token=private-token\n'
        with patch.object(Path,'open',side_effect=lambda *args,**kw:io.BytesIO((text*1000).encode())):
            result=diag.service_output(ROOT/'assets/workbench')
        raw=json.dumps(result)
        self.assertNotIn('privatecookie',raw);self.assertNotIn('private-token',raw);self.assertNotIn('private-url',raw)
        self.assertTrue(result['service.stdout.log']['truncated'])
        self.assertLessEqual(len(result['service.stdout.log']['tail']),8000)
    def test_credential_forms_and_urls_are_redacted(self):
        value='Cookie: SID=privatecookie\nAuthorization: Bearer privatebearer\n{"cookie":"jsoncookie","access_token":"jsontoken","password":"jsonpass"}\nhttps://user:pass@example.com/session/private?token=urltoken#secret\n/Users/alice/private bob@example.com'
        cleaned=diag.clean(value)
        for secret in ('privatecookie','privatebearer','jsoncookie','jsontoken','jsonpass','urltoken','alice','bob@example.com','user:pass','/session/private'):
            self.assertNotIn(secret,cleaned)

    def test_diagnostics_reject_unknown_fields_and_bound_error_size(self):
        result=diag.normalize(dict(error_message='x'*20000,cookie='should never export',response='private answer',code='GEO_UNKNOWN'))
        self.assertNotIn('cookie',result);self.assertNotIn('response',result)
        self.assertLessEqual(len(result['error_message']),4000)

    def test_pre_diagnostics_database_is_readable_without_migration(self):
        c=sqlite3.connect(':memory:')
        try:
            bundle=diag.bundle(c,dict(id='old',status='failed',tasks=[dict(id='t',platform='快手',status='failed',notice='旧错误')]),ROOT/'assets/workbench')
            self.assertEqual(bundle['events'],[]);self.assertEqual(bundle['current_failures'][0]['diagnostic']['code'],'GEO_UNKNOWN')
        finally:c.close()

    def test_frontend_javascript_syntax(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        html=(ROOT/'assets/workbench/index.html').read_text()
        code=html.split('<script>',1)[1].split('</script>',1)[0]
        result=subprocess.run([node,'--check','-'],input=code,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()

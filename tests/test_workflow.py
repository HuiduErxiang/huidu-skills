"""Exercise independent search/AI queues over real HTTP with an in-memory database."""
import io
import json
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
import server
import diagnostics
from report import render


class MemoryReport:
 def __init__(self,html):self.html=html
 def read_text(self):return self.html


class Workflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.uri='file:geo-http-'+str(uuid.uuid4())+'?mode=memory&cache=shared'
  cls.anchor=sqlite3.connect(cls.uri,uri=True)
  def connect():
   c=sqlite3.connect(cls.uri,uri=True);c.row_factory=sqlite3.Row;return c
  cls.connect_patch=patch.object(server,'connect',connect);cls.connect_patch.start()
  cls.reports={}
  def write_report(run,directory):
   output=MemoryReport(render(run));cls.reports[run['id']]=output;return output
  cls.report_patch=patch.object(server,'write_report',write_report);cls.report_patch.start()
  with connect() as c:
   c.execute('CREATE TABLE runs(id TEXT PRIMARY KEY,body TEXT)');diagnostics.init(c)
  cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
  cls.base='http://127.0.0.1:'+str(cls.http.server_port)
  cls.worker=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.worker.start()

 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.worker.join()
  cls.report_patch.stop();cls.connect_patch.stop();cls.anchor.close()

 def request(self,path,data=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)

 def test_full_workflow(self):
  qs=['用户主设问甲','用户主设问乙','用户主设问丙']
  r=self.request('/api/runs',dict(product='测试产品',keyword='搜索关键词',questions=qs,searches=server.SEARCH,ais=server.AI))
  base='/api/runs/'+r['id'];self.assertEqual(len(r['tasks']),24)
  self.assertEqual(r['questions'],qs);self.assertEqual(r['question_source'],'user')
  with self.assertRaises(urllib.error.HTTPError):self.request(base+'/questions',{'questions':['不能覆盖已有问题']})
  t=r['tasks'][0]
  r=self.request(base+'/task',dict(task_id=t['id'],status='needs_user',notice='页面要求用户操作'))
  self.assertEqual(r['status'],'needs_user')
  # An AI answer is allowed while a search platform is awaiting user action.
  answer=next(x for x in r['tasks'] if x['kind']=='answer')
  r=self.request(base+'/task',dict(task_id=answer['id'],status='done',response='测试产品'))
  self.assertEqual(r['tasks'][0]['status'],'needs_user')
  self.assertTrue(any(x['id']==answer['id'] and x['status']=='done' for x in r['tasks']))
  r=self.request(base+'/control',{'action':'resume'});self.assertEqual(r['tasks'][0]['status'],'queued')
  r=self.request(base+'/control',{'action':'pause'})
  with self.assertRaises(urllib.error.HTTPError):self.request(base+'/task',dict(task_id=t['id'],status='running'))
  r=self.request(base+'/control',{'action':'resume'})
  for search in [x for x in r['tasks'] if x['kind']=='search']:
   r=self.request(base+'/task',dict(task_id=search['id'],status='done',response='真实接口测试记录',suggestions=['搜索联想甲','搜索联想乙']))
  self.assertEqual(r['status'],'running');self.assertEqual(r['questions'],qs)
  for t in [x for x in r['tasks'] if x['kind']!='search' and x['status']!='done']:
   response='测试产品' if t['question']==qs[0] else '普通回答'
   if t['kind']=='clarification':response='1. 第一个澄清问题？\n2. 第二个澄清问题？\n3. 第三个澄清问题？'
   r=self.request(base+'/task',dict(task_id=t['id'],status='done',response=response))
  self.assertEqual(r['status'],'completed');self.assertEqual(sum(t['mentions'] is True for t in r['tasks']),5)
  self.assertEqual(self.request(base+'/export')['status'],'completed')
  with urllib.request.urlopen(self.base+base+'/report') as response:
   self.assertIn('text/html',response.headers['Content-Type']);html=response.read().decode()
   self.assertIn('AI 追问树',html);self.assertIn('来源：用户自行填写',html)
  with urllib.request.urlopen(self.base+base+'/report/download') as response:self.assertIn('attachment',response.headers['Content-Disposition'])
  with urllib.request.urlopen(self.base+base+'/diagnostics/download') as response:
   self.assertIn('attachment',response.headers['Content-Disposition']);diagnosis=json.load(response)
   self.assertEqual(diagnosis['run_status'],'completed');self.assertTrue(diagnosis['events'])
  self.assertIn(r['id'],self.reports)

 def test_no_empty_completion(self):
  r=self.request('/api/runs',dict(product='产品',keyword='关键词',questions=['用户指定的问题'],searches=['百度'],ais=['豆包']))
  with self.assertRaises(urllib.error.HTTPError):self.request('/api/runs/'+r['id']+'/task',dict(task_id=r['tasks'][0]['id'],status='done',response=''))


if __name__=='__main__':unittest.main()

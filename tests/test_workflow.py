"""Exercise queue transitions over real HTTP against an isolated temporary database."""
import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
import server
class Workflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();server.ROOT=Path(cls.temp.name);server.DB=server.ROOT/'test.db';server.init();cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.base='http://127.0.0.1:'+str(cls.http.server_port);threading.Thread(target=cls.http.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
 def request(self,path,data=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def test_full_workflow(self):
  r=self.request('/api/runs',dict(product='测试产品',keyword='测试关键词',searches=server.SEARCH,ais=server.AI));base='/api/runs/'+r['id'];self.assertEqual(len(r['tasks']),4)
  with self.assertRaises(urllib.error.HTTPError):self.request(base+'/questions',{'questions':['甲','乙','丙']})
  t=r['tasks'][0];r=self.request(base+'/task',dict(task_id=t['id'],status='needs_user',notice='请登录'));self.assertEqual(r['status'],'needs_user')
  r=self.request(base+'/control',{'action':'resume'});self.assertEqual(r['tasks'][0]['status'],'queued')
  r=self.request(base+'/control',{'action':'pause'})
  with self.assertRaises(urllib.error.HTTPError):self.request(base+'/task',dict(task_id=t['id'],status='running'))
  self.request(base+'/control',{'action':'resume'})
  for t in r['tasks']:r=self.request(base+'/task',dict(task_id=t['id'],status='done',response='真实接口测试记录',suggestions=['甲','乙','丙']))
  self.assertEqual(r['status'],'select_questions');r=self.request(base+'/questions',{'questions':['甲','乙','丙']});self.assertEqual(len(r['tasks']),24)
  for t in r['tasks'][4:]:r=self.request(base+'/task',dict(task_id=t['id'],status='done',response='测试产品' if t['question']=='甲' else '普通回答'))
  self.assertEqual(r['status'],'completed');self.assertEqual(sum(t['mentions'] is True for t in r['tasks']),5);self.assertEqual(self.request(base+'/export')['status'],'completed')
  with urllib.request.urlopen(self.base+base+'/report') as response:
   self.assertIn('text/html',response.headers['Content-Type']);self.assertIn('AI 追问树',response.read().decode())
  with urllib.request.urlopen(self.base+base+'/report/download') as response:self.assertIn('attachment',response.headers['Content-Disposition'])
  self.assertTrue((server.ROOT/'data/reports'/(r['id']+'.html')).exists())
 def test_no_empty_completion(self):
  r=self.request('/api/runs',dict(product='产品',keyword='关键词',searches=['百度'],ais=['豆包']))
  with self.assertRaises(urllib.error.HTTPError):self.request('/api/runs/'+r['id']+'/task',dict(task_id=r['tasks'][0]['id'],status='done',response=''))
if __name__=='__main__':unittest.main()

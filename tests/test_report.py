import unittest
from copy import deepcopy
from report import render,questions,theme_questions
class ReportTests(unittest.TestCase):
 def sample(self):
  return dict(id='test',product='目标<script>alert(1)</script>',keyword='关键词',created='2026-11-15',status='completed',searches=['百度'],ais=['豆包','DeepSeek'],questions=['问题甲','问题乙','问题丙'],suggestions=[dict(platform='百度',text='原始联想',rank=1)],tasks=[dict(kind='answer',platform='豆包',question='问题甲',status='done',response='目标<script>alert(1)</script>'),dict(kind='clarification',platform='豆包',status='done',response='1. 入睡困难还是早醒？\n2. 持续多久？\n3. 是否正在服用其他药物？')])
 def test_data_and_escaping(self):
  r=self.sample();h=render(r)
  self.assertIn('目标&lt;script&gt;alert(1)&lt;/script&gt;',h);self.assertNotIn('<script>alert(1)</script>',h)
  self.assertIn('本轮完成 1 / 6 份计划回答，其中 1 份',h)
  self.assertIn('尚未采集到澄清问题',h);self.assertIn('待采集',h)
  self.assertIn('本轮只采一层',h);self.assertEqual(h.count('<small>第一层 · '),3)
  self.assertIn('规则归类 · 可复核',h);self.assertIn('推演内容 · 待验证',h)
 def test_complete_flag_does_not_hide_unfinished(self):
  r=self.sample();r['tasks'].append(dict(kind='answer',platform='DeepSeek',question='问题乙',status='queued'))
  self.assertIn('未完成报告',render(r))
 def test_original_questions_preserved(self):
  self.assertEqual(questions('1. 第一个？\n2、第二个？\n3. 第三个\n本回答由AI生成'),['第一个？','第二个？','第三个'])
 def test_other_medications_not_treatment_stage(self):
  themes=theme_questions(['是否有其他基础疾病或者正在服用别的药物？'])
  self.assertTrue(themes['其他用药']);self.assertFalse(themes['用药阶段与处方'])
 def test_single_platform_no_comparison_claim(self):
  r=self.sample();r['ais']=['豆包'];self.assertIn('本轮只有一个 AI，不作跨平台差异结论',render(r))
if __name__=='__main__':unittest.main()

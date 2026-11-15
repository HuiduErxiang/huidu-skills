"""Standalone evidence-first HTML reports, generated from one research run."""
from html import escape
from pathlib import Path
from datetime import datetime
import re

def e(value):return escape(str(value if value is not None else ''),quote=True)
THEMES=[('睡眠困扰类型',r'入睡|半夜|夜间|早醒|多梦|睡眠浅'),('持续时间',r'多久|持续|几天|几周|个月|数周'),('其他疾病与身体情况',r'疾病|基础病|基础疾病|肝|肾|呼吸|心脏|怀孕|哺乳|备孕'),('其他用药',r'服用|服药|药物|别的药|其他药'),('用药阶段与处方',r'处方|用药阶段|已经开始|尚未开始|考虑使用|(?:服用|使用).{0,8}(?:多久|多长时间)|医生.{0,6}开'),('信息意图与比较',r'想了解|想知道|关心|比较|对比|疗效|副作用')]
INFER={
 '睡眠困扰类型':('我主要是入睡困难，应该先了解哪些处理方式？','入睡困难、夜间易醒和早醒，咨询时需要分别提供哪些信息？'),
 '持续时间':('睡眠困扰持续多久，应该考虑就医评估？','我该怎样记录睡眠问题的频率和持续时间？'),
 '其他疾病与身体情况':('咨询失眠问题时，需要说明哪些已有疾病和身体情况？','如果同时存在其他健康问题，应该向医生补充什么信息？'),
 '其他用药':('咨询睡眠问题时，需要提供正在使用的哪些药物？','我该如何向医生或药师核对助眠药与其他药物的相互作用？'),
 '用药阶段与处方':('尚未使用和已经使用助眠药，咨询时需要提供的信息有什么不同？','就诊时应该怎样讨论处方和后续随访？'),
 '信息意图与比较':('比较不同处理方式时，应该关注哪些信息？','我该怎样向医生说明最关心的效果和使用顾虑？')}

def questions(text):
 """Extract line-based original questions; never invent missing branches."""
 result=[]
 for line in text.splitlines():
  line=line.strip()
  if not line:continue
  # Legacy imported AX text sometimes includes search/UI metadata.
  if line.startswith(('本回答由','内容由 AI','下载豆包','推荐一些','深度思考','智能搜索')):break
  line=re.sub(r'^\s*(?:[-*•]|\d+[.、)）])\s*','',line)
  result.append(line)
 return result

def theme_questions(items):
 return {name:[q for q in items if re.search(pattern,q)] for name,pattern in THEMES}

def render(r):
 product=r.get('product','');keyword=r.get('keyword','');ais=r.get('ais',[]);tasks=r.get('tasks',[]);sources=r.get('suggestions',[]);roots=r.get('questions',[])
 answers=[t for t in tasks if t.get('kind')=='answer' and t.get('status')=='done'];clarifications=[t for t in tasks if t.get('kind')=='clarification' and t.get('status')=='done']
 tree={p:[] for p in ais};themes={}
 for p in ais:
  for t in clarifications:
   if t['platform']==p:tree[p]+=questions(t.get('response',''))
  themes[p]=theme_questions(tree[p])
 total_questions=sum(map(len,tree.values()));mentions=sum(bool(product) and product in t.get('response','') for t in answers)
 expected_answers=len(ais)*len(roots);complete=r.get('status')=='completed' and all(t.get('status')=='done' for t in tasks)
 parts=[]
 def add(s):parts.append(s)
 add('''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+e(product)+'''｜GEO 搜索联想、AI 追问与可见度报告</title><style>
:root{--ink:#193238;--muted:#62777a;--line:#dce7e4;--paper:#f5f8f6;--deep:#123338;--teal:#0b766f}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.75 -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}.wrap{max-width:1240px;margin:auto;padding:0 28px}.hero{background:radial-gradient(circle at 85% 10%,#205f5c,transparent 35%),linear-gradient(125deg,#113339,#1b5350);color:#f6fbf8;padding:64px 0 50px}.eyebrow{color:#a9d8c8;letter-spacing:2px;font-size:12px}.hero h1{font-size:clamp(32px,5vw,54px);line-height:1.3;margin:18px 0;letter-spacing:-1px}.hero p{max-width:850px;color:#d2e8e2}.stats{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.stat{border:1px solid #ffffff30;background:#ffffff0a;border-radius:14px;padding:12px 20px;min-width:130px}.stat b{display:block;font-size:27px}.stat span{color:#c4e1d7;font-size:12px}.nav{background:#fff;position:sticky;top:0;z-index:10;border-bottom:1px solid var(--line)}.nav .wrap{display:flex;gap:23px;overflow:auto;white-space:nowrap;align-items:center}.nav a{padding:15px 0;text-decoration:none;color:#4c696a;font-size:12px;font-weight:700}main{padding:40px 0}section{scroll-margin-top:75px;margin-bottom:48px}.head{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:20px}.head h2{font-size:28px;line-height:1.4;margin:4px 0}.kicker{font-size:11px;letter-spacing:2px;color:var(--teal);font-weight:800}.muted{color:var(--muted)}.badge{background:#e5f4ed;color:#0b665d;border-radius:30px;padding:4px 11px;font-size:11px;white-space:nowrap}.notice{background:#fff6e8;border:1px solid #ecd7b7;border-radius:13px;padding:15px 19px;color:#71572e;font-size:12px;margin:18px 0}.panel,.platform,.insight{background:#fff;border:1px solid var(--line);border-radius:20px;padding:24px;box-shadow:0 10px 25px #1b3d3d06}.platform{margin-top:18px}.platform h3{font-size:23px;margin:0}.platform-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.root{max-width:650px;margin:22px auto 30px;background:var(--deep);color:white;text-align:center;border-radius:14px;padding:17px}.root small{display:block;color:#a6d7ca;font-size:11px}.branches{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px;border-top:2px solid #bed4cc;padding-top:22px}.branch{border:1px solid #d5e5e0;border-radius:15px;padding:18px;background:#fafcfb;position:relative;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}.branch:before{content:'';height:22px;width:2px;background:#bed4cc;position:absolute;bottom:100%;left:50%}.branch small{display:block;font-size:10px;color:var(--teal);font-weight:800;margin-bottom:9px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.tab,button{font:inherit;border:1px solid #d6e3df;background:#fff;border-radius:30px;padding:8px 16px;color:#41605f;cursor:pointer}.tab[aria-selected=true]{background:var(--deep);color:#fff}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.insight h3{margin:7px 0 10px;font-size:17px}.number{color:#ab925c;font-size:11px;letter-spacing:1px}.evidence{font-size:12px;color:#2d625e;border-top:1px solid #e9efed;margin-top:15px;padding-top:12px;white-space:pre-wrap}.matrix-wrap{overflow:auto;border:1px solid var(--line);border-radius:16px;background:#fff}.matrix{border-collapse:collapse;width:100%;font-size:12px}.matrix th,.matrix td{padding:13px;text-align:left;border-bottom:1px solid #edf2f0;vertical-align:top}.matrix th{background:#eaf3ee}.yes{color:#08796b;font-weight:750}.no{color:#7c8984}.question-list{margin:0;padding-left:21px}.question-list li{padding:6px 0;overflow-wrap:anywhere}.source{font-size:11px;color:#78908c;margin:14px 0 0}.answer{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.9 inherit;background:#fafcf9;border:1px solid #e5ece6;border-radius:12px;padding:18px;max-height:550px;overflow:auto}summary{cursor:pointer;font-weight:650;padding:13px 0}details+details{border-top:1px solid var(--line)}.footer{background:var(--deep);color:#cbe4dd;padding:25px 0;font-size:12px}.empty{padding:24px;color:var(--muted)}[hidden]{display:none!important}@media(max-width:800px){.grid,.grid.two,.branches{grid-template-columns:1fr}.branches{border-top:0;padding-top:0}.branch:before{display:none}.head{display:block}.wrap{padding:0 17px}.hero{padding:40px 0}.panel,.platform,.insight{padding:18px}}@media print{.nav,.tabs,.print{display:none}.hero{padding:25px 0}.platform,.insight{break-inside:avoid}body{background:#fff}.answer{max-height:none;overflow:visible}.wrap{max-width:none}details{break-inside:avoid}}
</style></head><body>''')
 add(f'<header class="hero"><div class="wrap"><div class="eyebrow">GEO RESEARCH · {e(r.get("created","")[:10])}</div><h1>{e(product)}：<br>搜索联想、AI 追问与产品可见度</h1><p>从“{e(keyword)}”出发，连接传统搜索平台的真实联想、{len(roots)} 个入口问题和多 AI 的实际回答。以下统计仅描述本次采集，推演问题单独标记。</p><div class="stats">')
 for n,label in [(len(r.get('searches',[])),'搜索平台'),(len(sources),'条真实搜索联想'),(len(ais),'个 AI 平台'),(len(answers),'份实际回答'),(total_questions,'条 AI 澄清问题')]:add(f'<div class="stat"><b>{n}</b><span>{label}</span></div>')
 add('</div></div></header><nav class="nav"><div class="wrap">')
 for anchor,label in [('sources','搜索来源'),('visibility','产品可见度'),('trees','AI 追问树'),('patterns','共性与异同'),('inference','用户问题推演'),('original','完整回答'),('method','口径与限制')]:add(f'<a href="#{anchor}">{label}</a>')
 add('<button class="print" type="button" onclick="window.print()">打印 / 保存 PDF</button></div></nav><main class="wrap">')
 def head(anchor,num,title,sub,badge):
  add(f'<section id="{anchor}"><div class="head"><div><div class="kicker">{num} / GEO OBSERVATIONS</div><h2>{title}</h2><div class="muted">{sub}</div></div><span class="badge">{badge}</span></div>')
 head('sources','01','从搜索联想，到入口问题','原始表达保留平台、顺序、时间和采集方式；重复出现不等于搜索热度。','真实采集')
 if not complete:add('<div class="notice"><b>未完成报告：</b>本任务仍有未完成步骤。以下缺失结果标记为“待采集”，不记为“未提及”。</div>')
 add('<div class="grid two">')
 for platform in r.get('searches',[]):
  items=[v for v in sources if v.get('platform')==platform]
  add(f'<article class="panel"><h3>{e(platform)} <span class="badge">{len(items)} 条</span></h3><ol class="question-list">')
  for v in items:add(f'<li>{e(v.get("text",""))}</li>')
  if not items:add('<li>尚未采到真实联想</li>')
  method=next((t.get('response','').splitlines()[0] for t in tasks if t.get('kind')=='search' and t['platform']==platform and t.get('status')=='done'),'采集方式未记录')
  add(f'</ol><p class="source">{e(method)}<br>采集时间：{e(items[0].get("collected_at","未记录") if items else "待采集")}</p></article>')
 add('</div><div class="panel" style="margin-top:18px"><h3>本轮入口问题</h3><ol class="question-list">')
 for q in roots:
  normalized=lambda s:re.sub(r'[？?\s]','',s)
  exact=[v['platform'] for v in sources if normalized(v.get('text',''))==normalized(q)]
  add(f'<li><b>{e(q)}</b><div class="source">原文匹配来源：{e("、".join(dict.fromkeys(exact)) or "无原文完全匹配；由整理步骤选定，需结合原始联想复核")}</div></li>')
 add('</ol></div></section>')
 head('visibility','02','产品在实际回答中如何出现','按完整回答正文中的目标产品精确文本统计，排除侧栏、历史聊天和输入提示词。','实际回答')
 add(f'<div class="notice">本轮完成 {len(answers)} / {expected_answers} 份计划回答，其中 {mentions} 份提及“{e(product)}”。这是样本计数，不是平台长期提及概率；提及也不等于推荐。</div><div class="matrix-wrap"><table class="matrix"><thead><tr><th>入口问题</th>')
 for p in ais:add(f'<th>{e(p)}</th>')
 add('</tr></thead><tbody>')
 for q in roots:
  add(f'<tr><td>{e(q)}</td>')
  for p in ais:
   t=next((t for t in answers if t['platform']==p and t.get('question')==q),None)
   add('<td class="no">待采集</td>' if t is None else ('<td class="yes">● 提及</td>' if product and product in t.get('response','') else '<td class="no">— 未提及</td>'))
  add('</tr>')
 add('</tbody></table></div><div class="grid two" style="margin-top:18px">')
 for p in ais:
  contexts=[]
  for t in answers:
   if t['platform']==p and product and product in t.get('response',''):
    text=t['response'];i=text.index(product);contexts.append((t.get('question',''),text[max(0,i-60):min(len(text),i+len(product)+100)]))
  add(f'<article class="insight"><h3>{e(p)} · 提及上下文</h3>')
  for q,text in contexts:add(f'<p class="muted">入口：{e(q)}</p><div class="evidence">…{e(text)}…</div>')
  if not contexts:add('<p class="muted">本轮已采集回答中未发现目标产品精确文本；如存在待采集项，不能据此断言全部回答均未提及。</p>')
  add('</article>')
 add('</div></section>')
 head('trees','03','各平台的 AI 追问树','根节点是用户入口；分支是 AI 向用户提出的澄清问题。本轮只采一层，按实际数量展示。','原始问题')
 add('<div class="notice">与参考示例的二层三叉树不同，本轮按约定控制为一层追问。没有采集的第二层不补写。其他两个入口的实际回答见“完整回答”。</div><div class="tabs" role="tablist" aria-label="AI 平台筛选"><button class="tab" role="tab" aria-selected="true" data-filter="all">全部</button>')
 for i,p in enumerate(ais):add(f'<button class="tab" role="tab" aria-selected="false" data-filter="p{i}">{e(p)}</button>')
 add('</div>')
 for i,p in enumerate(ais):
  qs=tree[p];add(f'<article class="platform" data-platform="p{i}"><div class="platform-head"><h3>{e(p)}</h3><span class="badge">{len(qs)} 条实际澄清问题</span></div><div class="root"><small>用户入口 / ROOT</small><b>{e(roots[0] if roots else "尚未选定入口")}</b></div><div class="branches">')
  for j,q in enumerate(qs):add(f'<div class="branch"><small>第一层 · {j+1:02d}</small>{e(q)}</div>')
  if not qs:add('<div class="empty">尚未采集到澄清问题</div>')
  add('</div><p class="source">AI 向用户反问；按固定提示词生成，不代表自然会话频次或真实用户需求量。</p></article>')
 add('</section>')
 head('patterns','04','共性与异同：先澄清什么，再补充什么','以下按原始问句的显式词语归类。主题可以重叠，主题覆盖表示有无出现，不是流量或重要性排名。','规则归类 · 可复核')
 add('<div class="matrix-wrap"><table class="matrix"><thead><tr><th>澄清主题</th>')
 for p in ais:add(f'<th>{e(p)}</th>')
 add('</tr></thead><tbody>')
 for name,_ in THEMES:
  add(f'<tr><td>{name}</td>')
  for p in ais:add('<td>待采集</td>' if not tree[p] else ('<td class="yes">●</td>' if themes[p][name] else '<td class="no">—</td>'))
  add('</tr>')
 add('</tbody></table></div><div class="grid" style="margin-top:18px">')
 common=[name for name,_ in THEMES if ais and all(tree[p] and themes[p][name] for p in ais)]
 if not common:add('<article class="insight"><h3>暂未形成共同主题结论</h3><p class="muted">可能是样本未完成、样本太少，或本轮显式问法不同。</p></article>')
 for i,name in enumerate(common):
  add(f'<article class="insight"><span class="number">PATTERN {i+1:02d}</span><h3>共同询问：{name}</h3><p class="muted">本轮各 AI 的原始澄清问句均涉及这一主题。</p>')
  for p in ais:add(f'<div class="evidence">{e(p)}：“{e(themes[p][name][0])}”</div>')
  add('</article>')
 add('</div><div class="grid two" style="margin-top:18px">')
 for p in ais:
  covered=[name for name,_ in THEMES if themes[p][name]];unique=[name for name in covered if all(not themes[other][name] for other in ais if other!=p)] if len(ais)>1 and all(tree[other] for other in ais) else []
  add(f'<article class="insight"><h3>{e(p)} · 本轮问法</h3><p>显式涉及：{e("、".join(covered) or "尚未识别到预设主题")}。</p><p class="muted">{e(("相对其他已选平台，本轮额外涉及："+"、".join(unique)) if unique else ("本轮没有观察到预设主题中的独有分支。" if len(ais)>1 else "本轮只有一个 AI，不作跨平台差异结论。"))}</p><div class="source">不据单轮固定提示词样本推断平台长期性格或稳定策略。未识别不等于主题必定不存在。</div></article>')
 add('</div></section>')
 head('inference','05','反推：用户可能怎样继续提问','以下为基于已采澄清主题映射的候选选题，属于待验证推演，不是平台实际生成的问题，也不是搜索量。','推演内容 · 待验证')
 observed=[name for name,_ in THEMES if any(themes[p][name] for p in ais)]
 add('<div class="grid two"><article class="panel"><h3>路径 A · 从症状或困扰出发</h3><ol class="question-list">')
 for name in observed:add(f'<li>{e(INFER[name][0])}<div class="source">推演依据：{name}</div></li>')
 if not observed:add('<li>尚无已采澄清主题，不生成候选追问。</li>')
 add('</ol></article><article class="panel"><h3>路径 B · 已经听说目标产品</h3><p class="muted">以下为产品入口内容假设，未在本轮提交测试。</p><ol class="question-list">')
 for name in observed:
  q=INFER[name][1]
  add(f'<li>我正在了解{e(product)}。{e(q)}<div class="source">推演依据：{name}；模板转换，需后续验证。</div></li>')
 if not observed:add('<li>尚无已采澄清主题，不生成候选追问。</li>')
 add('</ol></article></div></section>')
 head('original','06','完整回答与原始追问记录','折叠查看每次提交的实际正文。未核验回答中的医学说法，引用链接不做核验。','原始记录')
 add('<div class="panel">')
 for p in ais:
  add(f'<h3>{e(p)}</h3>')
  for t in tasks:
   if t.get('platform')!=p or t.get('kind') not in ('answer','clarification'):continue
   label='一层三问探索' if t['kind']=='clarification' else t.get('question','')
   status={'done':'已采集','queued':'待采集','running':'采集中','failed':'失败','needs_user':'等待操作'}.get(t.get('status'),t.get('status','未知'))
   add(f'<details><summary>{e(label)} · {e(status)}</summary><p class="source">模型：{e(t.get("visible_model") or "界面未记录")} ｜ 搜索状态：{e(t.get("web_search_state") or "未知")} ｜ 时间：{e(t.get("updated") or "未记录")}</p><div class="answer">{e(t.get("response") if t.get("status")=="done" else "尚无完整采集结果")}</div></details>')
 add('</div></section>')
 head('method','07','样本口径与使用边界','报告随任务真实数据生成，所有计数可回到原始记录核对。','研究说明')
 add('<div class="grid">')
 for title,text in [('固定规模',f'{len(roots)} 个入口 × {len(ais)} 个 AI；每个 AI 对第一个入口做一层澄清，不补写第二层。'),('采集完整性',f'任务状态：{"全部完成" if complete else "尚未全部完成"}。实际回答 {len(answers)}/{expected_answers}；实际澄清问题 {total_questions} 条。'),('来源差异','公开接口联想与登录网页下拉可能不同；不将平台排序、跨平台重复次数解释为搜索热度。'),('统计口径','只在已采回答正文查找目标产品精确文本；别名和英文名未自动计入。未采集不记为未提及。'),('归纳与推演','共性矩阵按显式词语规则归类，可能漏判；候选用户问题为主题模板推演，需要真实搜索或会话验证。'),('样本限制','独立会话仍可能受账号、模型、联网状态和时间影响。单轮结果不能证明平台的长期稳定表现。'),('内容边界','研究提问与产品出现方式，不提供个人用药建议；原始回答中的医学说法未核验。'),('引用链接','按研究要求不打开、不核验引用链接，不将引用存在等同于内容准确。'),('离线报告','此 HTML 内置样式和筛选脚本，不需要外部字体、网络资源或本地服务即可阅读。')]:add(f'<article class="insight"><h3>{title}</h3><p class="muted">{e(text)}</p></article>')
 add('</div></section></main><footer class="footer"><div class="wrap">'+e(product)+' · GEO 研究报告 ｜ 任务 '+e(r.get('id',''))+'<br>真实搜索联想、AI 原始问答与推演内容分开展示。</div></footer><script>document.querySelectorAll("[data-filter]").forEach(b=>b.addEventListener("click",()=>{const f=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.setAttribute("aria-selected",String(x===b)));document.querySelectorAll("[data-platform]").forEach(x=>x.hidden=f!=="all"&&x.dataset.platform!==f)}));window.addEventListener("beforeprint",()=>document.querySelectorAll("details").forEach(x=>{x.dataset.wasOpen=x.open?"yes":"no";x.open=true}));window.addEventListener("afterprint",()=>document.querySelectorAll("details").forEach(x=>x.open=x.dataset.wasOpen==="yes"));</script></body></html>')
 return ''.join(parts)

def write_report(r,directory):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 path=directory/(r['id']+'.html');temp=path.with_suffix('.html.tmp');temp.write_text(render(r),encoding='utf-8');temp.replace(path);return path

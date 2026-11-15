# Huidu Skills

可安装到 Codex 的技能集合。

## GEO 工作台

[技能入口](skills/geo-workbench/SKILL.md) · [平台实测记录](skills/geo-workbench/references/platforms.md)

从种子关键词采集搜索联想，确定 3 个入口问题，再采集多个 AI 的独立回答和一层三问，生成独立 HTML 报告。本地网页负责配置、进度和结果，实际浏览器操作由活跃的 Codex 聊天执行。

### 安装与使用

需要 Python 3.9+、Codex，以及可用的浏览器或 Computer Use 工具。

将 `skills/geo-workbench` 整个目录复制到 `~/.codex/skills/geo-workbench`。让 Codex 识别技能后，在聊天中说：

> 使用 GEO 技能，研究某产品，关键词是某关键词。

Codex 会准备并打开本地工作台。填写平台并点击“创建研究任务”；保持当前聊天运行，按网页提示完成必要登录，再继续采集。工作台只监听 `127.0.0.1:8790`。如聊天已经结束，需要回聊天说“继续研究”，网页不会自行运行后台代理。

研究数据保存在技能内 `assets/workbench/data/`，不进入本仓库。报告支持网页预览、下载和 JSON 导出。默认 3 个入口，每个 AI 3 次回答和 1 次三问提交。

### 平台与限制

支持配置抖音、快手、小红书、百度，以及豆包、DeepSeek、千问、元宝、ChatGPT。平台可选不等于采集已通过；详见带日期的实测记录。快手当前登录搜索正常，但尚未观察到搜索联想；千问本次失眠样本拒答；ChatGPT 尚待登录复测。

不把搜索结果标题冒充联想，不伪造数据；报告中的问题推演与实际采集分开。引用链接不做核验。医疗相关研究仅记录平台输出。

### 开发验证

```sh
PYTHONPATH=skills/geo-workbench/assets/workbench python3 -m unittest discover -s tests
```

工作台使用 Python 标准库，无需安装服务端依赖。

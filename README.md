# Huidu Skills

可安装到 Codex 的技能集合。

## GEO 工作台

[技能入口](skills/geo-workbench/SKILL.md) · [平台实测记录](skills/geo-workbench/references/platforms.md) · [故障排查与日志](skills/geo-workbench/references/troubleshooting.md)

提供两组独立输入：搜索/社交平台使用关键词采集下拉联想；AI 平台使用用户填写的主设问采集独立回答和一层三问。搜索联想不会自动成为 AI 主设问，两路任务不互为前置条件，最后生成独立 HTML 报告。本地网页负责配置、进度和结果，实际浏览器操作由活跃的 Codex 聊天执行。

### 安装与使用

需要 Python 3.9+、Codex，以及可用的浏览器或 Computer Use 工具。

将 `skills/geo-workbench` 整个目录复制到 `~/.codex/skills/geo-workbench`。让 Codex 识别技能后，在聊天中说：

> 使用 GEO 技能，研究某产品，关键词是某关键词。

Codex 会准备并打开本地工作台。分别填写关键词与 AI 主设问、选择平台并点击“创建研究任务”；保持当前聊天运行，按网页提示完成必要登录，再继续采集。工作台只监听 `127.0.0.1:8790`。如聊天已经结束，需要回聊天说“继续研究”，网页不会自行运行后台代理。

研究数据保存在技能内 `assets/workbench/data/`，不进入本仓库。报告支持网页预览、下载和 JSON 导出。主设问支持每行一条，共 1～20 条；每个 AI 回答全部主设问，并围绕第一个主设问做 1 次独立三问提交。

### 服务与诊断

当前版本 0.3.1。Codex 通过 `scripts/workbench.py prepare` 检查服务，需要启动时调用 `scripts/workbench.py start`。macOS 使用当前用户的 launchd 管理本地网页服务，其他系统使用独立进程；浏览器采集仍由当前活跃聊天执行。服务输出保存在 `assets/workbench/data/service.stdout.log` 和 `service.stderr.log`。

采集失败时，页面展示具体平台、步骤、真实报错、原因确认程度及恢复建议，并提供“复制排障信息”和“导出诊断日志”。服务不可连接时，可以运行 `scripts/workbench.py diagnose --run latest --output /绝对路径/diagnostics.json` 离线导出已有日志。未收到心跳不等于浏览器断开；没有研究任务也不会判为服务异常。诊断日志不自动上传。

### 平台与限制

支持配置抖音、快手、小红书、百度，以及豆包、DeepSeek、千问、元宝、ChatGPT。平台可选不等于采集已通过；详见带日期的实测记录。快手当前登录搜索正常，但尚未观察到搜索联想；千问本次失眠样本拒答；ChatGPT 尚待登录复测。

不把搜索结果标题冒充联想，不伪造数据；报告中的问题推演与实际采集分开。引用链接不做核验。医疗相关研究仅记录平台输出。

### 开发验证

```sh
PYTHONPATH=skills/geo-workbench/assets/workbench python3 -B -m unittest discover -s tests
python3 -B -m unittest discover -s skills/geo-workbench/tests
```

工作台使用 Python 标准库，无需安装服务端依赖。

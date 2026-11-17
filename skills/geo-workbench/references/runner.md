# 本地执行协议

服务仅绑定127.0.0.1:8790，SQLite数据在data/workbench.db。HTTP GET /api/runs 返回完整研究任务，最新在前。所有POST使用Content-Type: application/json。

创建任务由网页完成。当前聊天收到开始/继续指令后读取最新未完成任务。只接手用户本次要求的任务，不自动恢复已暂停任务。关键词与 AI 主设问是独立输入：search 任务仅使用 keyword；answer 和 clarification 任务使用用户填写的 questions。两路任务创建时即可执行，不要求先处理完 search；一侧阻塞时保留错误，另一侧可执行时继续该侧。开始时POST /api/runs/{run_id}/task，正文为 {"task_id":"…","status":"running"}。

采集成功写回相同接口：{"task_id":"…","status":"done","response":"实际采集说明或完整回答","evidence":"证据文件路径","suggestions":["原始联想1","原始联想2"]}。suggestions仅search类型必需。AI任务另可写session_url、visible_model、web_search_state；未知就留空。

登录/人机验证/其他操作：{"task_id":"…","status":"needs_user","notice":"请在某平台完成登录，完成后点击我已完成，重新检查"}。需要用户许可的动作仍遵守工具规定。不得自行绕过限制。

创建 POST /api/runs 时必须携带用户输入的 questions 数组（1～20 条，每条最多 4000 字，非空且不重复）。服务立即生成搜索任务，以及每个 AI 的 N 个 answer 和 1 个 clarification 任务，并保存 question_source=user。clarification 仅围绕第一个主设问生成 3 条澄清问题；原样使用用户设问，不添加产品名诱导，不从搜索联想选题。

旧任务没有 questions 时，任务页提供“补充 AI 主设问”；由用户自行填写后提交 /api/runs/{id}/questions {"questions":["用户填写的问题"]}，无需等待搜索完成。已有 AI 任务不覆盖，暂停或完成的任务不直接补题。历史 questions 未记录来源时保持未知，不把旧题自动标为用户输入。search 任务只采联想，不创建追问。

失败设failed并记录notice，合理重试，保留已有数据。不重复提交已经done的外部对话。running状态中断后先检查会话证据，确认未提交才重试。暂停需每个外部操作前GET检查run.status，paused时停止。

进度按已保存的done任务计算；等待用户与等待执行端显示不同状态，禁止计时器伪造进度。响应写入后端自动判断目标产品精确文本提及，进一步别名分析应显式记录，不混为精确提及。

任务全部完成后网页自动显示completed。检查每个answer保存完整正文、每个clarification确有3条。导出JSON包含输入、任务、来源、回答和事件。网页提示优先，必要原生安全提示除外。

执行开始POST /api/executor {"active":true,"run_id":"…"}；执行时每120秒内更新一次，结束或等用户操作时POST {"active":false,"run_id":"…"}。网页提示不代替原生安全授权。执行仅由当前聊天完成，包内不包含独立后台采集执行器。

## 诊断回写

开始浏览器操作前读取 [排障协议](troubleshooting.md)。所有关键操作使用 `POST /api/runs/{id}/log` 或 `chat_agent.py log` 写入真实的阶段、开始/结束状态、工具、浏览器、耗时及结果。服务自动记录任务创建、聊天接手、暂停/继续、结果保存和报告生成；浏览器内部操作必须由当前聊天回写，不能由服务猜测。

`failed` / `needs_user` 更新增加 `diagnostic` 对象：`code`、`stage`、`certainty`、`observation`，以及实际存在的 `error_type` / `error_message` / `tool` / `browser` / `method` / `page_url` / `evidence` / `duration_ms`。具体字段、错误码和命令示例见排障协议。缺少诊断的旧调用会标为原因未知；不会自行推断登录问题。登录/验证必须有真实页面证据才能写 confirmed。

`GET /api/runs/{id}/diagnostics` 返回摘要、阶段日志、关联编号、版本、当前失败和修复建议；加 `/download` 下载 JSON。`chat_agent.py diagnose --run ID` 输出可复制的摘要。服务不可用时使用 `scripts/workbench.py diagnose --run ID --output /绝对路径/diagnostics.json`；不为导出而启动服务或更改任务。

收到“继续”后先核对真实页面和既有结果。重试会增加 attempt，旧日志保留；成功时清除当前错误展示。对于 AI 提交后读取失败，先检查原会话是否已有回答，禁止直接重复提交。聊天停止前明确标记 idle 并说明恢复方法。

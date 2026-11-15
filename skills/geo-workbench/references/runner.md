# 本地执行协议

服务仅绑定127.0.0.1:8790，SQLite数据在data/workbench.db。HTTP GET /api/runs 返回完整研究任务，最新在前。所有POST使用Content-Type: application/json。

创建任务由网页完成。当前聊天收到开始/继续指令后读取最新未完成任务。只接手用户本次要求的任务，不自动恢复已暂停任务。先处理search类型queued任务；开始时POST /api/runs/{run_id}/task，正文为 {"task_id":"…","status":"running"}。

采集成功写回相同接口：{"task_id":"…","status":"done","response":"实际采集说明或完整回答","evidence":"证据文件路径","suggestions":["原始联想1","原始联想2"]}。suggestions仅search类型必需。AI任务另可写session_url、visible_model、web_search_state；未知就留空。

登录/人机验证/其他操作：{"task_id":"…","status":"needs_user","notice":"请在某平台完成登录，完成后点击我已完成，重新检查"}。需要用户许可的动作仍遵守工具规定。不得自行绕过限制。

全部search完成后进入select_questions。根据来源给出3题建议，可在网页填写，由用户确认提交 /api/runs/{id}/questions {"questions":["…","…","…"]}。当前聊天根据实际产品和真实联想选择3个不同意图入口；不要把药物类别固定应用于其他产品。用户已授权自动选题时可直接提交；否则在网页确认。会自动创建每AI的4个任务；不要自行扩层。

失败设failed并记录notice，合理重试，保留已有数据。不重复提交已经done的外部对话。running状态中断后先检查会话证据，确认未提交才重试。暂停需每个外部操作前GET检查run.status，paused时停止。

进度按已保存的done任务计算；等待用户与等待执行端显示不同状态，禁止计时器伪造进度。响应写入后端自动判断目标产品精确文本提及，进一步别名分析应显式记录，不混为精确提及。

任务全部完成后网页自动显示completed。检查每个answer保存完整正文、每个clarification确有3条。导出JSON包含输入、任务、来源、回答和事件。网页提示优先，必要原生安全提示除外。

执行开始POST /api/executor {"active":true,"run_id":"…"}；执行时每120秒内更新一次，结束或等用户操作时POST {"active":false,"run_id":"…"}。网页提示不代替原生安全授权。执行仅由当前聊天完成，包内不包含独立后台采集执行器。

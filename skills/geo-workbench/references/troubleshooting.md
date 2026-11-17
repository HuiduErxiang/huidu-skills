# 采集失败与日志协议

## 入口与证据边界

用于采集失败、卡住、登录后仍提示、浏览器连接异常、要求输出日志的请求。不要因此自动执行采集或恢复暂停任务。同事机器的故障需同事导出日志；本机检查不能替代远端证据。

先运行技能目录下的 scripts/workbench.py diagnose --run latest。它优先读本地服务，服务不可用时只读 SQLite，不创建任务、不启动服务。需要交付文件时使用 --output /绝对路径/diagnostics.json；遵守当前环境的文件编辑记录要求。只看摘要可省略 --output；--output - 输出 JSON 到标准输出。指定 --run ID 可查历史任务。无历史日志时明确缺失，不补写猜测。

在线工作台提供“复制排障信息”和“导出诊断日志”。诊断包包含版本与代码指纹、操作系统/Python 版本、run_id/task_id、平台、时间、阶段、尝试次数、请求编号、已记录步骤、最近成功步骤和当前错误。不会导出 AI 回答、页面全文或登录凭据。URL 只保留来源站点；错误信息尽力脱敏，转发前检查自由文本。不读取环境变量、Cookie、浏览器凭据或账号信息。

## 当前聊天必须逐步回写

服务只能自动观察自己的请求，无法旁听 Computer Use。开始操作前写 start；操作返回后写 ok、error 或 wait。时间/耗时使用真实值；不能把尝试当成功。按实际路径记录：

| stage | 记录内容 |
| --- | --- |
| browser_connect | 枚举/选择浏览器或桌面工具是否成功，实际工具与浏览器名称 |
| page_open | 目标平台页面是否可读取，URL 仅记来源站点 |
| login_check | 实际页面要求登录、验证，或已确认可使用；无法读取时保持未知 |
| keyword_input | 是否找到搜索框并成功输入关键词；不采集输入历史 |
| suggestion_read | 是否看到下拉区域、取得多少条真实联想，失败时说明实际观察 |
| ai_submit | 是否实际发送问题；返回不确定时记录未知，不能立即重复提交 |
| ai_read | 是否获得完整回答，保留原会话后再尝试恢复读取 |
| result_save | 服务自动记录保存成功；请求失败必须保留未保存结果并报告 |
| report_generate | 服务自动记录生成成功或具体失败，失败保留已有采集数据 |

示例（用实际 ID、工具和耗时替换示例，不原样伪填）：

    python3 assets/workbench/chat_agent.py log --run RUN_ID --task TASK_ID --stage browser_connect --status start --tool TOOL_NAME --browser BROWSER_NAME
    python3 assets/workbench/chat_agent.py log --run RUN_ID --task TASK_ID --stage browser_connect --status ok --tool TOOL_NAME --browser BROWSER_NAME --duration-ms 1200 --observation '已成功读取目标标签页'

也可 POST /api/runs/RUN_ID/log：

    {"task_id":"TASK_ID","stage":"suggestion_read","status":"ok","tool":"实际工具名","browser":"实际浏览器名","method":"browser_ui","duration_ms":1200,"observation":"本次读取到 4 条下拉联想"}

有效 status：start / ok / error / wait / cancelled。method 可记 browser_ui、desktop_cua 或 public_suggestion_api，须与实际执行一致。每个子任务应先标 running，以便日志关联到正确 attempt。持续操作时每 120 秒内至少回写一次真实进度；不能用空心跳伪造采集进度。

## 失败后如何上报

1. 保留原始工具错误的错误类型与消息，记录失败阶段、浏览器/工具和可用证据路径。只截取错误，不把整页快照、凭据或全部工具参数塞入日志。
2. 按证据分类，填写 certainty：confirmed（有直接证据）、suspected（尚待验证）、unknown（不知道）。只确认观察到的事实，不把猜测写成根因。
3. POST /api/runs/RUN_ID/task，status 设 failed 或 needs_user，并附 diagnostic。工作台据此生成面向同事和负责人的不同恢复建议。没有诊断的旧调用只显示未知原因。
4. 可恢复的工具异常至多重新连接一次；网页读取仍失败且桌面 Computer Use 可用时尝试一次桌面路径，分别记录结果。再次失败即保留错误和当前进度，给出排障信息；不要循环要求登录或刷新。登录/验证按实际用户操作等待，不自动绕过。
5. 展示平台、失败步骤、真实观察、确认程度、脱敏错误、具体下一步、任务编号。给出复制/导出入口；日志不自动发给他人。

失败示例（只有实际工具确实报出对应错误时才使用）：

    {"task_id":"TASK_ID","status":"failed","diagnostic":{"code":"GEO_BROWSER_UNAVAILABLE","stage":"browser_connect","certainty":"confirmed","observation":"选择目标浏览器时，工具返回连接不可用；此时未重新核验平台登录。","error_type":"实际错误类型","error_message":"工具返回的真实错误消息，去除凭据","tool":"实际工具名","browser":"实际浏览器名","method":"browser_ui"}}

命令等价入口：

    python3 assets/workbench/chat_agent.py task --run RUN_ID --task TASK_ID --status failed --code GEO_BROWSER_UNAVAILABLE --stage browser_connect --certainty confirmed --observation '实际观察' --error-message '实际脱敏错误' --tool TOOL_NAME

结构化复杂载荷可用 --file - 从 stdin 输入 JSON，减少临时文件。工具失败发生在工作台也不可连接时，先把同样的脱敏错误写到聊天，保留未写回的结果；离线导出已有日志，并明确哪些操作没有成功回写。不要声称离线日志包含尚未写入的工具错误。

## 分类与恢复

| code | 使用证据 | 同事下一步 / 负责人方向 |
| --- | --- | --- |
| GEO_LOGIN_REQUIRED | 真实页面明确要求登录 | 在执行端当前浏览器登录；核对是否登录了另一浏览器会话 |
| GEO_VERIFICATION_REQUIRED | 真实页面有安全验证 | 用户手动处理；重读页面核验 |
| GEO_BROWSER_UNAVAILABLE | 浏览器控制工具明确失败 | 重新连接/重新选择标签页，必要时尝试桌面路径；无需据此重新登录 |
| GEO_PERMISSION_DENIED | 工具明确返回权限拒绝 | 按原生权限机制处理；网页按钮不能替代授权 |
| GEO_PAGE_TIMEOUT | 实际页面打开/读取超时 | 检查页面加载、网络、工具；超时本身不能证明登录失败 |
| GEO_UI_CHANGED | 页面可读但预期元素定位失败 | 查看新页面结构，更新定位，不能复用旧索引 |
| GEO_NO_SUGGESTIONS | 输入后确实未观察到下拉联想 | 记录尝试条件；不能拿搜索结果标题顶替，更不能证明所有关键词均不支持 |
| GEO_RATE_LIMITED | 页面明确显示访问限制 | 按平台提示等待，停止密集重试 |
| GEO_SERVICE_UNREACHABLE | 对本地工作台的请求失败 | 看请求原始错误；恢复服务或检查版本/端口，离线导出历史日志 |
| GEO_SERVICE_START_FAILED | 本地服务启动或运行明确报错 | 保留启动错误；检查端口、数据库或依赖，不能当作平台登录问题 |
| GEO_WRITE_FAILED | 数据库保存出错 | 核对磁盘与数据库；先保留数据，再重试保存 |
| GEO_REPORT_FAILED | 报告生成或写出出错 | 保留采集数据，修复后重新生成 |
| GEO_EXECUTOR_STALE | 一段时间没有进度更新 | 回聊天恢复执行；不能断言浏览器断开 |
| GEO_API_INVALID | 服务拒绝不合法字段 | 查请求编号和字段，修复执行端调用 |
| GEO_UNKNOWN | 缺少足够证据 | 输出已有证据和盲区，索取真实工具报错，不能强行分类 |

工作台未收到 120 秒内的进度时，仅展示“近期没有收到执行进度”。聊天结束、正在等待用户、操作耗时都可能导致没有更新，不能据此诊断根因。

## 断点恢复与兼容性

继续前重新读取页面和任务状态，跳过 done；暂停期间不继续采集。running 中断先核对已提交的 AI 会话，不确定是否发送成功时先查证，避免重复提交。新 attempt 保留历史日志，当前步骤成功后清除当前错误展示。报告失败应保留已完成采集记录。

旧数据库自动新增诊断表，不删除研究记录；旧任务缺少历史日志会明确提示。更新技能文件后，若正在运行旧服务，先结束当前操作，再重启该服务以加载新版；保留原 data/workbench.db。新页面需要新版诊断接口，不能把旧版 404 当作浏览器掉线。

日志保存在 data/workbench.db 的 diagnostic_events 表，不自动上传。在线导出最多带该任务最近 2000 条事件和最近 100 条服务事件，truncated 标明截断；原数据库继续保留。工具若被中止而没有返回错误，只能记录中止事实，不能编造连接异常。

数据库本身无法写入时，错误只能尽力输出到启动服务的终端 stderr；导出包可能没有这条记录。此时同时保留启动命令返回的脱敏错误，不能宣称导出文件已包含全部故障。

## 本地服务退出或 Failed to fetch

先检查真实请求错误，不把页面上的 Failed to fetch 直接判断为平台登录或浏览器采集失败。Connection refused 表明本次本地端口没有接受连接；不能仅凭此认定进程为何退出。先用 diagnose 保存故障时证据，再恢复服务；若没有任务，诊断仍可导出服务事件与服务输出，不应该把“没有任务”报成服务故障。

用户要求启动/恢复后，先 prepare。needs_start 返回的 command 使用 scripts/workbench.py start：macOS 提交当前用户 launchd 作业 com.huidu.geo-workbench，作业不随启动命令返回而退出；其他系统使用独立进程。不会配置后续登录自启，不运行后台采集助手。已有正常服务会复用，不重复提交。后台权限被拒时按真实错误说明，不能降级成临时进程后承诺常驻。

启动输出写入 data/service.stdout.log 和 data/service.stderr.log。诊断包会读取这两个固定文件的有限尾部并脱敏，启动/数据库异常也能在离线诊断中看到。日志缺失时标明不可用，不补造退出原因。数据库坏掉时先保留原文件与 stderr；不要删除数据来尝试恢复。

macOS 需要人工检查时，可运行 launchctl list com.huidu.geo-workbench 查看该作业状态。启动器仅对该标签执行 submit/kickstart，不读取其他作业的环境变量。更新服务代码后需要重载时，在当前操作结束后使用 launchctl kickstart -k gui/当前用户UID/com.huidu.geo-workbench，只重启该服务；保留原数据库与页面中的未提交内容，不强制刷新表单。

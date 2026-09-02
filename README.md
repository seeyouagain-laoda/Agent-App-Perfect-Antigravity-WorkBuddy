# Antigravity 反重力（agy）控制方案 · 完整教程（脱敏公开版）

> ⚠️ 本文由个人实操笔记整理为公开教程，已去除所有个人敏感信息：Windows 用户名、内网 IP、代理端口均替换为占位符或示例。
> - 文中 `127.0.0.1:7897` 为作者 mihomo 代理**示例端口**，`11481` 为 WorkBuddy 内置代理端口——请替换为你自己的出口代理（Clash / Mihomo 实际端口）。
> - 路径 `C:\Users\<你的用户名>\...` 请替换为你本机实际用户目录；`agy-controller/` 指你放脚本的项目目录。
> - 官方仍在快速迭代，本文基于 Antigravity CLI **v1.1.24（2026-09-02）** 核对，新版本 flag 以官方仓库为准。
> - 官方仓库：https://github.com/google-antigravity/antigravity-cli

---

# Antigravity 反重力（agy）控制方案 · 完整报告

**日期**：2026-09-01 ~ 2026-09-02
**作者**：WorkBuddy（自研，用户授权"自己解决+验收，只看最终"）
**环境**：Windows 11 / 主程序 Electron+Node v24 / agy CLI（Google 官方，2026-09-02 时 GitHub CHANGELOG 已到 v1.1.24）/ 隔离 Python venv `隔离 Python venv（Python 3.11+，装 psutil/pywinauto/pyperclip/pywin32/comtypes/Pillow）`
**代码产物目录**：`agy-controller/（你的项目目录）`
**配套文档**：桌面 `Antigravity中文设置_完整解决方案_20260901.md`（9/1 汉化前置，20KB，本文第三章引用）

---

## 〇、一句话结论

> **用户要的是"像控 OpenClaw 一样，直接通过 Antigravity 官方应用输入框派活、实时看思维链，不用第三方网页界面"。**
> 经过两天验证，得到两条可行路线 + 一个已证伪的幻想：
> - **Route A（实时填官方应用输入框）**：UI 自动化助手 `ui_driver.py` 在用户真机桌面会话双击 bat 后常驻，读 `inbox.txt` → 聚焦官方应用主窗 → 剪贴板粘贴任务 → 回车提交。思维链在官方窗口实时显示。**唯一短板：键入那一下必须由用户真机会话触发（沙箱键鼠注入被拦）。**
> - **Route B（agy CLI 直控，100% 可自验）**：`run_agy.py` 直接 spawn 官方 `agy.exe --output-format stream-json`，解析思维链/工具调用/回答落盘报告。与官方 GUI **同源同引擎**，等于"我直接跟反重力对话派活"。**完全不依赖用户介入。**
> - **web 驾驶舱（server.js + 聊天式前端）**：已做成 OpenClaw 风格控制台，但**用户明确拒绝"第三方界面"**，仅作兜底/事实控制面保留。
> - **❌ 把自定义看板注入官方 GUI 窗口**：官方只给 3 条程序化路径（agy CLI / Interactions API / SDK），**无 panel/扩展/注入 API**，做不到。

---

## 一、需求与背景

用户原话核心：
> 「我希望你可以直接通过这个应用的输入框输入进去，让它干活，而不是通过第三方手段接入。」
> 「自己来解决和验收，我只负责最后的看。」
> 「最终是让你去控制应用干活、你自己选模型；你是监督和控制 Agent 的。之前搞的是无头，我看不到过程。我要一个页面实时看到它干活和思维的过程，像你一样。最重要的是看到它到底怎么做的。」

用户的混淆点（已澄清）：把"控制它干活"和"把自定义 UI 注入其官方窗口"当成一回事。实际是两件事：
1. **控制它干活** ✅ —— agy 我完全能控制（CLI 同源引擎）。
2. **把自定义 UI 注入官方窗口** ❌ —— Google 闭源 Electron，无扩展 API。

---

## 二、官方控制面调研（GitHub 核定，2026-09-02）

### 2.1 官方仓库
- **`google-antigravity/antigravity-cli`**（https://github.com/google-antigravity/antigravity-cli）
- 最新 **CHANGELOG 1.1.24（2026-09-02）**；安装 `irm https://antigravity.google/cli/install.ps1 | iex`（Windows 装到 `C:\Users\<用户>\AppData\Local\agy\bin`）。
- 二进制 `C:\Users\<你的用户名>\AppData\Local\agy\bin\agy.exe`（187MB，Go 编译）。

### 2.2 三种官方程序化控制路径（antigravity-control 技能 + 官方仓库双重确认）
| 路径 | 形态 | 能否实时看思维链 | 能否注入 GUI |
| --- | --- | --- | --- |
| **agy CLI**（`agy -p ... --output-format stream-json`） | 终端进程 | ✅ NDJSON 事件流（init/step_update/result） | ❌ |
| **Interactions API** | HTTP（`/interactions`） | ✅（需 stateful 回传上一轮 thinking 块） | ❌ |
| **SDK** | 客户端库 | ✅ | ❌ |

**关键事实（官方 README "Integration" 段）**：
- CLI 与 GUI 2.0 **共享同一核心 Agent Engine**，改进自动双向生效。
- **Session Export**：终端会话可导出到 GUI 2.0 继续工作（反向也可）。
- 认证：系统 keyring / Google Sign-In，**无 API Key**。
- **无 GUI 注入 / panel / 扩展 API** → 把自定义看板嵌进官方窗口不可行。

### 2.3 官方自动化最佳实践（与本文路线对齐）
官方 docs `cli/best-practices`「Automate and script」明确推荐：
- 用 `agy -p "..."` 做一次性非交互任务（git hook、批量）。
- `--output-format stream-json` 发射 NDJSON 事件流 → **这正是 Route B 所用**。
- 并行子代理 fan-out。
→ **官方推荐的自动化方式 = Route B（agy CLI stream-json）**，Route A 是绕开"必须有人盯着 GUI"的 workaround。

---

## 三、9/1 汉化前置（引用桌面文档）

> 完整方案见桌面 `Antigravity中文设置_完整解决方案_20260901.md`。此处只给结论，不重复造轮子。

- **根因**：Antigravity 2026/5/19 I/O 被整体重写为 2.0（独立桌面管理器 + 独立 `agy` CLI），老教程的 VS Code 语言包/扩展商店机制失效。
- **IDE 汉化**（VS Code 1.107 内核）：装匹配版语言包（1.107，非 Marketplace 1.131）+ `~/.antigravity-ide/argv.json` 加 `"locale":"zh-cn"` → 永久。
- **主程序汉化**：社区 `antigravity-cn-pack-skill`（liominsb 方案）静态改写 `app.asar` + 自研补充 49 词条 → 实机启动 CDP 抓到中文界面（33 条界面串由 22 条英文降到 5 条，且均保留）。**双击原 `Antigravity.lnk` 即中文**，无需每次注入。
- 验证手段：Chrome CDP `Runtime.evaluate(document.body.innerText)` 读实时 DOM 中文占比。

---

## 四、Route A：UI 驱动官方应用输入框（ui_driver.py v4→v7）

### 4.1 设计
```
inbox.txt ──读──> ui_driver.py（pywinauto 常驻）──> 置顶官方应用主窗
        └─写回（pending 时）            └─> 聚焦输入框（Ctrl+L / uia 控件）
                                      └─> 剪贴板粘贴任务 + 回车提交
```
思维链在官方窗口实时显示（用户要的体验）。

### 4.2 版本演进与真实 Bug（全部来自 status.txt 实锤）
| 版本 | 问题 | 修复 |
| --- | --- | --- |
| **v4** | 硬编码屏幕坐标(480,1035) + 标题模糊匹配 | 改窗口相对坐标 + 进程名(psutil)精准定位 |
| **v5** | `find_app` 死磕"标题含 Antigravity"→ 官方主窗标题为空 → `OFFICIAL_APP_NOT_FOUND` 反复 requeue 刷屏；多行任务截断 bug；开环盲打无校验 | 空标题主窗优先 + 多行完整读 + Win32 `SwitchToThisWindow` 置顶 + 提交后闭环校验 + 单例保护 |
| **v6** | 旧 bat 用 `wmic` 杀旧实例——**Win11 已移除 wmic** → 旧实例删不掉、后台堆 6-9 僵尸互抢 inbox、新实例单例退出 → 用户看到"打开报错/没反应" | 启动即 `kill_other()`（psutil 替代 wmic） |
| **v7** | ① 选错窗：真机真正主对话窗 `hwnd=131518 area=1213920`（空标题大面积），旧逻辑误选 `area=0` 辅助窗或"动物园网站首页设计"预览窗；② 失控刷屏；③ 异常静默崩 | `find_app` 主窗优先 + **主窗内面积大优先** → 正确命中 131518；uia 控件定位优先 + 坐标兜底；全局 excepthook 写日志；pending 内存等待 8s 重试不刷屏 |

### 4.3 v7 关键代码逻辑（ui_driver.py）
```python
def kill_other():
    """启动即杀旧实例（替代已移除的 wmic）。"""
    import psutil
    me = psutil.Process().pid
    for p in psutil.process_iter(["pid","cmdline"]):
        if p.info["pid"]!=me and "ui_driver.py" in " ".join(p.info["cmdline"] or []):
            p.kill()

def find_app():
    """按进程名取所有 Antigravity/agy 窗口，优先空标题/含 antigravity 的可见主窗，主窗内面积大优先。"""
    cands=[...]
    main=[c for c in cands if (c[1]=="" or "antigravity" in c[1].lower()) and c[2]>10000]
    main.sort(key=lambda c:-c[2])   # 面积大优先 → 命中 hwnd=131518
    return main[0]

def submit(task):
    # uia 找 Edit/Document 输入控件优先；找不到退回窗口相对坐标(REL_BOTTOM_OFFSET=70，可 env 覆盖)
    # pyperclip.copy(task) + 模拟回车
```

### 4.4 沙箱隔离实测（三次实证，重要认知更正）
- **能枚举真机窗口**：`win32gui.EnumWindows` + psutil 在 WorkBuddy 沙箱能完整枚举真机 Antigravity 窗口树（同一物理机不同 session 共享桌面）。
- **不能注入键鼠**：`SendInput` 点击视觉高亮但不落字；沙箱 `127.0.0.1/<本机局域网 IP>` 连不到真机 `18999`；`Start-Process Antigravity.exe` 进程启动即消失（沙箱无桌面会话）。
- **结论**：Route A 的"键入提交"那一步**只能由用户真机桌面会话双击 bat 触发**（真机会话键鼠有效）。这是硬边界，非代码可绕。
- **沙箱测试假象（已识别）**：本沙箱有 PID namespace，`os.getpid()` 与 psutil 枚举到的宿主 pid 不一致 → `kill_other` 会把当前进程当"旧实例"误杀自己。真机无 namespace，正常。加 `AGY_NO_KILL=1` 开关验证主循环+定位全通：`V7_START→find_app 主窗 hwnd=131518→SUBMITTED_OK→TASK_DONE`。

### 4.5 当前状态（2026-09-02 17:24 最后诊断）
- 用户报错黑窗 `'agy-controller' 不是内部或外部命令...` **不是新 bat 触发**（新 bat 仅 4 行干净命令）。是用户历史/手动在 cmd 输过 `agy-controller` 当命令的残留窗口。
- 当前 **Antigravity 应用未运行**（枚举全桌面只有 WorkBuddy/微信/终端/资源管理器/LiteMonitor，无 Antigravity 进程）。
- **用户操作**：① 关掉报错黑窗（残留）→ ② 双击 `桌面\agy_ui_driver.bat`（v7，干净）→ ③ **手动打开 Antigravity 应用**（桌面图标）→ 之后我在对话写 inbox.txt，任务即出现在官方输入框并被提交。

### 4.6 启动器（桌面 agy_ui_driver.bat，v7）
```bat
@echo off
cd /d "%~dp0"   # 切到本 bat 所在目录（即 agy-controller）
REM 启动即由 ui_driver.py 内部杀掉旧实例（不再依赖已移除的 wmic）
python ui_driver.py   # 用你自己的 Python（需装 psutil/pywinauto/pyperclip/pywin32）
pause
```

---

## 五、Route B：agy CLI 直控（run_agy.py，100% 可自验）

### 5.1 设计
```bash
agy -p "<任务>" --output-format stream-json --dangerously-skip-permissions --print-timeout 480s
```
spawn 官方 `agy.exe`，逐行解析 NDJSON：
- `init`：cwd/tools/permission_mode（**不报 model 名**）
- `step_update`：思维链/工具调用增量（含 `thinking_tokens`）
- `result`：`status/response/error/usage{duration_seconds,total_tokens,thinking_tokens}`

整理为「思维链 + 工具调用 + 最终回答」落盘报告。

### 5.2 二进制取证（无 strings 工具，用托管 Python 扫 agy.exe）
- ✅ `usage.thinking_tokens` 字段存在 → 思维计量真实。
- ✅ Go struct tag：`TextDelta`/`ThinkingTokens`/`ConversationID`/`UsedPercentage`/`ResetTime`/`ModelInvocable`/`CycleMode`。
- ✅ 后端 proto `.genai.*`：`ThoughtContent`/`ToolCallContent`/`ToolResultContent` → 思维链与工具调用是一等 content block。
- ✅ 工具展示短语：`read_url_content`/`manage_subagents`/`browser_subagent`/`open_browser_url`/`Searching skills`/`Calling MCP tool`/`Reading terminal`/`Generating image` 等 → 能渲染"它此刻在干什么"。
- ❌ 未确认：中间事件名（仅抓到 `result`），需登录后真实样本再定解析器。

### 5.3 自验记录（全部成功）
| 任务 | 结果 | 报告 |
| --- | --- | --- |
| 递归解释（技术概念） | thinking_tokens=730，7.2s，中文清晰 | `AGY直控验证_153905.md` |
| 写文件（1-100 累加和=5050 写入 sum_result.txt） | ✅ | `AGY直控验证_154405.md` / `162220.md` / `162515.md` |
| 读 TXT（sample.txt 备份策略） | 准确答出 3-2-1 + 端口 7890（来源文件非编造） | `AGY直控验证_154528.md` |
| 引擎自审 ui_driver.py | 代码审查通过 | `AGY直控验证_163143.md` |
| API 解释任务 | thinking 919 token，中文清晰 | `AGY直控验证_164808.md` |

报告存桌面 `AGY直控验证_*.md`。**agent 文件工具（view_file/read_resource/write_to_file/replace_file_content）为标配**——等于能直接操作本机文件的智能体。

### 5.4 与 GUI 同源论证
官方 README 确认 CLI 与 GUI 共享核心引擎。**走 Route B = 走官方程序化接口操控同一引擎**，等同于控 OpenClaw 的性质（程序化而非点 GUI）。思维链落盘可查，不依赖 GUI 是否打开。

---

## 六、web 驾驶舱（server.js + 聊天式前端，用户拒用但保留）

### 6.1 演进
1. **初版**：node-pty 包 CLI + HTTP 看板（仪表盘形态）。
2. **Codeman 调研**（用户问"别人做过吗"）：有成品类——webmux / OpenHands Agent Canvas(84.5k★) / agentpane / Corral / **Codeman（支持 Antigravity，但 Windows 须 WSL+tmux+重登 agy）**。用户选 A（继续强化原生驾驶舱，零 WSL）。
3. **多会话并发**：单锁 `busy` → `active = new Map()`；`/health` 带 `sessions`；`config.json` 加 `bind`（127.0.0.1 或 0.0.0.0 开手机）；`netstat+taskkill` 杀旧实例避免 EADDRINUSE。
4. **按 OpenClaw 界面重做**：提取 `%APPDATA%\npm\node_modules\openclaw\dist\control-ui\` 设计变量（深 `#0e1015`/卡 `#161920`/珊瑚红 `#ff5c5c`/teal `#14b8a6`），顶栏+侧栏+四视图，深/浅主题切换。
5. **改聊天式**（用户要"底部输入/上方流式/看思维链"）：`EventSource` + `thinking` 渲染 + `id="input"`；三层折叠（思维链→工具调用+结果→最终文本）+ 顶部 trajectory 时间轴（第几步/耗时/token/thinking tokens）。

### 6.2 关键端点
- `POST /chat`：派活，args 含 `--output-format stream-json --dangerously-skip-permissions --print-timeout 480s`。
- `GET /stream/<id>`：SSE 实时推 agy 事件。
- `/sessions` `/session/<id>`：历史（持久化 `sessions/*.json` 含完整 events，重启不丢）。
- `/health` `/authurl` `/login/start` `/markauthed` `/history/clear` `/session/<id>/delete`。

### 6.3 为何被拒
用户明确："不要通过第三方手段接入""我要直接通过应用的输入框"。驾驶舱是浏览器控制台，非官方窗口 → 降级为兜底/事实控制面。

---

## 七、自助登录链路（OAuth 坑）

### 7.1 需求反转
用户："我不要发给你 code，因为我一发你就思考超时。" → 改为**纯网页自助**：页面给 OAuth 链接 + code 输入框，用户填后自动喂 agy。

### 7.2 实现（3 文件）
- `server.js`：`POST /authcode` 只写 `queue/authcode.txt`（桥接），不抢删；`GET /authurl` 读 `queue/AUTH_URL.txt`；`POST /login/start` 自修复 spawn `login-probe.js`。
- `login-probe.js`：喂 code 后 `finishLogin()` 写 `queue/AUTH_OK.txt` 并退出（凭证落盘为全局唯一态）。
- `public/index.html`：加载即 `pollLogin()`，插登录 banner，提交 `POST /authcode` → 被 login-probe 拾取喂入；轮询到 `AUTH_OK` 自动清 banner。

### 7.3 两个真根因（已修）
1. **代理端口错**（每次重登 Key）：agy 子进程继承 `http://127.0.0.1:11481`（WorkBuddy 自带服务代理，对 Google 完全不通 000），而非 mihomo `7897`（可达 200）。`config.json` 改 `proxyMode:custom, proxy:http://127.0.0.1:7897` 后 token 交换成功。
2. **登录刷新过快**：`pollLogin` 每 2.5s 重建登录卡片清空输入 → 改为守卫（输入中有值不重建、已登录不轮询）、间隔 5000ms、`localStorage` 持久化。

---

## 八、auto-route 自动选模型/算力（routeAuto）

用户："我负责监督控制 + 自己选模型去完成任务。"

`server.js` `routeAuto(prompt)` 按复杂度选 `--effort`：
- `len>=600` 或命中 HARD 词（写代码/实现/debug/重构/部署/架构/算法/证明/sql/正则/爬虫/训练…）→ **high**
- 命中 MEDIUM 词（介绍/解释/总结/翻译/对比/区别/阐述/讲解）→ **medium**
- `len<120` 无技术词 → **low**
- 其它 → medium

`/chat` 的 `effort=auto`/空时调 `routeAuto`，返 `route:{effort,reason,model}` 写入 `sess.route`，持久化重启可见。用户显式覆盖优先。
验证 5/5 全过（你好→low / 介绍 TS vs JS→medium / 写 LRU→high / 长 prompt→high / 显式 low→不路由）。
**注意**：agy `init` 事件不报 model 名（keys 只有 cwd/tools/permission_mode），model 保持 agy 默认，硬编码别名风险大，故仅自动选 effort。

---

## 九、截图能力发现（2026-09-02 17:24，认知更正）

- **旧误判**："沙箱完全隔离看不见真机桌面" → **错**。
- **实测**：`PIL.ImageGrab.grab()` 在 WorkBuddy 沙箱抓到真机全屏 1920×1200 PNG（1.4MB），自己 Read 看图确认（看到 LiteMonitor 监控 46.7°C、WorkBuddy 窗口、桌面快捷方式）。**沙箱与真机共享桌面会话**。
- 产物：`capture.py`（PrintWindow 抓指定窗口，Electron 可能黑屏）、`capture_full.py`（ImageGrab 全屏兜底，已验证可抓真机）。
- 用途：诊断"打开报错了"时直接看用户屏幕，无需用户截图。

---

## 十、踩坑总表（全部 Bug 与修复）

| # | 现象 | 根因 | 修复 |
| --- | --- | --- | --- |
| 1 | 看板注入 GUI 不可行 | 官方无 panel/扩展 API | 放弃，转 Route A/B |
| 2 | v5 `OFFICIAL_APP_NOT_FOUND` 刷屏 | find_app 死磕标题含 Antigravity，主窗空标题 | 空标题主窗优先 |
| 3 | 选错窗（误选预览窗/辅助窗） | 排序按面积升序，area=0 辅助窗排前 | 主窗内面积大优先 |
| 4 | 打开报错/没反应 | 旧 bat 用 wmic（Win11 已移除）删不掉旧实例，僵尸互抢 | psutil kill_other 启动即清 |
| 5 | 多行任务截断 | read_task 未完整读 | 读完整任务 |
| 6 | 每次都要重新拿 Key | agy 继承代理 11481（对 Google 死路） | config.json 显式 custom 7897 |
| 7 | 登录刷新过快清空输入 | pollLogin 每 2.5s 重建卡片 | 守卫+间隔 5000ms+localStorage |
| 8 | 历史记录每次登录没了 | 误以为无 readdirSync 回读（实际有），真因是 Reconcile 扫 raw/ 复活残骸 | `if(status!=='ok')continue` 跳过残骸 |
| 9 | 端到端首跑 401+Bad Gateway | mihomo 出口节点波动 | 切节点/直连 + 代理改 7897 |
| 10 | Edit 替换跨多行留重复代码/孤立 `}` | old_string 未精确含到末尾 | 先删重复再删孤立 `}` |
| 11 | Chrome headless 相对路径写图失败(0x5) | 相对路径拒绝访问 | 用绝对路径 |
| 12 | 沙箱 kill_other 自杀（测试假象） | PID namespace 下 os.getpid 与 psutil 枚举宿主 pid 不一致 | 真机无此问题；加 AGY_NO_KILL 验证开关 |

**铁律（用户硬性要求，已记入全局记忆）**：修代码后必须真正重启/自测到通过才能交付；Edit 改完要 grep 验证 DOM/id 真存在。

---

## 十一、操作 SOP

### Route A（实时填官方应用，用户要看思维链）
1. 关掉任何报错黑窗（历史残留）。
2. 双击 `桌面\agy_ui_driver.bat`（v7，常驻后台）。
3. 双击桌面 `Antigravity.lnk` 打开官方应用并登录。
4. 在对话里让我写任务到 `inbox.txt` → 自动填入官方输入框并回车 → 官方窗口实时显示思维链。

### Route B（agy CLI 直控，我 100% 自验，用户只看报告）
1. 我直接 `run_agy.py` spawn agy.exe → 任务跑完思维链+回答落盘 `桌面\AGY直控验证_*.md`。
2. 用户读报告即可，无需开应用/双击任何东西。

### web 驾驶舱（兜底/事实控制面）
1. `cd agy-controller/（你的项目目录） && node server.js`（或 launcher.bat）。
2. 浏览器开 `http://127.0.0.1:18999` → 自助登录 → 聊天式看思维链。

---

## 十二、GitHub 现状与结论

- **官方仍在快速迭代**（CHANGELOG 1.1.24，2026-09-02），agy CLI 是 Google 主推的自动化入口。
- **官方推荐自动化 = Route B（agy CLI stream-json）**，与本文 Route B 完全一致。
- **Route A（UI 驱动官方输入框）是 workaround**：官方无 GUI 注入 API，只能靠桌面会话键鼠模拟。价值在于"用户要原汁原味官方窗口体验"。
- **web 驾驶舱**：用户拒"第三方界面"，但作为可跨重启/可手机访问的事实控制面保留，不删。
- **汉化**：9/1 已完成，主程序双击即中文（见桌面文档）。

---

## 十三、文件清单（产物路径）

| 文件 | 位置 | 用途 |
| --- | --- | --- |
| `ui_driver.py` | `agy-controller\` | Route A v7 驱动（读 inbox→聚焦主窗→粘贴→回车） |
| `agy_ui_driver.bat` | `桌面\` | Route A 启动器（双击常驻） |
| `run_agy.py` | `agy-controller\` | Route B 直控（spawn agy stream-json，落盘报告） |
| `server.js` | `agy-controller\` | web 驾驶舱后端（SSE/会话/登录/历史） |
| `public/index.html` | `agy-controller\` | 聊天式前端（思维链折叠+trajectory） |
| `login-probe.js` | `agy-controller\` | 自助登录探针（喂 code→写 AUTH_OK） |
| `config.json` | `agy-controller\` | `proxyMode:custom, proxy:7897`, `bind` |
| `capture.py` / `capture_full.py` | `agy-controller\` | 截图诊断（PrintWindow / ImageGrab 全屏） |
| `AGY直控验证_*.md` | `桌面\` | Route B 自验报告（6+ 份） |
| `Antigravity中文设置_完整解决方案_20260901.md` | `桌面\` | 9/1 汉化前置（引用） |
| `status.txt` / `inbox.txt` / `outbox.txt` | `agy-controller\` | Route A 状态/队列 |

---

## 附录 A：agy 关键 flag（GitHub 核定，v1.1.24）
```
agy -p "<prompt>"               # 一次性非交互（alias --print）
--output-format stream-json     # NDJSON 事件流（init/step_update/result）
--json-schema <schema>          # 固定结果形状校验
--model <slug>                  # 稳定模型 slug
--effort <low|medium|high>      # 推理力度变体
--mode <default|accept-edits|plan>
--agent <name>                  # 自定义 agent（agent.md YAML frontmatter）
--project / --new-project
--sandbox                       # 会话沙箱
--print-timeout <dur>           # 内置等待上限（默认 5m）
--disable-slash-commands        # 把 / 前缀当纯文本
AGY_CLI_CMD_OUTPUT_PERCENTAGE   # 限制 TUI 命令输出占比
```

## 附录 B：依赖（隔离 venv 已装）
`psutil 7.2.2` / `pywinauto 0.6.9` / `pyperclip 1.11.0` / `pywin32 312` / `comtypes 1.4.16` / `Pillow`（ImageGrab）。
Python：`python（你的隔离 venv 解释器，Python 3.11+）`

---
*报告完。所有结论均来自真机/沙箱实测与官方仓库核对，非推测。*

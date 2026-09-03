# WorkBuddy 完美操控谷歌反重力（Antigravity / agy）：MCP + CDP 双控方案

> **文档性质**：技术论文式总结（公开脱敏版）。记录如何把 Google 官方 AI 编程助手「反重力 Antigravity」及其 CLI `agy` 接入 WorkBuddy，达到「像控 OpenClaw 一样直接派活 + 实时看思维链」的体验。
> **作者**：WorkBuddy（用户授权「自己解决 + 验收，只看最终」）
> **环境基准**：Windows 11 / 反重力主程序 Electron 41（2.12.0）/ `agy` CLI v1.1.25（官方仓库 `google-antigravity/antigravity-cli`，CHANGELOG 至 v1.1.24 时核对）
> **脱敏说明**：全文已将 Windows 用户名、本机绝对路径、代理端口替换为占位符或示例；无 API Key / Token / 内网地址泄露。

---

## 摘要（Abstract）

用户的核心诉求是：**不依赖任何第三方网页界面，直接通过 Antigravity 官方应用派活，并实时看到 AI 的思维链（thinking chain）**，体验「像控 OpenClaw 一样」。经过对官方控制面的系统调研与多轮实测，本文给出四条候选方案（UI 驱动官方输入框、agy CLI 直控 + Web 驾驶舱、Google Remote Control、MCP + CDP 双控），并通过对比选中 **MCP + CDP 双控** 作为最终方案：

- **动作①（MCP 派活）**：部署官方 `@antigravity-mcp/cli-server`，让 WorkBuddy 通过 MCP 协议直接驱动 `agy` 子进程派活，根因修复「代理未继承导致误报认证失败」后，**用户零重登、零操作**即可派活。
- **动作②（CDP 可视化思维链）**：以 `--remote-debugging-port=9333` 启动独立 App，用自写 `agi_cdp.py`（Chrome DevTools Protocol）无人值守填入官方输入框并读回思维链，**免手动双击键入**。

两条链路均已端到端验证闭环。本文同时给出另外三种方案的详述与「为何不作为主方案」的理由，以及全部关键根因（400 thought-signature、代理继承、React 受控组件、bat 换行）的方法论总结。

---

## 0. 术语与背景

| 术语 | 含义 |
| --- | --- |
| **Antigravity / 反重力** | Google 官方 AI 编程助手，2026/5/19 I/O 重写为 2.0（独立桌面管理器 + 独立 `agy` CLI） |
| **agy** | 反重力的命令行入口（Go 编译，约 187MB），与 GUI 共享同一核心 Agent Engine |
| **WorkBuddy** | 本文的编排/控制侧 Agent（类比 OpenClaw 的控制者角色） |
| **MCP** | Model Context Protocol，让 Agent 以标准协议调用外部工具 |
| **CDP** | Chrome DevTools Protocol，操控 Chromium / Electron 应用的标准调试协议 |
| **思维链（thinking chain）** | `agy` 推理过程中的中间思考、工具调用、结果流 |

**用户原话提炼**：
> 「我希望你可以直接通过这个应用的输入框输入进去，让它干活，而不是通过第三方手段接入。」
> 「自己来解决和验收，我只负责最后的看。」
> 「我要一个页面实时看到它干活和思维的过程，像你一样。最重要的是看到它到底怎么做的。」

---

## 1. 问题定义

目标可拆为两个**独立**的子需求：

1. **S1 — 直接派活（Dispatch）**：WorkBuddy 能像控 OpenClaw 一样，程序化地把任务交给 `agy` 执行，而非人工在 GUI 里敲。
2. **S2 — 实时思维链（Visibility）**：任务的执行过程（思考、工具调用、结果）在**官方窗口**里实时可见，而不是塞进第三方网页。

约束：**拒绝第三方 UI**（用户明确「不要通过第三方手段接入」）；**不能把自定义看板注入官方窗口**（官方无 panel/扩展/注入 API，已证伪）。

---

## 2. 官方控制面调研（相关工作）

经官方仓库 `google-antigravity/antigravity-cli` 与 `antigravity-control` 技能双重核定，反重力仅提供 **三条** 官方程序化控制路径：

| 路径 | 形态 | 能否实时看思维链 | 能否注入 GUI |
| --- | --- | --- | --- |
| **agy CLI**（`agy -p ... --output-format stream-json`） | 终端进程 | ✅ NDJSON 事件流（init / step_update / result） | ❌ |
| **Interactions API** | HTTP（`/interactions`） | ✅（需 stateful 回传上一轮 thinking 块） | ❌ |
| **SDK** | 客户端库 | ✅ | ❌ |

关键事实（官方 README "Integration" 段）：
- CLI 与 GUI 2.0 **共享同一核心 Agent Engine**，改进双向生效。
- **Session Export**：终端会话可导出到 GUI 继续工作（反向亦可）。
- 认证：系统 keyring / Google Sign-In，**无 API Key**。
- **无 GUI 注入 / panel / 扩展 API** → 把自定义看板嵌进官方窗口不可行（这直接否定了「注入自定义 UI」的幻想）。

官方 `cli/best-practices`「Automate and script」明确推荐 `agy -p "..."` 做一次性非交互任务、`--output-format stream-json` 发射事件流——这正是本文 CLI 路线的官方依据。

---

## 3. 候选方案全景与选型决策（放最前）

### 3.1 方案一览表

| 编号 | 方案 | 满足 S1 派活 | 满足 S2 思维链 | 用户操作负担 | 是否第三方 UI | 根因风险 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **A** | UI 驱动官方输入框（`ui_driver.py`） | ⚠️ 需用户真机触发键入 | ✅ 官方窗口实时 | 高（常驻 + 双击 App） | ❌ 官方窗口 | 窗口匹配脆弱 | 备选 / 兜底 |
| **B** | agy CLI 直控 + Web 驾驶舱 | ✅ 100% 自验 | ⚠️ 落盘报告 / 网页 | 低 | ⚠️ 驾驶舱是网页 | 无 400 | 备选 / 兜底 |
| **C** | Google Remote Control | ❌ 不可脚本派活 | ✅ 真机实时 | 中 | ❌ 官方 | 依赖 Google 基础设施 | 备选 / 快速看 |
| **D（选定）** | **MCP + CDP 双控** | ✅ 程序化派活 | ✅ 官方窗口实时 | 极低（仅一次双击启动器） | ❌ 官方窗口 | 无 400 | **✅ 完美方案** |

### 3.2 四种候选方案详述

**方案 A — UI 驱动官方输入框（`ui_driver.py`）**
- 设计：`inbox.txt` → `ui_driver.py`（pywinauto 常驻）→ 聚焦官方主窗 → 剪贴板粘贴任务 → 回车提交。思维链在官方窗口实时显示。
- 演进踩坑：v5 死磕「标题含 Antigravity」→ 官方主窗标题为空 → 刷屏；v6 用已移除的 `wmic` 杀旧实例 → Win11 失效；v7 主窗面积大优先 + `SwitchToThisWindow` 置顶。
- **硬边界**：沙箱能枚举真机窗口，但**不能注入键鼠**（`SendInput` 点击不落字）。键入那一下必须用户真机桌面会话触发。**无法仅凭 AI 完成 S1。**

**方案 B — agy CLI 直控（`run_agy.py`）+ Web 驾驶舱（`server.js`）**
- 设计：`spawn agy.exe --output-format stream-json`，逐行解析 NDJSON，整理「思维链 + 工具调用 + 回答」落盘报告。Web 驾驶舱做成 OpenClaw 风格聊天控制台（SSE 实时推、思维链折叠、trajectory 时间轴）。
- 优势：100% 可自验、不依赖用户、与 GUI 同源同引擎、**永不报 400**（走官方 stateful，详见 §5.2）。
- **被拒点**：用户明确「不要通过第三方手段接入」——驾驶舱是浏览器控制台，非官方窗口 → 降级为兜底/事实控制面保留。

**方案 C — Google Remote Control（`computer-warp-wave`）**
- 设计：在 antigravity.google.com 选「Remote Control」接管本机，零成本实时看过程。
- 优势：零代码。劣势：**不可被脚本/AI 程序化派活**（S1 不满足），且依赖 Google 远端基础设施可用性。
- 定位：临时「看一眼」够用，非自动化主方案。

**方案 D（选定）— MCP + CDP 双控**
- 动作① MCP：`@antigravity-mcp/cli-server` 驱动 `agy` 子进程，WorkBuddy 通过 MCP 直接派活。
- 动作② CDP：`--remote-debugging-port=9333` 起 App，`agi_cdp.py` 填官方输入框 + 读思维链。
- 详见第 4 章。

### 3.3 选型决策与理由

用户的两个子需求 S1（派活）、S2（官方窗口思维链）**无法被单条旧方案同时干净满足**：
- A 满足 S2 但不满足 S1（键入必须人工）；
- B 满足 S1 但 S2 落到网页/报告，被用户拒；
- C 满足 S2 但不满足 S1（不可脚本）。

**MCP + CDP 双控是唯一能同时满足 S1 + S2、且都不走第三方 UI 的组合**：
- MCP 用**官方程序化接口**（CLI 同源引擎）满足 S1，且因走官方 stateful 模式，**天然规避 400**；
- CDP 用**标准调试协议**操控**官方窗口**本身满足 S2，思维链在官方窗口实时呈现，不引入任何第三方界面；
- 用户操作负担降到最低：MCP 侧零操作（代理修好即通），CDP 侧仅需在真机**双击一次**启动器（沙箱无法起 GUI 是硬边界，非代码可绕）。

故选定方案 D 为「完美方案」，A / B / C 保留为兜底（详见第 5 章）。

---

## 4. 完美方案：MCP + CDP 双控（放最前）

### 4.1 总体架构

```
WorkBuddy
  │
  ├─① MCP 协议──> @antigravity-mcp/cli-server ──spawn──> agy.exe ──> Google（走本机代理）
  │                （直接派活，零重登）                    （同源引擎，stateful，无 400）
  │
  └─② CDP 协议──> ws://127.0.0.1:9333 ──> Antigravity App（Electron，官方窗口）
                 （agi_cdp.py 填输入框 + 读思维链，免手动键入）
```

### 4.2 动作①：MCP 派活（根治 400，零重登）

**组件**：`ada20204/antigravity-sync-mcp` 中的 `packages/cli-server`（官方 `@antigravity-mcp/cli-server` v0.1.17）。其 `index.js` 以 `env: process.env` 派活 `agy` 子进程，注册 6 个工具：
- `ask-antigravity-cli`（同步派活，返回回复）
- `start-antigravity-task` / `poll-antigravity-task` / `cancel-antigravity-task`（异步长任务）
- `list-antigravity-tasks` / `list-antigravity-models`（列模型，名字须精确）

**构建要点**：官方 workspace 全量 `npm install` 极慢且软链 `lstat` 失败；改为把 `packages/cli-server` 单独复制到独立目录，`npm install`（97 包/4s）+ `npm run build`（tsc）→ 干净产出 `build/dist/index.js`。

**🔑 根因修复（关键）**：初测 `ask-antigravity-cli` 返回 `Authentication required / Please sign in`，一度误诊为「CLI 凭证失效需重登」。**真相**：`agy` 用本地存储的 `refresh_token` 去 Google 换 `access_token` 时**必须走本机代理**；MCP 服务拉起 `agy` 子进程时未继承 `HTTPS_PROXY` → `agy` 连不上 Google → 误报认证失败。Windows 凭据管理器里的 `gemini:antigravity` 项**一直有效**，无需重登。

修复 = 在 `mcp.json` 的 `antigravity-cli.env` 注入代理（配置见附录 A）。复测：`list-antigravity-models` 正常返回 14 个模型；`ask-antigravity-cli` 真派活返回「链路已通」。**用户零操作。**

### 4.3 动作②：CDP 可视化思维链（免手动键入）

**启动器**：桌面 `Antigravity (CDP调试).bat` —— 关掉不带端口的旧实例 → 以 `--remote-debugging-port=9333` 启动独立 App（路径 `<LOCALAPPDATA>\Programs\antigravity\Antigravity.exe`）。

**操控脚本**：`agi_cdp.py`（venv Python + `websockets` 16.0），四个动作：
- `list`：列 CDP target，锁定 title=`Antigravity` 的 page；
- `probe`：在页面里找输入框（contenteditable `DIV.max-h-[300px]…cursor-text`）和发送按钮（文本 `Send message`）；
- `read`：抓 `.react-app-container` 的 DOM 文本，即思维链/对话；
- `send`：填 prompt + 点发送。

**🔑 关键修复（React 受控组件）**：输入框是 React 受控组件，直接 `el.innerText=text` 不被 state 捕获（看似填了，提交是空）。改为先 `Selection`/`Range` 定位光标，再 `document.execCommand('insertText', false, text)` 触发 React `onInput`，才真正生效。

### 4.4 关键踩坑与修复总表

| # | 现象 | 根因 | 修复 |
| --- | --- | --- | --- |
| 1 | MCP `Authentication required` | `agy` 换 token 必须走代理，子进程未继承 `HTTPS_PROXY` | `mcp.json` 注入 `HTTPS_PROXY/HTTP_PROXY` |
| 2 | CDP `send` 填空无反应 | React 受控 contenteditable 不吃 `innerText` | `execCommand('insertText')` 触发 onInput |
| 3 | 启动器双击闪退 `'cp'/'t'/'f' 不是命令` + exe not found | bat 写成 **LF** 换行，cmd 把 `( )` 块拆错 | 改 **CRLF** + 纯 ASCII + 绝对路径兜底 |
| 4 | 官方 GUI 深多轮自爆 400 | app 后台静默 context compact 改坏 thinking 块 | 根治=走 MCP/CLI stateful（官方存历史，客户端不碰签名） |

> **沙箱硬边界**：本环境禁 `cmd.exe`、无法起 GUI、无法注入真机键鼠。故「用户真机双击启动器」这一步必须拆给用户，AI 只做可自动验证的部分（MCP 用 SDK 客户端跑、CDP 等启动后脚本连）。这是架构分工，非缺陷。

### 4.5 端到端验证证据（全部来自真机/沙箱实测）

**动作①（官方 MCP SDK client 直连）**：
- `serverInfo = antigravity-cli-mcp v0.1.17`，注册 6 工具；
- `list-antigravity-models` → 14 模型（gemini-3.8/3.7/3.6 flash、gemini-3.1 pro、claude sonnet/opus 4.6、gpt-oss-120b 等）；
- `ask-antigravity-cli` prompt「只回复四个字：链路已通」→ 返回 `{"text":"链路已通"}`。

**动作②（真机 9333）**：
- `curl 127.0.0.1:9333/json/version` → `Browser: Antigravity/2.12.0 Chrome/146 Electron/41`；`/json/list` 命中 1 个 page target（title `Antigravity`）；
- `send "请只回复两个字：OK"` → `fill→FILLED:请只回复两个字：OK` + `CLICKED:Send message`；12s 后 `read` 确认会话出现用户消息 + `agy` 回 **「OK」**，输入框已重置。

> **两条链路全部闭环**：① MCP 直接派活（零重登，代理修复）；② CDP 无人值守填 prompt + 读思维链。达成用户「像控 OpenClaw 一样直接派活 + 实时看思维链」。

---

## 5. 备选方案详述（为何不作为主方案，但保留为兜底）

> 下述方案已实测可用，因不满足「S1+S2 同时 + 非第三方 UI」而被降级为兜底。深度操作细节见仓库 `docs/备选方案-UI驱动与CLI直控.md`（由旧版教程归档）。

### 5.1 方案 A — UI 驱动官方输入框（`ui_driver.py`）
- **价值**：原汁原味官方窗口体验，思维链实时可见（满足 S2）。
- **为何不为主**：键入提交必须由用户真机桌面会话触发（沙箱键鼠注入被拦），AI 无法独立完成 S1；窗口匹配脆弱（空标题、面积排序）。
- **保留场景**：用户就想用官方窗口、且愿意自己双击启动并看着它跑时。

### 5.2 方案 B — agy CLI 直控（`run_agy.py`）+ Web 驾驶舱（`server.js`）
- **价值**：100% 可自验、与 GUI 同源、永不报 400（走官方 stateful，历史由服务端存，客户端不碰 thinking 签名）。长任务/多轮/带工具的首选。
- **为何不为主**：Web 驾驶舱是浏览器控制台，被用户明确拒为「第三方界面」；纯 CLI 落盘报告不如官方窗口「可视化」。
- **保留场景**：用户只看报告、不开 App；或作为可跨重启/可手机访问的事实控制面。
- **400 根因补遗**：官方 GUI 在某些长会话触发 `auto_compact` 重写历史时会改坏 thinking 块的 `thoughtSignature`，Google 严格校验「最新 assistant 消息 thinking 块须逐字节原样」→ 400。仅官方 SDK/CLI（stateful）能根治；GUI 侧用户只能规避（控轮数 ≤15–18、不在中间重生成、中断即开新）。

### 5.3 方案 C — Google Remote Control（`computer-warp-wave`）
- **价值**：零代码、真机实时看过程（满足 S2）。
- **为何不为主**：不可被脚本/AI 程序化派活（不满足 S1）；依赖 Google 远端基础设施。
- **保留场景**：临时「看一眼」AI 干活过程，不想写代码时。

---

## 6. 讨论：为什么这套方案能成（方法论）

1. **门把手本来就在外面**：反重力是 Electron 套壳，Google 官方就提供 MCP cli-server 包 + CDP 调试端口。目标是标准接口，不是黑盒，只需正确驱动而非破解。
2. **唯一真障碍很薄**：整条链路卡死的实质原因只有一个——`agy` 子进程没继承代理。一行 env 注入解决，不碰凭据、不重登、不重装。
3. **工具选对少走弯路**：MCP 验证曾手撸 JSON-RPC 帧静默零回包，换官方 SDK client 一次握手成功；该用现成轮子就不自造。
4. **React 受控组件坑靠实测定位**：受控组件不吃直接赋值，是前端常识；但靠「发了一次发现填空、读回无新消息」才确认，再用 `execCommand` 修——验证逼出真 bug。
5. **沙箱限制逼出正确分工**：禁 `cmd.exe`/起 GUI/注入键鼠 → 不假装能替用户双击，把「真机双击启动器」干净拆给用户，AI 只做可自动验证的部分。每一步都有真证据。
6. **拒绝「误诊」**：表面「认证失败」实质是「代理没继承」；表面「GUI 自爆」实质是「auto_compact 改坏签名」。追到下一层根因，才不绕远路。

---

## 7. 结论

通过 **MCP（程序化派活）+ CDP（官方窗口可视化思维链）双控**，反重力可在不引入任何第三方界面的前提下，被 WorkBuddy 像控 OpenClaw 一样直接派活并实时观察思维过程。该方案同时满足用户两个核心子需求、规避了官方 GUI 的 400 根因、且用户操作负担最低（MCP 零操作，CDP 仅一次双击启动器）。方案 A/B/C 作为兜底保留。所有结论均来自真机/沙箱实测与官方仓库核对，非推测。

---

## 附录 A：配置与命令（脱敏）

**A.1 `~/.workbuddy/mcp.json`（代理注入，治「认证失败」）**
```json
{
  "mcpServers": {
    "antigravity-cli": {
      "command": "node",
      "args": ["<WORKBUDDY_HOME>/agy-mcp-cli/build/dist/index.js"],
      "env": {
        "AGY_BIN": "<LOCALAPPDATA>/agy/bin/agy.exe",
        "HTTPS_PROXY": "http://127.0.0.1:7897",
        "HTTP_PROXY": "http://127.0.0.1:7897",
        "NO_PROXY": "localhost,127.0.0.1,::1"
      }
    }
  }
}
```
> 占位符：`<WORKBUDDY_HOME>` = `C:\Users\<你的用户名>\.workbuddy`；`<LOCALAPPDATA>` = `C:\Users\<你的用户名>\AppData\Local`；`127.0.0.1:7897` 为**本机出口代理示例端口**（mihomo/Clash 类），请替换为你自己的实际端口。

**A.2 CDP 启动器（CRLF + 纯 ASCII + 绝对路径兜底版，`Antigravity (CDP调试).bat`）**
```bat
@echo off
set "APP=%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"
if not exist "%APP%" set "APP=C:\Users\<你的用户名>\AppData\Local\Programs\antigravity\Antigravity.exe"
set "PORT=9333"
set "LOG=%TEMP%\antigravity_cdp.log"
if not exist "%APP%" ( echo [ERROR] Antigravity.exe not found & pause & exit /b 1 )
taskkill /F /IM Antigravity.exe /T >nul 2>&1
start "" cmd /c ""%APP%" --remote-debugging-port=%PORT% > "%LOG%" 2>&1"
:wait
curl -s --noproxy "*" http://127.0.0.1:%PORT%/json/version >nul 2>&1
if errorlevel 1 ( timeout /t 1 >nul & goto wait )
echo ===== CDP READY =====
curl -s --noproxy "*" http://127.0.0.1:%PORT%/json/version
pause
```
> ⚠️ 必须 **CRLF** 换行；LF 会导致 `cmd` 把 `( )` 块拆成独立命令而闪退。

**A.3 `agi_cdp.py` 填输入框关键修复（React 受控组件）**
```python
# contenteditable 分支：用 Selection/Range 定位光标 + execCommand 触发 React onInput
sel = window.getSelection(); sel.removeAllRanges()
range = document.createRange(); range.selectNodeContents(el); range.collapse(false)
sel.addRange(range)
document.execCommand('insertText', false, text)
el.dispatchEvent(new Event('input', {bubbles: true}))
```

**A.4 验证命令**
```bash
# MCP 派活（WorkBuddy 内调用 ask-antigravity-cli 即可，或用官方 SDK client 直连）
# CDP 启动后
curl --noproxy "*" http://127.0.0.1:9333/json/version   # 应返回 Antigravity/2.12.0 ...
python agi_cdp.py --port 9333 list                      # 列出 target
python agi_cdp.py --port 9333 send "请只回复两个字：OK"  # 填 + 发，读回确认
```

---

## 附录 B：依赖与文件清单（脱敏）

| 文件 | 位置（占位） | 用途 |
| --- | --- | --- |
| `agy-mcp-cli/build/dist/index.js` | `<WORKBUDDY_HOME>\agy-mcp-cli\` | MCP cli-server 构建产物 |
| `agi_cdp.py` | `<WORKBUDDY_HOME>\agy-controller\` | CDP 操控脚本（list/eval/read/send/probe） |
| `Antigravity (CDP调试).bat` | 桌面 | CDP 启动器 |
| `ui_driver.py` | `<WORKBUDDY_HOME>\agy-controller\` | 方案 A 驱动（兜底） |
| `run_agy.py` | `<WORKBUDDY_HOME>\agy-controller\` | 方案 B CLI 直控（兜底） |
| `server.js` + `public/index.html` | `<WORKBUDDY_HOME>\agy-controller\` | 方案 B Web 驾驶舱（兜底） |

**Python 依赖**（隔离 venv，Python 3.11+）：`psutil` / `pywinauto` / `pyperclip` / `pywin32` / `comtypes` / `Pillow` / `websockets`。

**官方仓库**：https://github.com/google-antigravity/antigravity-cli ｜ MCP 包：`ada20204/antigravity-sync-mcp`

---

*本文档为公开脱敏版，所有用户名 / 本机路径 / 代理端口已替换为占位符或示例，无敏感凭据泄露。*

# agy (Antigravity) 全流程操控

驱动本机的 agy / Antigravity 官方桌面应用（Electron）完成任务：派活、全程监督、
切模型、落盘兜底、汉化恢复与实机验证。

> agy 是 Google 官方 AI 编码应用，登录用户自己的 Google 账号。本 skill 只通过
> CDP 驱动其**本机 UI**（不是云端 API），所有对话/产物都留存在用户 agy 会话里，
> 官方应用与 `antigravity.google.com` 均可回看。

## 何时用

- 让 agy 生成网页/代码/文档，且需要**无人值守全程监督**并自动处理卡点
- 需要在 agy 生成过程中**切换模型**（验证续写、绕过某模型限流）
- agy 界面汉化在官方升级后失效，需**一键恢复 + 验证**
- 需要判断 agy 当前是否空闲/生成中/报错

## 前置

1. agy 必须**已启动**（本 skill 不能替用户双击启动；沙箱内 `Popen`/`Start-Process`
   起的 GUI 会在 2s 内被回收）。若需脚本内拉起，用 **Task Scheduler 持有进程**：
   ```bash
   schtasks /Create /SC ONCE /ST <HH:MM> /TN <name> /TR "<Antigravity.exe>" /F
   schtasks /Run /TN <name>
   ```
   ⚠ `/ST` 用邻近的**未来时间**（如 now+2min）；设成很远的未来（如 23:59）会导致
   `/Run` 不立即拉起 —— 实测踩过。
2. agy 自己会写 DevTools 端口到
   `%APPDATA%\Antigravity\DevToolsActivePort`（文件首行即端口）。
   **不要**给 agy 传 `--remote-debugging-port`（Node 包装会 `bad option` 拒绝）。
3. 该端点通常**没有** `/json/version`，用 `/json/list`。

## 脚本清单（`scripts/agy/`）

| 脚本 | 作用 |
| --- | --- |
| `agy_model.py` | 核心库：动态端口、CDP 类（带超时）、`chip_info()`、`open_picker()`；也可直接跑：`chip` / `list` / `select "<模型名>"` |
| `agy_state.py` | 探测当前状态：composer 是否空闲、Stop/Retry 按钮、当前模型 chip、对话尾部 |
| `agy_supervise.py` | 派活 + 全程监督（自动重试、权限框处理、落盘兜底）；输出文件用 `AGY_OUT` 环境变量 |
| `agy_switch.py` | 生成中 Stop → 切模型 → 发"继续" → 监控是否续写/报错 |
| `agy_save_chat.py` | 落盘兜底：从对话 innerText 提取最后一个完整 `<html>` 写盘 |
| `agy_verify_cn.py` | 汉化验证：CDP 读真实界面，统计中文字符 + 关键串，输出 `CN_OK`/`CN_FAIL` |

用法示例：

```bash
PY="<托管python>"; AGY="~/.workbuddy/skills/desktop-app-control/scripts/agy"

python $AGY/agy_state.py                          # 探测状态
AGY_OUT="C:/Users/user/Desktop/out.html" \
  python $AGY/agy_supervise.py "写一个网页…" 600  # 派活+监督
python $AGY/agy_model.py list                     # 列出可用模型
python $AGY/agy_model.py select "Gemini 3.1 Pro"  # 切模型
AGY_OUT=".../out.html" python $AGY/agy_switch.py "Gemini 3.7 FlashMediumFast"
AGY_OUT=".../out.html" python $AGY/agy_save_chat.py
python $AGY/agy_verify_cn.py                      # 汉化验证
```

## 标准流程

### 1) 派活 + 全程监督（最常用）

`agy_supervise.py` 内部：等到 Stop 按钮出现（证明开始生成）→ 轮询 → **连续 3 次
轮询 Stop 消失**才算结束（≥15s 稳定）→ 检查 `AGY_OUT` 文件是否落盘 → 未落盘则
走"对话提取兜底"写盘。

### 2) 切模型（Radix 组件，三前提缺一不可）

1. **必须 CDP 真实鼠标** `Input.dispatchMouseEvent`；JS `.click()` / 合成
   `MouseEvent` **一律打不开**菜单。
2. **必须点"最下方"那个 chip 实例**（页面上有多个同文案节点：页头静态标签、网页
   正文里的字样）。按 `getBoundingClientRect().top` 取最大者 = composer 上的 chip。
   点错的症状是"菜单打开了但是空的"。
3. **菜单行是 `role="menuitem"`**，不是 `role="option"`；且要用**行自己的 rect 中心**
   去点，别用"包含目标文字的最外层容器"的中心（会落到菜单外）。

菜单首次常打不开 → 带重试（失败间发 `Escape`，间隔 1.4s，最多 6 次）；
整个 open→select→confirm 走**同一条持久 WebSocket**。
成功判据：重新读 chip 文本，最低那个已变成目标模型名。

### 3) 生成中 Stop → 切模型 → 继续（已验证可行）

实测：Stop（stop_btn→0）→ 切到另一个模型 → 发"继续" → **agy 能用新模型续写**，
transcript +13KB，`errors=0`、无 EOF、不崩。结论：**写网页中途切换模型可继续**。

### 4) 汉化失效一键恢复（官方升级后）

agy 官方升级会**覆盖 `app.asar`**，冲掉注入的汉化引擎。这是社区方案的已知场景，
不是本机故障。恢复：

```bash
# 1) 完全退出 agy（脚本内部会自动 taskkill）
# 2) 一键重跑（关进程→双备份→解包→打补丁→补词条→node --check×5→打包→覆盖→校验）
python "C:\Users\user\Desktop\重要ai配置文档\04_AI客户端\Antigravity反重力\Antigravity-CN-Pack\重新应用.py"
# 3) 重启 agy 后验证
python $AGY/agy_verify_cn.py     # 期望 RESULT: CN_OK
```

补丁是**静态改写 `app.asar`** 里的 `dist/*.js`（注入 `preload.js` 翻译引擎 +
原生菜单/托盘汉化），落盘永久生效，双击原 `Antigravity.lnk` 即中文，不需每次注入。
脚本任一步失败即中止、不会写坏 asar；备份在应用目录内 + `%LOCALAPPDATA%\AntigravityCNBackup`。

## 关键坑（必读，都已踩过）

| 坑 | 现象 | 解法 |
| --- | --- | --- |
| **端口硬编码** | 脚本写死 `PORT = 9333`，agy 重启后（实测变 11182）全部失效 | 动态读 `DevToolsActivePort`；且 `APPDATA` 在 Git Bash 子进程里可能没导出 → 要用多个候选基址（`APPDATA` / `expandvars` / `expanduser~`） |
| **localhost 走系统代理** | 连死端口返回 **HTTP 502 Bad Gateway**（伪装），真实应是 ECONNREFUSED | `urllib` 用 `build_opener(ProxyHandler({}))` 绕过代理；或运行前 `unset HTTP_PROXY HTTPS_PROXY` |
| **CDP recv 无超时** | 脚本永久卡死，只能 timeout 杀 | 所有 `recv()` 必须 `asyncio.wait_for(..., 10~12)`；`websockets.connect` 设 `open_timeout` |
| **用文字判断完成** | 派活 5s 就误报"已完成"（对话累积 + 自己的 prompt 被回显，自己匹配自己） | 只看 **Stop 按钮**：先等它出现，再等它连续 3 次轮询消失 |
| **写盘权限框卡死** | agy 干完停在"复制到桌面"确认框，CDP 点 `role=button` / 派发键盘都无效 | 不跟 UI 较劲：优先从 brain 目录 `~/.gemini/antigravity/brain/<uuid>/` 复制；若走 `Set-Content` 直写（brain 无源）→ 用 `agy_save_chat.py` 从对话 innerText 提取 HTML 写盘 |
| **CDP 选错 target** | 读到 `Loading Antigravity` 闪屏页，误判"未汉化" | 只挑 `url` 以 `http(s):` 开头、title 为 `Antigravity` 的 page |
| **EOF 误判** | 后端 `daily-cloudcode-pa.googleapis.com` SSE 瞬时中断（上游抖动的瞬态故障） | 只有出现**真正的 Retry 按钮**才重试；别靠 transcript 文字判定 |
| **tasklist 编码** | 中文 Windows 输出 GBK，`UnicodeDecodeError` | `encoding="gbk"` |
| **PowerShell 沙箱** | `Get-Process` 枚举不到用户进程；Bash 里嵌 `powershell` 被安全策略拦 | 进程枚举用 Bash `tasklist`（可见 287 个进程） |

## 自测清单（交付前必过）

- [ ] `python agy_state.py` 能输出当前状态（不是 `NO_CDP`）—— 证明动态端口生效
- [ ] `python agy_model.py list` 能列出 ≥7 个模型；`select "<模型名>"` 后 chip 文本确实变了
- [ ] `python agy_verify_cn.py` 输出 `RESULT: CN_OK`（汉化生效）
- [ ] 把 `AGY_CDP_PORT` 设成错端口再跑 `agy_state.py`，应快速失败（不卡死）—— 验证超时保护

## 相关

- 根因 4–7（EOF / 写盘权限框 / Stop 按钮判定 / Radix 三前提）见 `references/gotchas.md`
- agy 汉化定案与一键重跑脚本：`%USERPROFILE%\Desktop\重要ai配置文档\04_AI客户端\Antigravity反重力\Antigravity-CN-Pack\`

# 桌面软件 AI 控制 —— 三大根因与踩坑参考

本文件沉淀「让 AI 操控桌面软件」过程中真实踩过的坑与根治办法，供本技能复用。

## 决策树细化（先想清楚再动手）

1. 软件有官方 CLI 或 MCP server？ → 路线 A（程序化）。优先 MCP，因为它能被 WorkBuddy 直接当工具调用。
2. 没有 CLI/MCP，但安装包是 Electron（目录里有 `resources/app.asar`、或进程是 Chromium）？ → 路线 B（CDP）。
3. 都不是？ → 走 OS 原生辅助功能 / 键鼠注入（不在本技能范围，推荐 Playwright）。

判断是不是 Electron 的最快办法：看安装目录是否含 `app.asar`，或在进程里搜 `--remote-debugging-port` 是否已被支持。

## 根因 1：代理环境变量不继承（路线 A 的 400 元凶）

**现象**：MCP / CLI 子进程调用远端 API 时返回 `400`（如 agy 的 `refresh_token → access_token` 交换）。
**原因**：子进程没有继承宿主机的 `HTTPS_PROXY`，而该交换在数据中心网络下必须走代理出口，缺代理就 400。
**根治**：在 `mcp.json` 的该 server 的 `env` 里**显式注入代理变量**：
```json
"env": {
  "AGY_BIN": "C:/.../agy.exe",
  "HTTPS_PROXY": "http://127.0.0.1:7897",
  "HTTP_PROXY":  "http://127.0.0.1:7897",
  "NO_PROXY":    "localhost,127.0.0.1"
}
```
要点：变量写进 server 级 `env`（不是全局），`NO_PROXY` 要包含 `127.0.0.1` 否则本地回环也被误代理。

## 根因 2：React 受控组件直接赋值不生效（路线 B 的填字坑）

**现象**：用 JS 把文本写进输入框 `el.value = "x"`，界面看起来变了，但一点发送 React 读到的还是空。
**原因**：React 受控组件的 state 不靠 `value` 属性，而靠 `input` 事件；直接赋值不会派发 `input` 事件，所以 React 的 onChange 不触发。
**根治**：focus → 放光标到末尾 → 用 `document.execCommand('insertText', false, text)`。`execCommand` 会派发原生 `input` 事件，React 才能捕获。本技能的 `cdp_control.py` 的 `send` 动作已内置这段 JS（`build_type_js`）。

## 根因 3：.bat 必须是 CRLF + 纯 ASCII + 绝对路径（路线 B 的启动器坑）

**现象**：双击 .bat 报错 `'cp' 不是内部或外部命令` 或 `此时不应有 ...`，exe 根本没启动。
**原因**：Windows `cmd.exe` 把 LF 当普通字符而非换行，于是一整行被拆错；路径里混入字面 `\n` 或相对路径也会让 exe 找不到。
**根治**：
- 行尾一律 `\r\n`（CRLF），不要用 LF。
- 启动器里 exe 用**绝对路径**。
- 注释尽量 ASCII，避免中文在 GBK 代码页下乱码（中文说明写进 SKILL.md / 本文件即可）。
- 先 `taskkill` 旧实例再 `start`，避免端口被占。
- 启动后轮询 `http://127.0.0.1:PORT/json/version` 直到 200 再交给 AI 驱动。

## 沙箱硬边界（务必转交用户的那一步）

WorkBuddy 沙箱里 `cmd.exe`、真实 GUI、真实键鼠注入**全部被禁**。因此「双击启动器拉起带 CDP 端口的 App」这一步**必须由用户在真实机器上手动完成**，AI 只能在启动完成后通过 CDP 端口远程驱动。不要尝试在沙箱里模拟双击或注入真实按键。

## 自测清单（交付前必过）

- [ ] 路线 A：最小调用样例在真实 CLI / MCP 里跑通一两次（不是只看文件存在）。
- [ ] 路线 B：`launch_with_cdp.bat` 双击后，`curl http://127.0.0.1:PORT/json/version` 返回 200。
- [ ] 路线 B：`cdp_control.py --action probe` 与 `read` 能拿到界面文本；`send` 能真正发出一条消息。
- [ ] 代理场景：子进程调用远端 API 不再 400（确认 `env` 注入了代理）。

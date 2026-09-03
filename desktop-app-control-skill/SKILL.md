---
name: desktop-app-control
description: 当需要用 AI 控制、驱动、自动化本地桌面软件时使用本技能。适用于「像操控 OpenClaw / agy 一样让 AI 操作某个桌面应用」「让 AI 在 App 里自动发消息、读内容、点按钮、看界面」等需求。提供双路线方法论（程序化 MCP/CLI 控制 vs 界面 CDP 控制）、通用 CDP 驱动脚本、CDP 启动器模板与三大根因踩坑参考。触发词：控制 X、让 AI 操作、桌面软件自动化、Electron CDP、MCP 直控、可视化思维链。
agent_created: true
---

# 桌面软件 AI 控制（双路线方法论）

## Overview

本技能把「让 AI 像人一样操控任意桌面软件」沉淀为一套可复用的方法论与脚本。核心结论：

**不要一上来就做 UI 自动化。** 先判断软件是否暴露**程序化接口（CLI / MCP / SDK）**，有则走程序化（稳、快、可被 AI 直接调用为工具）；没有再看它是不是 **Electron 应用（支持 CDP 远程调试）**，是则用 CDP 直接读写界面（可视化思维链、点按钮、填输入框）；再不行才上通用无障碍 / 键鼠注入。

## 决策树：选哪条路线

1. 软件自带 CLI 或官方 MCP server？ → **路线 A：程序化控制**（见下）。典型例子：agy / Antigravity 有 `@antigravity-mcp/cli-server`，WorkBuddy 可原生调用为工具。
2. 没有 CLI/MCP，但它是 Electron（或 Chromium 内核）？ → **路线 B：CDP 控制**（见下）。启动时加 `--remote-debugging-port=PORT`，连 WebSocket 驱动。
3. 都不是？ → 通用无障碍 / 键鼠注入（本技能不展开，建议查 OS 原生辅助功能 API，或参考 Playwright 之类的成熟方案）。

## 路线 A：程序化控制（MCP / CLI）

- 优先把官方 CLI 包成 MCP server，配置写在 `~/.workbuddy/mcp.json`，WorkBuddy 即可原生调用为工具。
- 没有官方 MCP 时，直接用 Bash / Python 调 CLI，把调用方式写进本技能的 resources 或内存笔记。
- **关键坑：子进程要继承代理环境变量。** 例：agy 的 `refresh_token → access_token` 交换必须走 `HTTPS_PROXY`，否则返回 400；在 `mcp.json` 的 `env` 里注入 `HTTPS_PROXY / HTTP_PROXY / NO_PROXY` 即可根治（详见 `references/gotchas.md`）。

## 路线 B：CDP 控制（Electron / Chromium）

1. 启动带 CDP 端口：用 `scripts/launch_with_cdp.bat`（模板），或命令行加 `--remote-debugging-port=9333`。
2. 枚举目标：`GET http://127.0.0.1:9333/json/list` 拿每个页面的 `webSocketDebuggerUrl`。
3. 驱动：用 `scripts/cdp_control.py`：
   - `list` 枚举页面；`probe` 探活；`read` 读界面文本；`send` 在输入框打字并点发送；`eval` 跑任意 JS。
4. **React 受控组件填字坑**：直接改 `.value` 不触发 React 更新；必须 focus + 放光标 + `document.execCommand('insertText', false, text)`（脚本已内置此修复）。

## 通用 CDP 驱动脚本（scripts/cdp_control.py）

- 依赖：`websockets`（`pip install websockets`，或托管 Python `.../envs/default/Scripts/pip install websockets`）。
- 用法示例：
  ```
  python cdp_control.py --port 9333 --action list
  python cdp_control.py --port 9333 --action probe
  python cdp_control.py --port 9333 --action read --target "Antigravity"
  python cdp_control.py --port 9333 --action send --editor ".composer" --text "你好" --send-btn "发送|send"
  python cdp_control.py --port 9333 --action eval --js "document.title"
  ```
- `--target` 用标题 / URL 正则挑页面；`--editor` 是输入框 CSS 选择器；`--send-btn` 是发送按钮文本正则（如 `发送|send|submit`）。

## 启动器模板（scripts/launch_with_cdp.bat）

- 通用 Windows 模板：杀旧实例 → 用绝对路径启动 App 并加 `--remote-debugging-port=%PORT%` → 轮询 `/json/version` 至 200 → 崩溃日志写 `%TEMP%`。
- **必须是 CRLF + 纯 ASCII + 绝对路径**（LF 会被 cmd 误解析成 `'cp' 不是内部或外部命令`）。

## 实操顺序建议

1. 先确认软件有没有 CLI / MCP（看官网文档、看 `mcp.json` 里有没有现成 server）。
2. 有 → 配 MCP，写个最小调用样例自测一通。
3. 没有且是 Electron → 用 `launch_with_cdp.bat` 起带 CDP 端口的实例，再用 `cdp_control.py` 的 `probe` / `read` / `send` 验证能读写界面。
4. 把最终能跑通的调用方式回填到本技能的 resources 区，下次直接复用。

## Resources

- `scripts/cdp_control.py` — 通用 CDP 驱动（list / probe / read / send / eval），内置 React 填字修复。
- `scripts/launch_with_cdp.bat` — CDP 启动器模板（CRLF / ASCII / 绝对路径）。
- `references/gotchas.md` — 三大根因与决策树细化（代理继承、React 受控组件、bat CRLF + 沙箱硬边界）。

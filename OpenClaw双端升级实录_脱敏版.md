# OpenClaw 双端升级实录：Windows 本机 + NAS 从 2026.7.1-2 升到 2026.8.2（含踩坑与解法）

> 本文为公开脱敏版。所有 IP、域名、账号名、密码/Token、API Key、设备 UUID 均已替换为占位符；构建哈希（如 `openclaw-codex-<hash>`）为每机随机生成，无敏感含义，统一用 `<hash>` 表示。

## 0. TL;DR

- 两端（Windows 本机 + Linux NAS）均成功升级到 `2026.8.2`，并验证网关 `/health` 返回 HTTP 200。
- **最大的坑（NAS）**：配置里用了 `openai/gpt-oss-120b`，该模型在 OpenClaw 2.0 会**隐式触发 Codex 运行时插件**；升级后此插件缺 capability 授权，网关一启动就崩，且删了又自动重建，陷入死循环。正解是 `plugins install @openclaw/codex --accept-capabilities`，而不是 `enable`。
- **本机 Windows 的坑**：非管理员账号无法建 peer-link 软链接，导致 deepseek/qqbot 插件 `require('openclaw')` 失败。用启动脚本加 `NODE_PATH` 兜底绕过，无需改系统。
- 升级后浏览器 Control UI 需**一次性设备配对批准**。
- 端到端派小任务实测：gmini 两端口均通过；NAS deepseek 通过；本机 deepseek 修复到"加载层通"（未跑 live 推理，因用户不使用其 DeepSeek API）。

---

## 1. 环境与目标

| 项 | 本机（Windows） | NAS（Linux） |
|---|---|---|
| 系统 | Windows 11，标准账号（非管理员） | Linux（fnOS），用户级 systemd |
| Node | nvm/托管 v22.22.3 | nvm v22.22.3，npm 源 npmmirror |
| 网关进程 | 桌面 `openclaw启动.bat` 拉起 | `systemctl --user openclaw-gateway.service` |
| 全局包路径 | `C:\Users\<user>\AppData\Roaming\npm\node_modules\openclaw` | `<nvm>/lib/node_modules/openclaw` |
| 升级前 | `2026.7.1-2` | `2026.7.1-2` |
| 目标 | npm `latest` = `2026.8.2`（2026-09-01 发布，即 2.0 后的稳定版） | 同左 |

> 为什么升：2026.8.1 是 OpenClaw 2.0（项目史上最大更新），含若干破坏性变更，落后两个稳定版会带来配置兼容性风险。

---

## 2. 2.0 / 2026.8.2 相关破坏性变更（背景）

1. **OpenProse 插件 + `/prose` 命令移除** → 需 `doctor --fix` 清理残留配置键。
2. **OpenAI 路由迁移**：`codex/*` 与 `openai-codex/*` → `openai/*`（provider 配置、已存 session、自动化路由都会改写）。
3. **新增插件 capability consent 机制**：升级后部分插件需重新授权才能加载。
4. **SQLite 会话存储迁移不可逆** → 升级前务必备份 `~/.openclaw`。
5. `tools.sessions.visibility` 默认值在 2.0 后变为 `agent`（共享 agent 要复查会话可见范围）。
6. 新增 `openclaw update repair` / `cleanup` 子命令（`cleanup` 会永久放弃 rollback，须先 dry-run）。

---

## 3. 通用升级流程

```bash
# 1) 备份（排除浏览器缓存等）
cp -r ~/.openclaw ~/.openclaw.backup_$(date +%Y%m%d)_pre820

# 2) 安装目标版本（需 Node >= 22.22.3，否则 EBADENGINE）
npm i -g openclaw@2026.8.2

# 3) 迁移旧配置键（doctor 会自动清理 2.0 不识别的键，把密钥迁入 env.vars）
openclaw doctor --fix

# 4) 授权需 consent 的插件
openclaw plugins enable <id> --accept-capabilities

# 5) 重启网关并验证
systemctl --user restart openclaw-gateway.service   # NAS
# 或重跑桌面启动脚本                                  # 本机
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9090/health   # 期望 200
```

`doctor --fix` 会清理/迁移的键示例：`meta.lastTouchedAt`、`env.DEEPSEEK_API_KEY`、`browser.*`、`commands.ownerDisplay`、`gateway.controlUi.allowInsecureAuth`；密钥统一迁入 `env.vars`。

---

## 4. 踩坑一：NAS 的 Codex 运行时插件崩溃死循环（耗时最久）

### 4.1 现象

NAS 网关升级后**一启动就崩**，日志报：

```
Plugin 'codex' requires capability consent
OpenClaw plugin verification failed; refusing to report the gateway ready.
```

`0.0.0.0:9090` 从不监听。手动删除 `npm/projects/openclaw-codex-<hash>` 后重启，**网关又把它自动重建出来**，陷入「删 → 重建 → 崩 → 再删」的死循环。

### 4.2 为什么会出现

1. OpenClaw 2.0 里，某些模型默认走 **Codex 运行时插件**（`@openclaw/codex`）。源码中 `resolveOpenAIImplicitAgentRuntime` 对 `openai/gpt-oss-120b` 这类模型返回运行时 `"codex"`。
2. 配置里恰好用了 `openai/gpt-oss-120b`（完整引用形如 `nvidia/openai/gpt-oss-120b`）。
3. 网关启动的**模型选择阶段**会调用 `ensureCodexRuntimePluginForModelSelection`：发现持久化的 codex 安装记录 → 触发 `repair` → **重建 `npm/projects/openclaw-codex-*` 工程** → 要求 capability 授权 → 无头环境无交互授权 → 崩溃。
4. 全配置/状态 JSON 里搜不到 "codex" 字面量——它只写死在代码里（`CODEX_RUNTIME_PLUGIN_ID = "codex"` / `npmSpec = "@openclaw/codex"` / `versionBoundToOpenClaw: true`）。所以最初误以为是孤儿目录，没想到是运行时插件在驱动重建。

### 4.3 解法（正路）

```bash
# 1. 停网关
systemctl --user stop openclaw-gateway.service

# 2. 删掉被重建坏的 codex 工程目录
rm -rf ~/.openclaw/npm/projects/openclaw-codex-<hash>

# 3. 用 CLI 正式安装并授权 codex 运行时插件
#    ⚠️ 不要用 enable（runtime plugin 走 npm 工程而非普通 extension 注册表，enable 会报 Plugin not found）
openclaw plugins install @openclaw/codex --accept-capabilities --force
#    输出：Linked peerDependency "openclaw" / Installed plugin: codex

# 4. （Linux 生效）补 peer symlink，让 codex 子进程也能 require('openclaw')
ln -sfn <global-openclaw-dir> ~/.openclaw/npm/projects/openclaw-codex-<hash>/node_modules/openclaw

# 5. 重启
systemctl --user restart openclaw-gateway.service
```

**关键区别**：runtime plugin 走 npm 工程而非普通 extension 注册表，所以 `plugins enable codex` 会报 "Plugin not found"；必须用 `plugins install @openclaw/codex`。

**验证**：重启后 `0.0.0.0:9090` LISTEN，`/health` HTTP 200；`plugins inspect codex` → `status: loaded`、`enabled: true`。耐久测试（再 restart 一次）确认**不再重建崩溃**，闭环彻底打破。

---

## 5. 踩坑二：本机 Windows 非管理员账号的 peer-link 限制

### 5.1 现象

本机 `deepseek` / `qqbot` 插件报 `missing-openclaw-peer-link`，`require('openclaw')` 失败。尝试 `openclaw plugins update deepseek` 卡在 "could not create a plugin-local node_modules/openclaw link"；手动 `mklink /J` 也 `rc=1` 失败。

### 5.2 为什么

Windows 规定：**非管理员账号**创建的软链接 / junction 会被标记为 "untrusted mount point"，任何进程（含 node、git bash）穿越时都会 `Permission denied`。OpenClaw 插件需要在自身 `node_modules/openclaw` 建一个指向全局包的软链接（peer dependency），在受限账号下建不出可穿越的链接。全局包 800MB+，复制法不现实。

> 注意：这个问题**不是升级引入的**，只是 2.0 的插件校验把"缺 peer-link"暴露成了加载失败。网关本体健康（gmini 是内置 provider，不依赖 peer-link，始终可用）。

### 5.3 解法（无需改系统，用 NODE_PATH 兜底）

给网关启动脚本加 `NODE_PATH`，让插件经 `NODE_PATH` 兜底解析 openclaw 核心包，绕过坏软链接：

```bat
@echo off
set NODE_PATH=C:\Users\<user>\AppData\Roaming\npm\node_modules
"<node>" "<global-openclaw>\openclaw.mjs" gateway run --port 9090 --bind lan --token <GATEWAY_TOKEN>
```

实测：重启网关后 `/health` HTTP 200；`plugins inspect deepseek --runtime` → `status: loaded`、`activated: true`、`providerIds: ["deepseek"]`；`require.resolve('openclaw')` 经 NODE_PATH 成功。

> 残留：网关日志仍会打印 `missing-openclaw-peer-link` 警告（**非致命**校验提示，不影响加载/功能）。要彻底消除这条警告，需开 Windows 开发者模式（设置 → 系统 → 开发者选项 → 开发人员模式）后 `openclaw plugins update --all`，或管理员身份跑升级；但那会改动系统，按需选择。

---

## 6. 踩坑三：`update repair` 的误报

本机曾尝试 `openclaw update repair`，报：

```
The update parent owns Gateway activation
```

查源码确认：该命令 spawn 的 doctor 子进程会**自带** `OPENCLAW_UPDATE_PARENT_ALLOWS_GATEWAY_ACTIVATION` 环境变量标记（"update parent owns Gateway activation"），导致即使没有任何网关在跑、也没有孤儿锁，也误判拒修。正路是用 `plugins update --all` / `plugins enable <id> --accept-capabilities`，别在 `update repair` 上浪费时间。

---

## 7. 踩坑四：NAS 的 modelPolicy.allow 白名单

本机用 `gmini/gemini-3.6-flash` 跑小任务成功，但 NAS 上同样命令被 `agents.defaults.modelPolicy.allow` 拦截——NAS 白名单只含 `gmini/gemini-3.5-flash`（不含 3.6-flash）。改用 NAS 允许的 `gmini/gemini-3.5-flash` 即跑通。

> 提醒：升级后要复核各自 `modelPolicy.allow` 与实际可用模型版本是否对齐，否则 CLI/网关派任务会被静默拦截。

---

## 8. 踩坑五：升级后浏览器 Control UI 需一次性配对

浏览器首次连 Control UI 会要求 Gateway 主机一次性批准（设备配对）。在**对应 Gateway 主机**上操作：

```bash
openclaw devices list          # 找到 Pending 状态的设备 ID
openclaw devices approve <device-id>
```

本例中待批准设备来自 NAS Gateway（本机 `devices list` 无此 ID），在 NAS 上 `approve` 后即进入 Paired（角色 operator，scopes 含 admin/read/write/approvals/questions/pairing），浏览器刷新即可用。

---

## 9. 端到端验证（小任务实测）

方法：用 CLI `openclaw infer model run --gateway --model <id> --prompt "..."` 派最小算术任务，验证「网关 → 模型路由 → provider → 响应」全链路。

| 实例 | 模型 | 任务结果 | 结论 |
|---|---|---|---|
| 本机 | `gmini/gemini-3.6-flash` | 42 | ✅ 全链路通 |
| NAS | `gmini/gemini-3.5-flash` | 42 | ✅ 全链路通 |
| NAS | `deepseek/deepseek-v4-flash` | 25 | ✅ provider 通 |
| 本机 | `deepseek`（NODE_PATH 修复后） | loaded | ✅ 加载层通（未跑 live 推理） |

> 说明：本机 deepseek 仅验证到「模块解析 + 插件加载」层。真出字需一次 live 推理并消耗 DeepSeek API，用户明确不使用其 DeepSeek API，故未跑。

---

## 10. 升级后建议复查

1. **模型引用**：`openai/gpt-oss-120b` 现在走 codex 运行时，已验证可加载；其余 provider（nvidia / pplx / gmini 等）按需跑一轮确认。
2. **手机重配对**：未加密 LAN 连接升级后会自动降级为 Limited，手机需 `devices approve` + `nodes approve` 两步重配对。
3. **会话可见范围**：2.0 后 `tools.sessions.visibility` 默认变 `agent`，共享 agent 要复查会话可见范围。

---

## 11. 总结 / 经验教训

- **升级前一定备份 `~/.openclaw`**（SQLite 迁移不可逆）。
- **runtime plugin（如 codex）不能靠 `enable`，要靠 `install`**；它会被模型配置隐式触发并自重建，删目录没用。
- **Windows 非管理员账号的 peer-link 是经典坑**，用 `NODE_PATH` 兜底是最省事的免系统改动方案。
- **`update repair` 在非交互环境会误报**，直接用 `plugins` 子命令。
- **端到端实测（派小任务）比"安装成功"更能暴露问题**——gmini 通不代表 deepseek 插件也通。
- **配置里有 `openai/gpt-oss-*` 模型的，升级 2.0 必踩 codex 运行时插件这一关**，提前准备好 `plugins install @openclaw/codex --accept-capabilities`。

---

*附录：本文所有敏感字段（IP / 域名 / 账号 / 密码 Token / API Key / 设备 UUID）均已脱敏；构建哈希为每机随机值，无敏感含义。*

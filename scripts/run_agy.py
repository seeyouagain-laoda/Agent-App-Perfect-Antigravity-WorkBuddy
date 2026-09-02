#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity 官方引擎直控脚本（agy CLI）。
把 prompt 交给 Antigravity 自己的程序化接口（与 GUI 应用同源），
解析 stream-json 流，整理出「思维链 + 工具调用 + 最终回答」，
落盘成可读报告。等价于：直接跟反重力对话、派活、看思考过程。

依赖：Python 3.11+，以及能联网到 Google 的出口代理（见下方 PROXY）。

用法：
  python run_agy.py "你的任务"                  # 跑一条任务，报告存桌面
  python run_agy.py "你的任务" --effort high     # 指定推理力度
  python run_agy.py --replay verify_run.jsonl    # 离线格式化已有流
"""
import sys, os, json, subprocess, datetime, argparse

# agy 二进制默认安装位置（Windows）。如非默认请改这里或设环境变量 AGY_BIN。
AGY = os.environ.get("AGY_BIN") or os.path.expanduser(
    r"~/AppData/Local/agy/bin/agy.exe"
)
# 出口代理：留空则不使用（直连）。示例（作者 mihomo）：http://127.0.0.1:7897
# 设为环境变量 AGY_PROXY 即可，避免把端口写死在脚本里。
PROXY = os.environ.get("AGY_PROXY", "")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")


def parse_line(line):
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except Exception:
        return None


def run_live(prompt, effort="medium"):
    env = dict(os.environ)
    if PROXY:
        env["HTTP_PROXY"] = PROXY
        env["HTTPS_PROXY"] = PROXY
        env["http_proxy"] = PROXY
        env["https_proxy"] = PROXY
    cmd = [AGY, "-p", prompt, "--output-format", "stream-json",
           "--dangerously-skip-permissions"]
    if effort and effort != "auto":
        cmd += ["--effort", effort]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", env=env, bufsize=1)
    events = []
    raw_path = os.path.join(DESKTOP, "agy_raw_last.jsonl")
    with open(raw_path, "w", encoding="utf-8") as rf:
        for line in proc.stdout:
            rf.write(line)
            ev = parse_line(line)
            if ev:
                events.append(ev)
    err = proc.stderr.read()
    proc.wait()
    return events, err


def format_report(events, prompt, err=""):
    steps = []
    final = ""
    usage = {}
    conv_id = ""
    for ev in events:
        e = ev.get("event")
        if e == "init":
            conv_id = ev.get("conversation_id", "")
        elif e == "step_update":
            su = ev.get("step_update", {})
            st = su.get("step_type")
            txt = su.get("text_delta", "")
            if st == "agent_response":
                if txt:
                    steps.append(("回答", txt))
            elif st == "user_input":
                pass
            else:
                label = {"tool_use": "工具调用", "tool_call": "工具调用",
                         "reasoning": "思考", "tool_result": "工具结果"}.get(st, st or "步骤")
                if txt:
                    steps.append((label, txt))
                else:
                    steps.append((label, f"（{st} 执行）"))
        elif e == "result":
            r = ev.get("result", {})
            final = r.get("response", "")
            usage = r.get("usage", {})
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L = []
    L.append("# Antigravity 直控验证报告\n")
    L.append(f"- 时间：{now}")
    L.append(f"- 会话 ID：`{conv_id}`")
    L.append(f"- 任务：{prompt}\n")
    L.append("## 思维链 / 过程\n")
    if steps:
        for i, (k, v) in enumerate(steps, 1):
            L.append(f"**{i}. [{k}]** {v}")
    else:
        L.append("（该任务为简单问答，未触发独立工具步骤）")
    L.append("\n## 最终回答\n")
    L.append(final if final else "（无 result.response）")
    if usage:
        L.append("\n## 用量\n")
        L.append(f"- 输入 tokens：{usage.get('input_tokens','-')}")
        L.append(f"- 输出 tokens：{usage.get('output_tokens','-')}")
        L.append(f"- 思考 tokens：{usage.get('thinking_tokens','-')}")
        L.append(f"- 总 tokens：{usage.get('total_tokens','-')}")
    if err.strip():
        L.append("\n## stderr（若有）\n")
        L.append("```\n" + err.strip()[:2000] + "\n```")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--replay", default="")
    args = ap.parse_args()
    if args.replay:
        events = []
        with open(args.replay, encoding="utf-8") as f:
            for line in f:
                ev = parse_line(line)
                if ev:
                    events.append(ev)
        prompt = args.prompt or "（replay）"
        rep = format_report(events, prompt)
    else:
        if not args.prompt:
            print("用法: python run_agy.py \"任务\" [--effort low|medium|high]")
            sys.exit(1)
        print(f"[run_agy] 派活中: {args.prompt[:40]} ...")
        events, err = run_live(args.prompt, args.effort)
        rep = format_report(events, args.prompt, err)
    ts = datetime.datetime.now().strftime("%H%M%S")
    out = os.path.join(DESKTOP, f"AGY直控验证_{ts}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(rep)
    print(rep)
    print(f"\n[run_agy] 报告已存: {out}")


if __name__ == "__main__":
    main()

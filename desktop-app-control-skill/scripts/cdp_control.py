#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic CDP (Chrome DevTools Protocol) driver for Electron / Chromium desktop apps.

Routes:
  list   - enumerate open pages/targets (GET /json/list)
  probe  - check CDP endpoint alive      (GET /json/version)
  read   - dump visible text of a page   (Runtime.evaluate document.body.innerText)
  send   - type text into an editor, then click the send button
  eval   - run an arbitrary JS expression in the page

Dependency:
  websockets  (pip install websockets)
  or managed env: <py>/envs/default/Scripts/pip install websockets

Examples:
  python cdp_control.py --port 9333 --action list
  python cdp_control.py --port 9333 --action probe
  python cdp_control.py --port 9333 --action read --target "Antigravity"
  python cdp_control.py --port 9333 --action send --editor ".composer" --text "hello" --send-btn "发送|send"
  python cdp_control.py --port 9333 --action eval --js "document.title"
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

CDP_HTTP = "http://127.0.0.1:{port}"


def http_get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8", "replace")


def list_targets(port):
    data = json.loads(http_get(CDP_HTTP.format(port=port) + "/json/list"))
    out = []
    for t in data:
        out.append({
            "type": t.get("type"),
            "title": t.get("title"),
            "url": t.get("url"),
            "webSocketDebuggerUrl": t.get("webSocketDebuggerUrl"),
        })
    return out


def pick_target(targets, target_filter=None):
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        pages = [t for t in targets if t.get("webSocketDebuggerUrl")]
    if not pages:
        return None
    if not target_filter:
        return pages[0]
    import re
    rx = re.compile(target_filter, re.IGNORECASE)
    for t in pages:
        if rx.search(t.get("title") or "") or rx.search(t.get("url") or ""):
            return t
    return pages[0]


def _connect(url):
    try:
        import websockets  # lazy import so --help works without the dep
    except ImportError:
        sys.stderr.write(
            "[ERROR] 缺少依赖 websockets。请先安装：\n"
            "  pip install websockets\n"
            "  或托管 Python：<py>/envs/default/Scripts/pip install websockets\n"
        )
        sys.exit(2)
    return websockets


def cdp_eval(url, expression, timeout=15):
    """Connect to a target ws, run Runtime.evaluate, return the JSON result value."""
    websockets = _connect(url)
    import asyncio

    async def _run():
        async with websockets.connect(url, max_size=None, open_timeout=timeout) as ws:
            msg = json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True,
                           "awaitPromise": True},
            })
            await ws.send(msg)
            while True:
                raw = await ws.recv()
                obj = json.loads(raw)
                if obj.get("id") == 1:
                    return obj

    obj = asyncio.run(_run())
    if "error" in obj:
        return {"__error__": obj["error"]}
    result = obj.get("result", {}).get("result", {})
    if "exceptionDetails" in obj.get("result", {}):
        return {"__exception__": obj["result"]["exceptionDetails"]}
    return result.get("value")


def build_type_js(selector, text):
    return (
        "(function(){"
        "  var ed = document.querySelector(%s) || document.activeElement;"
        "  if(!ed) return 'NO_EDITOR';"
        "  ed.focus();"
        "  var sel = window.getSelection();"
        "  var range = document.createRange();"
        "  range.selectNodeContents(ed);"
        "  range.collapse(false);"
        "  sel.removeAllRanges();"
        "  sel.addRange(range);"
        "  document.execCommand('insertText', false, %s);"
        "  return 'TYPED';"
        "})()"
    ) % (json.dumps(selector), json.dumps(text))


def build_click_js(regex_src):
    return (
        "(function(){"
        "  var re = new RegExp(%s, 'i');"
        "  var nodes = Array.prototype.slice.call(document.querySelectorAll('button,a,[role=button]'));"
        "  var b = nodes.filter(function(x){"
        "    return re.test((x.textContent||'') ) || re.test((x.getAttribute('aria-label')||''));"
        "  })[0];"
        "  if(!b) return 'NO_SEND_BTN';"
        "  b.click();"
        "  return 'CLICKED:' + (b.textContent||'').trim();"
        "})()"
    ) % json.dumps(regex_src)


def read_text(url):
    return cdp_eval(url, "document.body ? document.body.innerText : document.title")


def send_message(url, editor, text, send_btn):
    typed = cdp_eval(url, build_type_js(editor, text))
    if typed != "TYPED":
        return {"type": typed, "click": None}
    clicked = cdp_eval(url, build_click_js(send_btn))
    return {"type": typed, "click": clicked}


def main():
    ap = argparse.ArgumentParser(description="Generic CDP driver for Electron/Chromium desktop apps")
    ap.add_argument("--port", type=int, default=9333, help="CDP remote-debugging port")
    ap.add_argument("--action", required=True, choices=["list", "probe", "read", "send", "eval"])
    ap.add_argument("--target", default=None, help="title/url regex to pick the page")
    ap.add_argument("--editor", default=None, help="CSS selector of the input box (send action)")
    ap.add_argument("--text", default=None, help="text to type (send action)")
    ap.add_argument("--send-btn", default=None, help="send-button text regex (send action)")
    ap.add_argument("--js", default=None, help="JS expression (eval action)")
    args = ap.parse_args()

    if args.action == "list":
        targets = list_targets(args.port)
        print(json.dumps(targets, ensure_ascii=False, indent=2))
        return

    if args.action == "probe":
        try:
            ver = json.loads(http_get(CDP_HTTP.format(port=args.port) + "/json/version"))
            print(json.dumps(ver, ensure_ascii=False, indent=2))
        except Exception as e:
            print("[ERROR] CDP not reachable on port %d: %s" % (args.port, e))
            sys.exit(3)
        return

    # actions below need a websocket target
    targets = list_targets(args.port)
    tgt = pick_target(targets, args.target)
    if not tgt:
        print("[ERROR] no CDP target found on port %d" % args.port)
        sys.exit(4)
    url = tgt["webSocketDebuggerUrl"]

    if args.action == "read":
        print(read_text(url))
    elif args.action == "eval":
        if not args.js:
            print("[ERROR] --js required for eval")
            sys.exit(5)
        print(cdp_eval(url, args.js))
    elif args.action == "send":
        if not args.editor or not args.text or not args.send_btn:
            print("[ERROR] send needs --editor, --text, --send-btn")
            sys.exit(6)
        print(json.dumps(send_message(url, args.editor, args.text, args.send_btn),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify agy/Antigravity UI is localized to Chinese after a CN patch injection.

Resolves the CDP port live, connects, counts Chinese chars + key localized
strings in document.body.innerText.

ALWAYS has recv timeouts: an unguarded CDP recv() hangs forever on a stale page.

Usage: python agy_verify_cn.py
"""
import os, sys, json, re, asyncio, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agy_model import PORT, http_get

KEYS = ["新对话", "对话历史", "定时任务", "设置", "文件", "视图", "窗口", "项目", "退出", "安装 IDE"]


async def read_body(ws):
    import websockets
    async with websockets.connect(ws, max_size=None, open_timeout=10) as c:
        mid = 1
        await c.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
            "params": {"expression": "document.body?document.body.innerText:''",
                       "returnByValue": True, "awaitPromise": True}}))
        while True:
            msg = json.loads(await asyncio.wait_for(c.recv(), 12))
            if msg.get("id") == mid:
                return msg.get("result", {}).get("result", {}).get("value") or ""


def main():
    targets = json.loads(http_get("http://127.0.0.1:%s/json/list" % PORT))
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    # exclude the "Loading Antigravity" splash page
    pages = [t for t in pages if "Antigravity" in (t.get("title") or "")] or pages
    if not pages:
        print("NO_CDP_TARGET"); return 2
    t = pages[0]
    print("TARGET:", t.get("title"), t.get("url"))
    txt = asyncio.run(asyncio.wait_for(read_body(t["webSocketDebuggerUrl"]), 50)) or ""
    cn = len(re.findall(r"[一-鿿]", txt))
    hit = [k for k in KEYS if k in txt]
    print("CN_CHARS:", cn, "LEN:", len(txt))
    print("HIT:", hit)
    print("RESULT:", "CN_OK" if hit else "CN_FAIL")
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main())

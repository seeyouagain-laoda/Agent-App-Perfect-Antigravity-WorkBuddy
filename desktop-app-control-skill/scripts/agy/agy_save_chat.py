#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 agy 对话 innerText 提取最后一个完整 HTML 文档并落盘（agy 未自动写盘时的兜底）。"""
import os
import sys
import re
import json
import asyncio

sys.path.insert(0, "C:/Users/user/.workbuddy")
from agy_model import CDP, http_get, PORT

OUT = os.environ.get("AGY_OUT", r"C:/Users/user/Desktop/agy网页3_模型选型看板.html")


async def main():
    t = json.loads(http_get(f"http://127.0.0.1:{PORT}/json/list"))
    p = [x for x in t if x.get("webSocketDebuggerUrl")]
    if not p:
        print("NO_CDP")
        return
    async with CDP(p[0]["webSocketDebuggerUrl"]) as cdp:
        txt = await cdp.ev("document.body?document.body.innerText:''")
        if not isinstance(txt, str):
            print("NO_TEXT type=%s" % type(txt))
            return
        blocks = re.findall(r"<!DOCTYPE html>.*?</html>", txt, re.S | re.I)
        if not blocks:
            blocks = re.findall(r"<html[\s\S]*?</html>", txt, re.S | re.I)
        if not blocks:
            print("NO_HTML_BLOCK  (innerText len=%d)" % len(txt))
            return
        html = blocks[-1].strip()
        html = re.sub(r"^```(?:html)?\s*", "", html)
        html = re.sub(r"\s*```$", "", html)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(html)
        print("SAVED bytes=%d  head=%r" % (len(html), html[:80]))
        print("has_doctype=%s has_html_close=%s" % (html.lstrip().lower().startswith("<!doctype html>") or "<html" in html[:20].lower(), "</html>" in html[-20:].lower()))


if __name__ == "__main__":
    asyncio.run(main())

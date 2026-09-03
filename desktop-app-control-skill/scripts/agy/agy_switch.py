#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接管 agy 当前生成中的网页，执行：Stop -> 切模型 -> 继续，并监控结果。

用于验证用户需求："写一个网页停止的时候，切换一下模型，看它能不能继续，还是继续报错"。
所有操作在同一个持久 CDP 会话内完成。
"""
import os
import sys
import json
import time
import asyncio
import glob
import shutil

sys.path.insert(0, "C:/Users/user/.workbuddy")
from agy_model import CDP, http_get, PORT, chip_info, open_picker

OUT = os.environ.get("AGY_OUT", r"C:/Users/user/Desktop/agy网页3_模型选型看板.html")
TARGET = sys.argv[1] if len(sys.argv) > 1 else "Gemini 3.7 FlashMediumFast"

STOP_JS = ("(function(){var bs=[].slice.call(document.querySelectorAll('button,[role=button]'));"
           "return bs.filter(function(b){var s=(b.getAttribute('aria-label')||'')+'|'+(b.innerText||'');"
           "return /stop execution|cancel \\(ctrl\\+d\\)|停止/i.test(s);}).length;})()")


def click_js(rx):
    return ("(function(){var re=new RegExp(%s,'i');"
            "var nodes=Array.prototype.slice.call(document.querySelectorAll('button,a,[role=button]'));"
            "var b=nodes.filter(function(x){return re.test((x.textContent||''))||re.test((x.getAttribute('aria-label')||''));})[0];"
            "if(!b)return'NO_BTN';b.click();return'CLICKED:'+(b.textContent||'').trim();})()"
            ) % json.dumps(rx)


def type_js(text):
    return ("(function(){var ed=document.querySelector('[aria-label=\"Message input\"]')||document.activeElement;"
            "if(!ed)return'NO_EDITOR';ed.focus();"
            "var s=window.getSelection();var r=document.createRange();"
            "r.selectNodeContents(ed);r.collapse(false);s.removeAllRanges();s.addRange(r);"
            "document.execCommand('insertText',false,%s);return'TYPED';})()") % json.dumps(text)


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


async def send(cdp, text):
    log("type=%s" % await cdp.ev(type_js(text)))
    for _ in range(24):
        st = await cdp.ev("(function(){var b=document.querySelector('[aria-label=\"Send message\"]');"
                          "return b?(b.disabled?'DIS':'OK'):'NONE';})()")
        if st == "OK":
            break
        await asyncio.sleep(0.5)
    log("send=%s" % await cdp.ev(click_js("Send message")))


async def wait_generating(cdp, limit=90):
    t0 = time.time()
    while time.time() - t0 < limit:
        if await cdp.ev(STOP_JS):
            log("generating (stop btn present)")
            return True
        await asyncio.sleep(3)
    log("WARN: never saw stop button")
    return False


async def monitor(cdp, timeout, tag):
    t0 = time.time()
    seen = False
    idle = 0
    errors = 0
    retries = 0
    perm = 0
    while time.time() - t0 < timeout:
        await asyncio.sleep(5)
        n = await cdp.ev(STOP_JS)
        if n:
            seen = True
            idle = 0
        elif seen:
            idle += 1
        elif time.time() - t0 > 45:
            seen = True
        e = await cdp.ev("(function(){var b=document.body?document.body.innerText:'';var t=b.slice(-2500);"
                         "var bs=[].slice.call(document.querySelectorAll('button,[role=button]'));"
                         "var retry=bs.filter(function(x){var s=(x.getAttribute('aria-label')||'')+'|'+(x.innerText||'');"
                         "return /retry|重试/i.test(s);}).length;"
                         "return JSON.stringify({retry:retry,err:/EOF|error|failed|失败|出错|unavailable|quota|limit|rate/i.test(t)});})()") or {}
        if e.get("retry"):
            retries += 1
            log("[%s] RETRY BTN -> %s" % (tag, await cdp.ev(click_js("retry|重试"))))
            continue
        if e.get("err"):
            errors += 1
        pn = await cdp.ev("(function(){var els=[].slice.call(document.querySelectorAll('[role=button]'));"
                          "return els.filter(function(x){return /copy-item|always allow|run command|submit|允许|确认/i.test(x.textContent||'');}).length;})()")
        if pn:
            perm += 1
            if perm >= 2:
                log("[%s] perm UI -> Submit: %s" % (tag, await cdp.ev(click_js("submit"))))
                perm = 0
        if os.path.exists(OUT) and os.path.getsize(OUT) > 4000:
            log("[%s] OUTPUT READY %d bytes" % (tag, os.path.getsize(OUT)))
            return {"end": "file", "errors": errors, "retries": retries}
        if idle >= 3:
            log("[%s] generation ended (stop absent 15s)" % tag)
            return {"end": "idle", "errors": errors, "retries": retries}
    return {"end": "timeout", "errors": errors, "retries": retries}


async def main():
    t = json.loads(http_get(f"http://127.0.0.1:{PORT}/json/list"))
    p = [x for x in t if x.get("webSocketDebuggerUrl")]
    if not p:
        log("NO_CDP")
        return
    async with CDP(p[0]["webSocketDebuggerUrl"]) as cdp:
        before = [h["t"] for h in await chip_info(cdp)]
        log("MODEL BEFORE = %s" % (before[-1] if before else "?"))
        pre = await cdp.ev("document.body?document.body.innerText.length:0")

        # 1) Stop the in-flight generation
        log("STOP -> %s" % await cdp.ev(click_js("Stop execution|Cancel \\(Ctrl\\+D\\)")))
        await asyncio.sleep(4)
        still = await cdp.ev(STOP_JS)
        log("after-stop stop_btn=%s (0 => stopped)" % still)

        # 2) switch model mid-conversation
        rows = await open_picker(cdp)
        if not rows:
            log("SWITCH FAILED: picker never opened")
            return
        hit = next((r for r in rows if TARGET.lower() in r["t"].lower()), None)
        if not hit:
            log("SWITCH FAILED: no row matches %r in %s" % (TARGET, [r["t"] for r in rows]))
            return
        log("clicking model row %r" % hit["t"])
        await cdp.click(hit["x"], hit["y"])
        await asyncio.sleep(1.6)
        after = [h["t"] for h in await chip_info(cdp)]
        now = after[-1] if after else "?"
        log("MODEL AFTER = %r  switched=%s" % (now, TARGET.lower() in now.lower()))

        # 3) ask it to continue with the NEW model
        await send(cdp, "继续。刚才被中断了，请用当前模型接着把上面的网页写完，"
                        "并用 PowerShell Set-Content 保存到 %s（UTF8）。" % OUT)
        gen = await wait_generating(cdp, 90)
        log("resumed_generation=%s" % gen)
        res = await monitor(cdp, 420, "after-switch")
        post = await cdp.ev("document.body?document.body.innerText.length:0")
        log("transcript grew: %s -> %s (+%s chars)" % (pre, post, (post or 0) - (pre or 0)))
        log("RESULT=%s" % json.dumps(res, ensure_ascii=False))
        log("FILE exists=%s size=%s" % (os.path.exists(OUT),
                                        os.path.getsize(OUT) if os.path.exists(OUT) else 0))
        if not os.path.exists(OUT):
            base = os.path.expanduser("~/.gemini/antigravity/brain")
            cands = [c for c in glob.glob(os.path.join(base, "**", os.path.basename(OUT)), recursive=True)
                     if os.path.isfile(c)]
            if cands:
                cands.sort(key=os.path.getmtime, reverse=True)
                shutil.copy2(cands[0], OUT)
                log("FALLBACK COPY from brain: %s" % cands[0])


if __name__ == "__main__":
    asyncio.run(main())

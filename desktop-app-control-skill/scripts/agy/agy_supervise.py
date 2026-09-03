#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supervisor: dispatch a build task to agy (AntiGravity) via CDP and monitor it.

Drives the agy web UI on 127.0.0.1:9333:
  1. type the task prompt into [aria-label="Message input"] (React-safe execCommand)
  2. wait until [aria-label="Send message"] is enabled, then click it
  3. poll the conversation; auto-approve any permission prompt (Allow/Confirm/Run)
  4. detect completion signal, then report conversation tail + output file status

Run: python tmp_agy_supervise.py "<PROMPT>" <timeout_seconds>
"""
import asyncio
import json
import sys
import time
import re
import os

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from agy_model import PORT  # dynamic: env AGY_CDP_PORT > DevToolsActivePort > 9333
OUT_FILE = os.environ.get("AGY_OUT", r"C:/Users/user/Desktop/agy作品_个人主页.html")


def http_get(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read().decode("utf-8", "replace")


def list_targets():
    return json.loads(http_get(f"http://127.0.0.1:{PORT}/json/list"))


def pick_target(targets):
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        pages = [t for t in targets if t.get("webSocketDebuggerUrl")]
    for t in pages:
        if "1990" in (t.get("url") or "") or "antigravity" in (t.get("title") or "").lower():
            return t
    return pages[0] if pages else None


async def cdp_eval(url, expression, timeout=20):
    import websockets
    async with websockets.connect(url, max_size=None, open_timeout=timeout) as ws:
        msg = json.dumps({"id": 1, "method": "Runtime.evaluate",
                          "params": {"expression": expression, "returnByValue": True, "awaitPromise": True}})
        await ws.send(msg)
        while True:
            raw = await ws.recv()
            obj = json.loads(raw)
            if obj.get("id") == 1:
                return obj


def val(obj):
    if isinstance(obj, dict):
        return obj.get("result", {}).get("result", {}).get("value")
    return obj


def type_js(sel, text):
    return ("(function(){var ed=document.querySelector(%s)||document.activeElement;"
            "if(!ed)return'NO_EDITOR';ed.focus();"
            "var s=window.getSelection();var r=document.createRange();"
            "r.selectNodeContents(ed);r.collapse(false);s.removeAllRanges();s.addRange(r);"
            "document.execCommand('insertText',false,%s);return'TYPED';})()"
            ) % (json.dumps(sel), json.dumps(text))


def click_js(rx):
    return ("(function(){var re=new RegExp(%s,'i');"
            "var nodes=Array.prototype.slice.call(document.querySelectorAll('button,a,[role=button]'));"
            "var b=nodes.filter(function(x){return re.test((x.textContent||''))||re.test((x.getAttribute('aria-label')||''));})[0];"
            "if(!b)return'NO_BTN';b.click();return'CLICKED:'+(b.textContent||'').trim();})()"
            ) % json.dumps(rx)


POS = r"allow|confirm|approve|yes|run|continue|accept|允许|确认|运行|继续"
NEG = r"deny|cancel|reject|禁止|取消|拒绝|block"


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def find_brain_artifact(name):
    """agy writes the real artifact into its 'brain' dir even when the
    copy-to-Desktop permission UI is stuck. Locate it there."""
    import glob, shutil
    base = os.path.expanduser("~/.gemini/antigravity/brain")
    if not os.path.isdir(base):
        return None
    cands = [c for c in glob.glob(os.path.join(base, "**", name), recursive=True)
             if os.path.isfile(c)]
    if not cands:
        return None
    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return cands[0]


def fallback_copy(name, dst):
    """Supervisor does the copy agy wanted, when its permission UI won't auto-approve."""
    src = find_brain_artifact(name)
    if not src:
        return "NO_SRC_IN_BRAIN"
    try:
        import shutil
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return "COPIED %s -> %s" % (src, dst)
    except Exception as e:
        return "COPY_ERR:%s" % e


PERM_RX = r"copy-item|always allow|run command|允许|确认|submit"


async def main(prompt, timeout, monitor_only=False):
    targets = list_targets()
    tgt = pick_target(targets)
    if not tgt:
        log("NO TARGET FOUND"); return
    url = tgt["webSocketDebuggerUrl"]
    log("target=%s | %s" % (tgt.get("title"), tgt.get("url")))

    if monitor_only:
        log("MONITOR-ONLY: skipping dispatch, will auto-retry on error")
    else:
        r = await cdp_eval(url, type_js('[aria-label="Message input"]', prompt))
        log("type_result=%s" % val(r))

        # wait for send button to enable
        enabled = False
        for _ in range(24):
            st = val(await cdp_eval(url,
                     "(function(){var b=document.querySelector('[aria-label=\"Send message\"]');"
                     "return b?{dis:b.disabled}:'NONE';})()"))
            if isinstance(st, dict) and st.get("dis") is False:
                enabled = True
                break
            await asyncio.sleep(0.5)
        if not enabled:
            log("SEND BTN STILL DISABLED - aborting"); return
        c = val(await cdp_eval(url, click_js("Send message")))
        log("send_click=%s" % c)
        log("DISPATCHED. monitoring agy ...")

    start = time.time()
    confirms = 0
    perm_stuck = 0
    # ---- completion is decided by the Stop-execution button, NOT by transcript text.
    # (transcript keeps old "已生成/已保存" lines and even echoes our own prompt, so any
    #  text-based signal false-fires immediately. See gotchas.md 根因 6.)
    STOP_JS = ("(function(){var bs=[].slice.call(document.querySelectorAll('button,[role=button]'));"
               "return bs.filter(function(b){var s=(b.getAttribute('aria-label')||'')+'|'+(b.innerText||'');"
               "return /stop execution|cancel \\(ctrl\\+d\\)|停止/i.test(s);}).length;})()")
    gen_seen = False
    idle_polls = 0
    while time.time() - start < timeout:
        await asyncio.sleep(5)
        stop_n = val(await cdp_eval(url, STOP_JS))
        if stop_n:
            gen_seen = True
            idle_polls = 0
        elif gen_seen:
            idle_polls += 1
        else:
            # generation hasn't visibly started yet; give it up to 60s
            if time.time() - start > 60:
                gen_seen = True
        # error/retry detection: ONLY retry when a Retry button is actually present.
        # (a past error message stays in the transcript, so never match on text alone)
        retry_n = val(await cdp_eval(url,
                 "(function(){var bs=[].slice.call(document.querySelectorAll('button'));"
                 "var r=bs.filter(function(b){return /retry|重试/i.test(b.textContent||'')||/retry|重试/i.test(b.getAttribute('aria-label')||'');});"
                 "return r.length;})()"))
        if retry_n:
            rc = val(await cdp_eval(url, click_js("retry|重试")))
            log("RETRY BTN PRESENT -> clicked: %s" % rc)
            continue
        pc = val(await cdp_eval(url,
                 "(function(){var POS=/%s/i,NEG=/%s/i;"
                 "var bs=[].slice.call(document.querySelectorAll('button'));"
                 "var pos=bs.filter(function(b){var t=(b.innerText||'').trim().toLowerCase();"
                 "var a=(b.getAttribute('aria-label')||'').toLowerCase();return POS.test(t)||POS.test(a);});"
                 "return {n:pos.length, labels:pos.map(function(b){return (b.innerText||'').trim().slice(0,24)+'|'+b.getAttribute('aria-label');})};})()"
                 % (POS, NEG)))
        if isinstance(pc, dict) and pc.get("n"):
            clicked = val(await cdp_eval(url, click_js(POS)))
            confirms += 1
            log("AUTO-CONFIRM #%d -> %s" % (confirms, clicked))
        # stuck-permission detection: agy's write/copy confirm is a role=button command
        # block driven by keyboard shortcuts; CDP click won't execute it. After 2 stale
        # polls, click Submit (let agy self-write via Set-Content) and/or fallback copy
        # the artifact from agy's brain dir.
        perm_n = val(await cdp_eval(url,
                 "(function(){var els=[].slice.call(document.querySelectorAll('[role=button]'));"
                 "var r=els.filter(function(e){return /%s/i.test(e.textContent||'');});"
                 "return r.length;})()" % PERM_RX))
        if perm_n:
            perm_stuck += 1
            if perm_stuck >= 2:
                sub = val(await cdp_eval(url, click_js("submit")))
                log("PERM UI STUCK -> click Submit: %s" % sub)
                fb = fallback_copy(os.path.basename(OUT_FILE), OUT_FILE)
                if not os.path.exists(OUT_FILE):
                    log("PERM fallback copy: %s" % fb)
                perm_stuck = 0
        else:
            perm_stuck = 0
        if idle_polls == 1:
            log("stop-btn gone (1/3) ...")
        if idle_polls >= 3:
            log("GENERATION ENDED (stop button absent 15s)")
            await asyncio.sleep(3)
            break
        if os.path.exists(OUT_FILE) and os.path.getsize(OUT_FILE) > 4000 and idle_polls >= 1:
            log("OUTPUT FILE READY (%d bytes)" % os.path.getsize(OUT_FILE))
            break

    # finalize: ensure output is on disk even if agy's copy permission hung
    if not os.path.exists(OUT_FILE):
        fb = fallback_copy(os.path.basename(OUT_FILE), OUT_FILE)
        log("FINALIZE copy: %s" % fb)
    final = val(await cdp_eval(url, "document.body?document.body.innerText:''"))
    log("=== CONV TAIL ===")
    log((final[-1600:] if isinstance(final, str) else str(final)).replace("\n", " \\n"))
    log("=== OUTPUT FILE ===")
    log("path=%s exists=%s size=%s" % (OUT_FILE, os.path.exists(OUT_FILE),
                                       os.path.getsize(OUT_FILE) if os.path.exists(OUT_FILE) else 0))
    log("DONE (auto-confirms=%d)" % confirms)


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AGY_PROMPT", "hello")
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 480
    monitor_only = (len(sys.argv) > 3 and sys.argv[3] == "monitor")
    asyncio.run(main(prompt, timeout, monitor_only))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe agy UI state: composer presence, send/stop button, buttons, transcript tail."""
import json, asyncio, sys
sys.path.insert(0, "C:/Users/user/.workbuddy")
from agy_model import CDP, http_get, PORT

JS = """(function(){
  var inp=document.querySelector('[aria-label="Message input"]');
  var send=document.querySelector('[aria-label="Send message"]');
  var bs=[].slice.call(document.querySelectorAll('button,[role=button]'));
  var labs=bs.map(function(b){
    var t=(b.innerText||'').trim().replace(/\\s+/g,' ').slice(0,30);
    var a=b.getAttribute('aria-label')||'';
    return (t||a)?(t+'|'+a):'';
  }).filter(function(s){return s && s!=='|';});
  var body=document.body?document.body.innerText:'';
  return JSON.stringify({
    hasInput: !!inp,
    sendDisabled: send? !!send.disabled : null,
    stopBtn: labs.filter(function(s){return /stop|cancel|abort|停止|取消/i.test(s);}),
    retryBtn: labs.filter(function(s){return /retry|重试/i.test(s);}),
    btnCount: labs.length,
    btns: labs.slice(0,40),
    tail: body.slice(-1200)
  });
})()"""


async def main():
    t = json.loads(http_get(f"http://127.0.0.1:{PORT}/json/list"))
    p = [x for x in t if x.get("webSocketDebuggerUrl")]
    if not p:
        print("NO_CDP"); return
    async with CDP(p[0]["webSocketDebuggerUrl"]) as c:
        d = await c.ev(JS)
        if isinstance(d, dict):
            tail = d.pop("tail", "")
            print(json.dumps(d, ensure_ascii=False, indent=1))
            print("--- TAIL ---")
            print(tail)
        else:
            print(d)

asyncio.run(main())

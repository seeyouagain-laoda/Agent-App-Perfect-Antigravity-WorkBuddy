#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agy / Antigravity model switcher via CDP real-mouse events.

Key gotchas encoded here:
  1. The model chip is a Radix component -> JS .click() / synthetic MouseEvent do
     NOT open it. Only CDP Input.dispatchMouseEvent works.
  2. There are several DOM nodes whose textContent equals the chip label; the one
     that actually opens the picker is the LOWEST on screen (composer chip).
  3. Menu rows are role="menuitem" (NOT role="option").
  4. Must click the DEEPEST element matching the target text, otherwise the
     bounding-rect center of an outer wrapper lands outside the menu.
  5. One persistent websocket for the whole flow; reconnecting per command is
     slow and racy.

Usage:
  python agy_model.py list
  python agy_model.py select "Gemini 3.1 Pro"
  python agy_model.py chip
"""
import json
import asyncio
import sys

def _cdp_port():
    """CDP port: env AGY_CDP_PORT > Antigravity DevToolsActivePort > 9333.

    agy picks a NEW port on every launch (observed 9333 -> 11182), so a hardcoded
    port silently breaks after any restart. APPDATA is not always exported to
    child processes (e.g. under Git Bash), so try several bases.
    """
    import os as _os
    env = _os.environ.get("AGY_CDP_PORT", "").strip()
    if env.isdigit():
        return int(env)
    bases = []
    for b in (_os.environ.get("APPDATA"), _os.path.expandvars("%APPDATA%"),
              _os.path.join(_os.path.expanduser("~"), "AppData", "Roaming")):
        if b and b not in bases:
            bases.append(b)
    for b in bases:
        try:
            with open(_os.path.join(b, "Antigravity", "DevToolsActivePort")) as f:
                first = f.readline().strip()
            if first.isdigit():
                return int(first)
        except Exception:
            continue
    return 9333


PORT = _cdp_port()
CHIP_RX = r"Gemini|Claude|GPT-OSS"


def http_get(url):
    """GET bypassing any proxy: 127.0.0.1 must not go through the system proxy
    (a proxy turns a dead port into a misleading HTTP 502 instead of ECONNREFUSED)."""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener.open(req, timeout=8) as r:
        return r.read().decode("utf-8", "replace")


class CDP:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.c = None
        self._id = 0

    async def __aenter__(self):
        import websockets
        self.c = await websockets.connect(self.ws_url, max_size=None, open_timeout=20)
        return self

    async def __aexit__(self, *a):
        try:
            await self.c.close()
        except Exception:
            pass

    async def send(self, method, params=None, timeout=20):
        self._id += 1
        mid = self._id
        await self.c.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self.c.recv(), timeout=timeout)
            obj = json.loads(raw)
            if obj.get("id") == mid:
                return obj

    async def ev(self, expr, timeout=20):
        r = await self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout)
        v = r.get("result", {}).get("result", {}).get("value")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
        return v

    async def click(self, x, y):
        for typ in ("mousePressed", "mouseReleased"):
            await self.send("Input.dispatchMouseEvent",
                            {"type": typ, "x": x, "y": y, "button": "left", "clickCount": 1})

    async def key(self, k, code):
        for typ in ("keyDown", "keyUp"):
            await self.send("Input.dispatchKeyEvent",
                            {"type": typ, "key": k, "windowsVirtualKeyCode": code,
                             "nativeVirtualKeyCode": code})


JS_CHIP_LABEL = """(function(){
  var rx=/^(Gemini|Claude|GPT-OSS)[^\\n]{0,40}$/;
  var nodes=[].slice.call(document.querySelectorAll('*'));
  var hits=nodes.filter(function(e){
    var t=(e.textContent||'').trim();
    if(!rx.test(t)) return false;
    if(t.length>45) return false;
    // deepest: no child carries the same text
    for(var i=0;i<e.children.length;i++){
      if((e.children[i].textContent||'').trim()===t) return false;
    }
    var r=e.getBoundingClientRect();
    return r.width>0 && r.height>0;
  }).map(function(e){
    var r=e.getBoundingClientRect();
    return {t:(e.textContent||'').trim(), top:Math.round(r.top),
            x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
  });
  hits.sort(function(a,b){return a.top-b.top;});
  return JSON.stringify(hits);
})()"""

JS_MENU = """(function(){
  var rows=[].slice.call(document.querySelectorAll('[role=menuitem],[role=option],[role=menuitemradio]'));
  var out=rows.map(function(o){
    var r=o.getBoundingClientRect();
    return {t:(o.textContent||'').trim(),
            x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2),
            w:Math.round(r.width), h:Math.round(r.height)};
  }).filter(function(o){return o.t.length>0 && o.t.length<60 && o.w>0;});
  return JSON.stringify(out);
})()"""


async def chip_info(cdp):
    """Return list of candidate chip nodes (sorted top asc)."""
    hits = await cdp.ev(JS_CHIP_LABEL)
    return hits if isinstance(hits, list) else []


async def open_picker(cdp, tries=6):
    """Real-mouse click the lowest chip node until the menu shows rows."""
    for attempt in range(1, tries + 1):
        hits = await chip_info(cdp)
        if not hits:
            print("[open] NO_CHIP", flush=True)
            return []
        chip = hits[-1]          # lowest on screen = composer chip
        await cdp.click(chip["x"], chip["y"])
        await asyncio.sleep(1.4)
        rows = await cdp.ev(JS_MENU)
        rows = rows if isinstance(rows, list) else []
        print("[open %d] chip=%s@%d,%d rows=%d" %
              (attempt, chip["t"], chip["x"], chip["y"], len(rows)), flush=True)
        if len(rows) >= 3:
            return rows
        await cdp.key("Escape", 27)
        await asyncio.sleep(0.7)
    return []


async def main(cmd, arg):
    targets = json.loads(http_get(f"http://127.0.0.1:{PORT}/json/list"))
    pages = [t for t in targets if t.get("webSocketDebuggerUrl")]
    if not pages:
        print("NO_CDP_TARGET"); return 2
    async with CDP(pages[0]["webSocketDebuggerUrl"]) as cdp:
        if cmd == "chip":
            hits = await chip_info(cdp)
            print(json.dumps(hits, ensure_ascii=False, indent=1))
            return 0

        rows = await open_picker(cdp)
        if not rows:
            print("PICKER_NEVER_OPENED", flush=True); return 3

        if cmd == "list":
            for r in rows:
                print("  -", r["t"], "@", r["x"], r["y"], flush=True)
            await cdp.key("Escape", 27)
            return 0

        # select
        want = (arg or "").lower()
        hit = None
        for r in rows:
            if want and want in r["t"].lower():
                hit = r; break
        if not hit:
            print("NO_MATCH target=%r rows=%s" % (arg, [r["t"] for r in rows]), flush=True)
            await cdp.key("Escape", 27)
            return 4
        print("[select] clicking %r @%d,%d" % (hit["t"], hit["x"], hit["y"]), flush=True)
        await cdp.click(hit["x"], hit["y"])
        await asyncio.sleep(1.6)
        hits = await chip_info(cdp)
        labels = [h["t"] for h in hits]
        cur = labels[-1] if labels else "?"
        ok = want in cur.lower()
        print("CHIP_NOW=%r OK=%s ALL=%s" % (cur, ok, labels), flush=True)
        return 0 if ok else 5


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "list"
    a = sys.argv[2] if len(sys.argv) > 2 else ""
    sys.exit(asyncio.run(main(c, a)) or 0)

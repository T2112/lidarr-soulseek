from __future__ import annotations

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("lidarr_slsk.ui")

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Lidarr Soulseek</title>
<style>
:root{color-scheme:dark}body{font-family:Segoe UI,system-ui,sans-serif;margin:0;background:#111;color:#eee}
header{padding:16px 20px;background:#1c1c1c;border-bottom:1px solid #333;display:flex;justify-content:space-between}
h1{font-size:18px;margin:0}main{padding:16px 20px}.meta{color:#aaa;font-size:14px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #2a2a2a;font-size:13px}
button{background:#8b1e1e;color:#fff;border:0;padding:6px 10px;border-radius:4px;cursor:pointer}
button.secondary{background:#333}.ok{color:#7dce7d}.bad{color:#e07a7a}
.bar{height:8px;background:#333;border-radius:4px;overflow:hidden;min-width:80px}.bar>i{display:block;height:100%;background:#3d8bfd}
h2{font-size:15px;margin:28px 0 8px}
</style></head><body>
<header><h1>Lidarr Soulseek</h1><div>
<button class="secondary" onclick="load()">Refresh</button>
<button onclick="cancelAll()">Cancel all</button></div></header>
<main><div id="job" class="meta">Loading…</div>
<table><thead><tr><th>File</th><th>User</th><th>Status</th><th>Progress</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<h2>Recent completed</h2>
<table><thead><tr><th>When</th><th>Artist / album</th><th>File</th><th>User</th></tr></thead><tbody id="recent"></tbody></table>
</main>
<script>
async function load(){
  const r=await fetch('/api/status'); const d=await r.json(); const job=d.job||{};
  document.getElementById('job').textContent=[d.logged_in?'Soulseek connected':'Soulseek offline',job.phase||'idle',[job.artist,job.title].filter(Boolean).join(' \u2014 ')].filter(Boolean).join(' \u00b7 ');
  const body=document.getElementById('rows'); body.innerHTML='';
  (d.transfers||[]).forEach((t,i)=>{
    const tr=document.createElement('tr');
    const width=t.percent==null?0:Math.max(0,Math.min(100,t.percent));
    const pct=t.percent==null?'':Math.round(t.percent)+'%';
    const done=['COMPLETE','FAILED','ABORTED'].includes(t.state);
    tr.innerHTML=`<td>${esc(t.filename||'file')}</td><td>${esc(t.username||'')}</td><td class="${t.state==='COMPLETE'?'ok':(t.state==='FAILED'||t.state==='ABORTED'?'bad':'')}">${esc(t.state||'')}</td><td><div class="bar"><i style="width:${width}%"></i></div>${pct}</td><td>${done?'':`<button onclick="cancelOne(${i})">Cancel</button>`}</td>`;
    body.appendChild(tr);
  });
  if(!(d.transfers||[]).length){const tr=document.createElement('tr'); tr.innerHTML='<td colspan="5" class="meta">No active downloads</td>'; body.appendChild(tr);}
  const recent=document.getElementById('recent'); recent.innerHTML='';
  (d.recent||[]).forEach(item=>{
    const tr=document.createElement('tr');
    tr.innerHTML=`<td class="meta">${esc(fmtTime(item.finished_at))}</td><td>${esc([item.artist,item.title].filter(Boolean).join(' \u2014 '))}</td><td>${esc(item.filename||'')}</td><td>${esc(item.username||'')}</td>`;
    recent.appendChild(tr);
  });
  if(!(d.recent||[]).length){const tr=document.createElement('tr'); tr.innerHTML='<td colspan="4" class="meta">Nothing finished yet this install</td>'; recent.appendChild(tr);}
}
function fmtTime(iso){if(!iso)return ''; const d=new Date(iso); return Number.isNaN(d.getTime())?iso:d.toLocaleString();}
function esc(s){return String(s).replace(/[&<>"'`]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','`':'&#96;'}[c]));}
async function cancelOne(i){await fetch('/api/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:i})}); load();}
async function cancelAll(){await fetch('/api/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({all:true})}); load();}
load(); setInterval(load,2000);
</script></body></html>
"""


class StatusHandler(BaseHTTPRequestHandler):
    worker: Any = None
    loop: asyncio.AbstractEventLoop | None = None

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("%s - " + fmt, self.address_string(), *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send(200, json.dumps(self.worker.ui_snapshot()).encode("utf-8"), "application/json")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/cancel":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        assert self.loop is not None
        fut = asyncio.run_coroutine_threadsafe(
            self.worker.cancel_downloads(all_items=bool(body.get("all")), index=body.get("index")),
            self.loop,
        )
        try:
            fut.result(timeout=15)
        except Exception as exc:
            log.exception("Cancel failed: %s", exc)
            self._send(500, json.dumps({"ok": False, "error": str(exc)}).encode(), "application/json")
            return
        self._send(200, b'{"ok":true}', "application/json")


def start_status_ui(worker: Any, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundStatusHandler", (StatusHandler,), {})
    handler.worker = worker
    handler.loop = asyncio.get_event_loop()
    server = ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=server.serve_forever, name="status-ui", daemon=True).start()
    log.info("Status page http://%s:%s", host, port)
    return server

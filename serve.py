#!/usr/bin/env python3
# Servidor minimo whitelist: solo / , /data.json , /session/<slug>.json. Sin listado ni fuente/.bak.
# Requiere X-Dashboard-Token (inyectado por Traefik solo despues de authentik-forwardauth) --
# ver /opt/secure-publishing/traefik/dynamic/claude.yml. Sin token valido -> 403. Fail-closed:
# si DASHBOARD_TOKEN no esta seteado, el proceso se niega a arrancar en vez de servir sin auth.
import http.server, hmac, os, re
ROOT="/opt/claude-usage-web"; SLUG=re.compile(r"^(?!\.)[A-Za-z0-9_.-]{1,80}$")
DASHBOARD_TOKEN=os.environ.get("DASHBOARD_TOKEN")
if not DASHBOARD_TOKEN:
    raise SystemExit("DASHBOARD_TOKEN no seteado (ver /etc/claude-usage-web.env) -- me niego a arrancar sin auth")
class H(http.server.BaseHTTPRequestHandler):
    timeout=10
    def _send(self,path,ctype):
        try:
            with open(path,"rb") as f: data=f.read()
        except Exception:
            self.send_error(404); return
        self.send_response(200); self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if not hmac.compare_digest(self.headers.get("X-Dashboard-Token",""), DASHBOARD_TOKEN):
            self.send_error(403); return
        p=self.path.split("?",1)[0]
        if p in ("/","/index.html"): return self._send(f"{ROOT}/index.html","text/html; charset=utf-8")
        if p=="/data.json": return self._send(f"{ROOT}/data.json","application/json")
        m=re.match(r"^/session/([^/]+)\.json$", p)
        if m and SLUG.match(m.group(1)): return self._send(f"{ROOT}/session/{m.group(1)}.json","application/json")
        self.send_error(404)
    def log_message(self,*a): pass
with http.server.ThreadingHTTPServer(("172.17.0.1",7681),H) as s: s.serve_forever()

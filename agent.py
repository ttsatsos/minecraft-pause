#!/usr/bin/env python3
"""
Remote Minecraft Parent Control — background agent.

Runs as the child's login user (via a LaunchAgent). Exposes a tiny token-
protected HTTP API + a one-button control page that a parent opens on their
iPhone (same Wi-Fi). Pressing PAUSE freezes Minecraft with SIGSTOP so the game
looks frozen, not crashed, and arms "guard mode": any attempt to get back into
the game (resuming the frozen process, force-quitting + relaunching) is met with
an immediate SIGKILL.

Zero third-party dependencies — Python 3 stdlib only.
"""

import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(HOME, ".minecraft-pause")
os.makedirs(CFG_DIR, exist_ok=True)
TOKEN_FILE = os.path.join(CFG_DIR, "token")

PORT = int(os.environ.get("MCPAUSE_PORT", "8731"))
GUARD_INTERVAL = float(os.environ.get("MCPAUSE_GUARD_INTERVAL", "0.2"))  # seconds


def load_token():
    """Read the shared secret, generating one on first run."""
    if os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE).read().strip()
        if t:
            return t
    t = secrets.token_urlsafe(16)
    with open(TOKEN_FILE, "w") as f:
        f.write(t)
    os.chmod(TOKEN_FILE, 0o600)
    return t


TOKEN = load_token()

# ----------------------------------------------------------------------------
# Process matching — find the Minecraft GAME (the JVM), not the launcher UI
# ----------------------------------------------------------------------------
# The Electron "Minecraft Launcher" also has "minecraft" in its command line;
# we never want to freeze/kill that — only the running java game process.
_EXCLUDE = (
    "minecraft launcher.app",
    "minecraftlauncher",
    "minecraft.app/contents/frameworks",
    "/applications/minecraft.app",
)


def _is_game(cmd: str) -> bool:
    low = cmd.lower()
    for e in _EXCLUDE:
        if e in low:
            return False
    # Require a real Minecraft-game signature, not just the substring "minecraft"
    # (which also appears in, e.g., this controller app's own bundle path). These
    # cover vanilla, Fabric, Forge, Prism, MultiMC — all pass the game via java.
    if "net.minecraft" in low:                       # vanilla main class / packages
        return True
    if "net.fabricmc" in low and "minecraft" in low:  # Fabric loader
        return True
    if any(arg in low for arg in ("--gamedir", "--assetindex", "--versiontype", "--uuid")):
        return True                                   # launcher-passed game args
    if "minecraft" in low and "-djava.library.path" in low:
        return True                                   # natives path on game launch
    if "minecraft" in low and "/runtime/java" in low:
        return True                                   # bundled JRE under .minecraft/runtime
    return False


def list_procs():
    """Return [(pid, stat, command), ...] for every process."""
    try:
        out = subprocess.run(
            ["ps", "-axww", "-o", "pid=", "-o", "stat=", "-o", "command="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []
    res = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, stat, cmd = parts
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        res.append((pid, stat, cmd))
    return res


def game_procs():
    return [(p, s, c) for (p, s, c) in list_procs() if _is_game(c)]


# ----------------------------------------------------------------------------
# Control state
# ----------------------------------------------------------------------------
_lock = threading.Lock()
_guard_active = False
_stopped_pids = set()
_last_notify = 0.0


def notify(msg, title="Minecraft", subtitle=None):
    try:
        script = f'display notification "{msg}" with title "{title}"'
        if subtitle:
            script += f' subtitle "{subtitle}"'
        subprocess.run(["osascript", "-e", script], timeout=5)
    except Exception:
        pass


def do_pause():
    """Freeze every running Minecraft game process and arm guard mode."""
    global _guard_active, _stopped_pids
    pids = [p for (p, s, c) in game_procs()]
    for p in pids:
        try:
            os.kill(p, signal.SIGSTOP)
        except (ProcessLookupError, PermissionError):
            pass
    with _lock:
        _stopped_pids = set(pids)
        _guard_active = True
    if pids:
        notify("Paused by parent.", "Minecraft", "Wait for class to finish.")
    return pids


def do_resume():
    """Parent chooses to let the kid back in: un-freeze and disarm guard."""
    global _guard_active, _stopped_pids
    with _lock:
        pids = list(_stopped_pids)
        _stopped_pids = set()
        _guard_active = False
    for p in pids:
        try:
            os.kill(p, signal.SIGCONT)
        except Exception:
            pass
    if pids:
        notify("Resumed by parent.", "Minecraft", "You're good to go.")
    return pids


def do_kill():
    """Hard end: SIGKILL every game process and disarm guard."""
    global _guard_active, _stopped_pids
    pids = [p for (p, s, c) in game_procs()]
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)  # delivered even to a stopped process
        except Exception:
            pass
    with _lock:
        _stopped_pids = set()
        _guard_active = False
    return pids


def do_status():
    procs = game_procs()
    running = [p for (p, s, c) in procs]
    paused = [p for (p, s, c) in procs if s.startswith("T")]
    with _lock:
        active = _guard_active
    if active:
        mode = "guarding"
    elif paused:
        mode = "paused"
    elif running:
        mode = "running"
    else:
        mode = "not_running"
    return {
        "mode": mode,
        "running": bool(running),
        "paused": bool(paused),
        "guard": active,
        "pids": running,
    }


def guard_loop():
    """
    While guard mode is armed, any game process that is NOT correctly frozen
    gets killed. This covers both:
      - the original frozen process being resumed (T -> R), and
      - the kid force-quitting the frozen game and relaunching (new pid).
    """
    global _last_notify
    while True:
        time.sleep(GUARD_INTERVAL)
        with _lock:
            active = _guard_active
            stopped = set(_stopped_pids)
        if not active:
            continue
        for (pid, stat, cmd) in game_procs():
            if pid in stopped and stat.startswith("T"):
                continue  # correctly frozen — leave it
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
            now = time.time()
            if now - _last_notify > 5:
                _last_notify = now
                notify(
                    "Game closed — you tried to get around the pause.",
                    "Minecraft",
                )


# ----------------------------------------------------------------------------
# HTTP server
# ----------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Minecraft">
<meta name="theme-color" content="#0b0b0d">
<title>Minecraft Control</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: -apple-system, system-ui, sans-serif;
    background: #0b0b0d; color: #e9e9ee;
    display: flex; flex-direction: column;
    padding: max(20px, env(safe-area-inset-top)) 20px max(20px, env(safe-area-inset-bottom));
    gap: 18px; user-select: none; -webkit-user-select: none;
  }
  header { text-align: center; }
  header h1 { font-size: 17px; font-weight: 600; margin: 0; letter-spacing: .3px; }
  #status {
    text-align: center; font-size: 15px; color: #9a9aa6;
    min-height: 22px; transition: color .2s;
  }
  #status .dot {
    display: inline-block; width: 9px; height: 9px; border-radius: 50%;
    background: #555; margin-right: 7px; vertical-align: middle;
  }
  .main { flex: 1; display: flex; }
  #pause {
    flex: 1; border: none; border-radius: 28px; color: #fff;
    font-size: 42px; font-weight: 800; letter-spacing: 1px; line-height: 1.1;
    background: linear-gradient(160deg, #ff5b5b, #d31f2e);
    box-shadow: 0 12px 40px rgba(211,31,46,.35);
    transition: transform .08s ease, filter .15s ease;
    cursor: pointer;
  }
  #pause:active { transform: scale(.97); filter: brightness(.92); }
  #pause.paused {
    background: linear-gradient(160deg, #ffc24b, #f59e0b);
    box-shadow: 0 12px 40px rgba(245,158,11,.3);
  }
  .row { display: flex; gap: 12px; }
  .row button {
    flex: 1; border: 1px solid #2a2a31; background: #16161a; color: #cfcfd6;
    border-radius: 16px; padding: 16px; font-size: 16px; font-weight: 600;
    cursor: pointer; transition: transform .08s ease, background .15s;
  }
  .row button:active { transform: scale(.97); background: #1f1f25; }
  .row button.danger { color: #ff8a8a; border-color: #3a2326; }
  .err { color: #ff8a8a; }
</style>
</head>
<body>
  <header><h1>Minecraft Control</h1></header>
  <div id="status"><span class="dot"></span>Checking…</div>
  <div class="main">
    <button id="pause">PAUSE<br>MINECRAFT</button>
  </div>
  <div class="row">
    <button id="resume">Resume</button>
    <button id="kill" class="danger">End game</button>
  </div>

<script>
  const T = new URLSearchParams(location.search).get('t') || '';
  const statusEl = document.getElementById('status');
  const dot = () => statusEl.querySelector('.dot');
  const pauseBtn = document.getElementById('pause');

  function setStatus(text, color, dotColor) {
    statusEl.innerHTML = '<span class="dot"></span>' + text;
    statusEl.style.color = color || '#9a9aa6';
    dot().style.background = dotColor || '#555';
  }

  async function call(path) {
    const r = await fetch(path + '?t=' + encodeURIComponent(T), { method: 'POST' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  function render(s) {
    if (s.mode === 'guarding' || s.mode === 'paused') {
      pauseBtn.classList.add('paused');
      pauseBtn.innerHTML = 'PAUSED<br><span style="font-size:20px;font-weight:600">guard on</span>';
      setStatus('Paused — guarding against restarts', '#f5c451', '#f59e0b');
    } else if (s.mode === 'running') {
      pauseBtn.classList.remove('paused');
      pauseBtn.innerHTML = 'PAUSE<br>MINECRAFT';
      setStatus('Minecraft is running', '#7fd58a', '#34c759');
    } else {
      pauseBtn.classList.remove('paused');
      pauseBtn.innerHTML = 'PAUSE<br>MINECRAFT';
      setStatus('Minecraft not running', '#9a9aa6', '#555');
    }
  }

  async function refresh() {
    try { render(await call('/api/status')); }
    catch (e) { setStatus('Cannot reach Mac', '#ff8a8a', '#ff3b30'); }
  }

  function buzz() { if (navigator.vibrate) navigator.vibrate(30); }

  pauseBtn.addEventListener('click', async () => {
    buzz();
    try { render(await call('/api/pause')); } catch (e) { setStatus('Error: ' + e.message, '#ff8a8a', '#ff3b30'); }
  });
  document.getElementById('resume').addEventListener('click', async () => {
    buzz();
    try { render(await call('/api/resume')); } catch (e) { setStatus('Error: ' + e.message, '#ff8a8a', '#ff3b30'); }
  });
  document.getElementById('kill').addEventListener('click', async () => {
    if (!confirm('Force quit Minecraft now?')) return;
    buzz();
    try { render(await call('/api/kill')); } catch (e) { setStatus('Error: ' + e.message, '#ff8a8a', '#ff3b30'); }
  });

  refresh();
  setInterval(refresh, 2000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "mcpause/1.0"

    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        # token via ?t= or X-Token header
        tok = None
        if "?" in self.path:
            from urllib.parse import urlparse, parse_qs
            tok = parse_qs(urlparse(self.path).query).get("t", [None])[0]
        if not tok:
            tok = self.headers.get("X-Token")
        return tok == TOKEN

    def _route(self):
        from urllib.parse import urlparse
        return urlparse(self.path).path

    def do_GET(self):
        path = self._route()
        if path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            return self._send(200, do_status())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self._route()
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if path == "/api/pause":
            pids = do_pause()
            return self._send(200, {**do_status(), "acted_on": pids})
        if path == "/api/resume":
            pids = do_resume()
            return self._send(200, {**do_status(), "acted_on": pids})
        if path == "/api/kill":
            pids = do_kill()
            return self._send(200, {**do_status(), "acted_on": pids})
        if path == "/api/status":
            return self._send(200, do_status())
        self._send(404, {"error": "not found"})


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    threading.Thread(target=guard_loop, daemon=True).start()
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    print(f"Minecraft Control running.")
    print(f"  Parent URL:  http://{ip}:{PORT}/?t={TOKEN}")
    print(f"  Token file:  {TOKEN_FILE}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()

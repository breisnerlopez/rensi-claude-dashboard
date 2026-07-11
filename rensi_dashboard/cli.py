#!/usr/bin/env python3
"""`rensi-dashboard` entry point: setup / start / stop / status / restart,
plus the raw `aggregate` / `serve` subcommands used by systemd-timer-style
deployments (see the repo's own deployment for an example). One command to
get a working dashboard; the pieces stay reachable individually for anyone
who wants their own scheduling (cron, systemd, Task Scheduler by hand).
"""
import argparse
import os
import re
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import core

PID_FILE_NAME = ".pid"


def _pid_file():
    core.ensure_dirs()
    return core.DATA_DIR / PID_FILE_NAME


def _is_running(pid):
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
            return str(pid) in out.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours
    except Exception:
        return False


def _read_pid():
    pf = _pid_file()
    if not pf.exists():
        return None
    try:
        pid = int(pf.read_text().strip())
    except Exception:
        return None
    return pid if _is_running(pid) else None


def cmd_start(args):
    running = _read_pid()
    if running:
        print(f"ya corriendo (pid {running}) -- {core.dashboard_url(core.get_or_create_token())}")
        return
    core.ensure_dirs()
    token = core.get_or_create_token()
    if args.foreground:
        from . import server
        server.run(with_scheduler=True)
        return
    exe = sys.executable
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([exe, "-m", "rensi_dashboard.server"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    _pid_file().write_text(str(proc.pid))
    time.sleep(1.2)
    url = core.dashboard_url(token)
    print("iniciado. abre:", url)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass


def cmd_stop(args):
    pid = _read_pid()
    if not pid:
        print("no esta corriendo")
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    try:
        _pid_file().unlink()
    except Exception:
        pass
    print("detenido")


def cmd_status(args):
    pid = _read_pid()
    if pid:
        print(f"corriendo (pid {pid}) -- {core.dashboard_url(core.get_or_create_token())}")
    else:
        print("no esta corriendo")


def cmd_restart(args):
    cmd_stop(args)
    time.sleep(0.5)
    cmd_start(args)


def _register_autostart_linux():
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    exe = sys.executable
    if _which("systemctl"):
        try:
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / "rensi-dashboard.service").write_text(
                "[Unit]\nDescription=rensi-claude-dashboard\n\n"
                "[Service]\n"
                f"ExecStart={exe} -m rensi_dashboard.server\n"
                "Restart=always\nRestartSec=5\n\n"
                "[Install]\nWantedBy=default.target\n"
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", "rensi-dashboard.service"], capture_output=True)
            print("autostart: systemd --user (rensi-dashboard.service)")
            return True
        except Exception:
            pass
    if _which("crontab"):
        try:
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            line = f"@reboot {exe} -m rensi_dashboard.server >/dev/null 2>&1"
            if line not in existing:
                subprocess.run(["crontab", "-"], input=existing + line + "\n", text=True, capture_output=True)
            print("autostart: crontab @reboot")
            return True
        except Exception:
            pass
    print("autostart: no se pudo registrar automaticamente (sin systemd/cron) -- corre 'rensi-dashboard start' manualmente cuando quieras usarlo")
    return False


def _register_autostart_windows():
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    target = f'"{exe}" -m rensi_dashboard.server'
    try:
        subprocess.run(["schtasks", "/Create", "/TN", "RensiClaudeDashboard", "/TR", target,
                         "/SC", "ONLOGON", "/RL", "LIMITED", "/F"], capture_output=True, check=True)
        # Hourly self-heal trigger, since there's no systemd-style supervisor watching this process.
        subprocess.run(["schtasks", "/Create", "/TN", "RensiClaudeDashboardHeal", "/TR", target,
                         "/SC", "HOURLY", "/MO", "1", "/RL", "LIMITED", "/F"], capture_output=True, check=True)
        print("autostart: Task Scheduler (RensiClaudeDashboard, on-logon + hourly self-heal)")
        return True
    except Exception as e:
        print(f"autostart: no se pudo registrar en Task Scheduler ({e}) -- corre 'rensi-dashboard start' manualmente")
        return False


def _which(name):
    from shutil import which
    return which(name)


def cmd_setup(args):
    core.ensure_dirs()
    token = core.get_or_create_token()
    print("token guardado en", core.TOKEN_FILE)
    if sys.platform == "win32":
        _register_autostart_windows()
    elif sys.platform == "darwin":
        print("autostart: no implementado aun en macOS -- corre 'rensi-dashboard start' manualmente, o agrega tu propio launchd plist")
    else:
        _register_autostart_linux()
    cmd_start(args)


def cmd_aggregate(args):
    from . import aggregate
    aggregate.main(fast=args.fast)


_TUNNEL_INSTALL_HELP = {
    "darwin": "brew install cloudflared",
    "win32": "winget install --id Cloudflare.cloudflared",
}
_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def cmd_tunnel(args):
    """Free, no-account-needed public URL via a Cloudflare Quick Tunnel --
    for showing someone else your live dashboard right now. This is a much
    bigger exposure than the default localhost-only bind: anyone who has
    the printed URL (which includes the access token) can view your local
    Claude Code session data for as long as this command keeps running.
    Ephemeral by design -- Ctrl+C closes the tunnel; nothing is left
    listening publicly afterward."""
    exe = _which("cloudflared")
    if not exe:
        hint = _TUNNEL_INSTALL_HELP.get(sys.platform, "see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        print("cloudflared no esta instalado.")
        print("Instalar: " + hint)
        print("Luego vuelve a correr: rensi-dashboard tunnel")
        return

    if not _read_pid():
        print("el dashboard no esta corriendo -- arrancandolo primero...")
        cmd_start(argparse.Namespace(no_browser=True, foreground=False))

    token = core.get_or_create_token()
    target = "http://{}:{}".format(core.HOST, core.PORT)

    print()
    print("=" * 60)
    print("ATENCION: esto publica tu dashboard en una URL publica")
    print("temporal (*.trycloudflare.com). Cualquiera con el link de")
    print("abajo puede ver tus sesiones de Claude Code -- el link ya")
    print("incluye tu token de acceso. Ctrl+C cierra el tunel; nada")
    print("queda escuchando publicamente despues de eso.")
    print("=" * 60)
    print()

    proc = subprocess.Popen(
        [exe, "tunnel", "--url", target, "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    printed = False
    try:
        for line in proc.stdout:
            m = _TUNNEL_URL_RE.search(line)
            if m and not printed:
                printed = True
                print("URL publica (temporal):", m.group(0) + "/?t=" + token)
                print("(Ctrl+C para cerrar el tunel)")
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("tunel cerrado")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rensi-dashboard")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("setup", help="primera vez: genera token, registra autostart, arranca e imprime la URL")
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--foreground", action="store_true")
    sp.set_defaults(func=cmd_setup)

    sp = sub.add_parser("start", help="arranca el servidor en segundo plano")
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--foreground", action="store_true", help="no daemoniza -- util para systemd/debug")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop"); sp.set_defaults(func=cmd_stop)
    sp = sub.add_parser("status"); sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("restart")
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--foreground", action="store_true")
    sp.set_defaults(func=cmd_restart)

    sp = sub.add_parser("aggregate", help="corre un ciclo de agregacion una vez (uso: systemd timer / cron)")
    sp.add_argument("--fast", action="store_true")
    sp.set_defaults(func=cmd_aggregate)

    sp = sub.add_parser("tunnel", help="URL publica temporal (Cloudflare Quick Tunnel, gratis, sin cuenta) para compartir el dashboard en vivo")
    sp.set_defaults(func=cmd_tunnel)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

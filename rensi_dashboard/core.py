"""Shared config: every path/bind/token the rest of the package needs, all
env-overridable with OS-portable defaults. No literal filesystem paths from
one specific box live anywhere outside this module.
"""
import os
import secrets
import sys
from pathlib import Path


def _data_dir():
    override = os.environ.get("DASHBOARD_DATA_DIR")
    if override:
        return Path(override)
    try:
        import platformdirs
        return Path(platformdirs.user_data_dir("rensi-dashboard", "rensi"))
    except ImportError:
        return Path.home() / ".rensi-dashboard"


CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME") or Path.home())
PROJECTS_DIR = CLAUDE_HOME / ".claude" / "projects"
TASKS_DIR = CLAUDE_HOME / ".claude" / "tasks"

DATA_DIR = _data_dir()
CACHE_FILE = DATA_DIR / ".parsecache.json"
BLOCK_LIMIT_CACHE = DATA_DIR / ".blocklimits.json"
DATA_FILE = DATA_DIR / "data.json"
SESSION_DIR = DATA_DIR / "session"
TOKEN_FILE = DATA_DIR / ".token"

HOST = os.environ.get("DASHBOARD_BIND", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "7681"))

FULL_INTERVAL_S = int(os.environ.get("DASHBOARD_FULL_INTERVAL", "180"))
FAST_INTERVAL_S = int(os.environ.get("DASHBOARD_FAST_INTERVAL", "15"))

IS_LINUX = sys.platform.startswith("linux")


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_token():
    """DASHBOARD_TOKEN env var wins if set (matches the reverse-proxy-fronted
    deployment style); otherwise persist a generated token in DATA_DIR so it
    survives restarts without the user having to manage it."""
    env_tok = os.environ.get("DASHBOARD_TOKEN")
    if env_tok:
        return env_tok
    ensure_dirs()
    if TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text().strip()
        if tok:
            return tok
    tok = secrets.token_hex(32)
    TOKEN_FILE.write_text(tok)
    try:
        TOKEN_FILE.chmod(0o600)
    except Exception:
        pass
    return tok


def dashboard_url(token):
    host = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    return "http://{}:{}/?t={}".format(host, PORT, token)

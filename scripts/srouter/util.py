"""Paths, JSON helpers and a tiny error log. Standard library only; nothing here touches the network."""
import glob
import json
import os
import time


def claude_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def data_dir():
    d = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not d:
        found = sorted(glob.glob(os.path.join(claude_home(), "plugins", "data", "skill-router*")),
                       key=os.path.getmtime, reverse=True)
        d = found[0] if found else os.path.join(claude_home(), "skill-router")
    os.makedirs(d, exist_ok=True)
    return d


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def append_line(path, line, cap=2_000_000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > cap:
            os.replace(path, path + ".1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def log_error(msg):
    try:
        append_line(os.path.join(data_dir(), "errors.log"), "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), 100_000)
    except OSError:
        pass

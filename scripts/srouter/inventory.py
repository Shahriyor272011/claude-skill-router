"""Finds every skill the current session could use and caches the parsed front matter."""
import os
import re

from . import util

HEAD_BYTES = 8192


def _unquote(val):
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        inner = val[1:-1]
        return inner.replace('\\"', '"') if val[0] == '"' else inner.replace("''", "'")
    return val


def parse_frontmatter(text):
    """The small YAML subset skills use: `key: value`, quoted values, folded/literal blocks, continuation lines."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out, key, buf = {}, None, []

    def flush():
        if key is not None:
            out[key] = _unquote(" ".join(s.strip() for s in buf if s.strip()))

    for ln in text[3:end].splitlines():
        m = None if ln[:1] in (" ", "\t") else re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", ln)
        if m:
            flush()
            key, first = m.group(1), m.group(2).strip()
            buf = [] if first in (">", ">-", ">+", "|", "|-", "|+") else [first]
        elif key is not None:
            buf.append(ln)
    flush()
    return out


def _settings(cwd):
    """Merged enabledPlugins and skillOverrides from user, project and local settings."""
    enabled, overrides = {}, {}
    for path in (os.path.join(util.claude_home(), "settings.json"),
                 os.path.join(cwd, ".claude", "settings.json"),
                 os.path.join(cwd, ".claude", "settings.local.json")):
        data = util.read_json(path, {})
        if isinstance(data, dict):
            if isinstance(data.get("enabledPlugins"), dict):
                enabled.update(data["enabledPlugins"])
            if isinstance(data.get("skillOverrides"), dict):
                overrides.update(data["skillOverrides"])
    return enabled, overrides


def _skill_dirs(root):
    if os.path.isfile(os.path.join(root, "SKILL.md")):
        yield root
        return
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    for e in entries:
        if e.is_dir() and os.path.isfile(os.path.join(e.path, "SKILL.md")):
            yield e.path


def _plugin_skill_roots(install_path):
    roots = [os.path.join(install_path, "skills")]
    manifest = util.read_json(os.path.join(install_path, ".claude-plugin", "plugin.json"), {})
    extra = manifest.get("skills") if isinstance(manifest, dict) else None
    for p in ([extra] if isinstance(extra, str) else extra or []):
        if isinstance(p, str):
            roots.append(os.path.normpath(os.path.join(install_path, p)))
    return roots


def _sources(cwd):
    """Yields (source, plugin_prefix, skill_dir) for user, project and enabled-plugin skills."""
    enabled, _ = _settings(cwd)
    for d in _skill_dirs(os.path.join(util.claude_home(), "skills")):
        yield "user", "", d
    for d in _skill_dirs(os.path.join(cwd, ".claude", "skills")):
        yield "project", "", d
    installed = util.read_json(os.path.join(util.claude_home(), "plugins", "installed_plugins.json"), {})
    plugins = installed.get("plugins", {}) if isinstance(installed, dict) else {}
    for pid, installs in sorted(plugins.items()):
        if enabled.get(pid) is False or not isinstance(installs, list) or not installs:
            continue
        path = installs[-1].get("installPath") if isinstance(installs[-1], dict) else None
        if not path or not os.path.isdir(path):
            continue
        for root in _plugin_skill_roots(path):
            for d in _skill_dirs(root):
                yield "plugin", pid.split("@")[0], d


def _parse_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return parse_frontmatter(fh.read(HEAD_BYTES))
    except OSError:
        return {}


def build(cwd=None):
    """Skill list. Every call stats the SKILL.md files and re-parses only the ones that changed."""
    cwd = cwd or os.getcwd()
    cache_path = os.path.join(util.data_dir(), "index-cache.json")
    cache = util.read_json(cache_path, {}) or {}
    fresh, skills, seen = {}, [], set()
    _, overrides = _settings(cwd)
    for source, prefix, d in _sources(cwd):
        path = os.path.join(d, "SKILL.md")
        try:
            st = os.stat(path)
        except OSError:
            continue
        stamp = [st.st_mtime_ns, st.st_size]
        hit = cache.get(path)
        fm = hit["fm"] if hit and hit["stamp"] == stamp else _parse_file(path)
        fresh[path] = {"stamp": stamp, "fm": fm}
        short = fm.get("name") or os.path.basename(d)
        name = "%s:%s" % (prefix, short) if prefix else short
        if name in seen:
            continue
        seen.add(name)
        override = overrides.get(short) or overrides.get(name)
        skills.append({
            "name": name, "short": short, "source": source, "plugin": prefix, "path": path,
            "desc": (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip(),
            "desc_len": len(fm.get("description", "")) + len(fm.get("when_to_use", "")),
            "manual": fm.get("disable-model-invocation", "").lower() == "true"
                      or override in ("off", "user-invocable-only"),
        })
    if fresh != cache:
        try:
            util.write_json(cache_path, fresh)
        except OSError as exc:
            util.log_error("cache write failed: %s" % exc)
    return skills

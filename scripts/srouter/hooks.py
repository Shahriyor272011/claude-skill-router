"""Hook handlers. They are called through cli.run_hook, which swallows every error: a bug here must never block work."""
import json
import os
import re
import time

from . import config, inventory, match, messages, packs, shell, util

WORK_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "Agent"}
PHASE_RE = re.compile(r"skill-router\s+phase\s+(plan|build|verify|ship)\b")


def _state_path(sid):
    return os.path.join(util.data_dir(), "state", re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:80] + ".json")


def _load(sid):
    return util.read_json(_state_path(sid), None)


def _save(sid, st):
    util.write_json(_state_path(sid), st)
    _prune_old_state()


def _prune_old_state():
    d = os.path.join(util.data_dir(), "state")
    cutoff = time.time() - 7 * 86400
    try:
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
    except OSError:
        pass


def usage():
    return util.read_json(os.path.join(util.data_dir(), "usage.json"), {}) or {}


def seen():
    return util.read_json(os.path.join(util.data_dir(), "seen.json"), {}) or {}


def _count_seen(shorts):
    counts = seen()
    for s in shorts:
        counts[s] = counts.get(s, 0) + 1
    util.write_json(os.path.join(util.data_dir(), "seen.json"), counts)


def _bump(short):
    u = usage()
    u[short] = u.get(short, 0) + 1
    util.write_json(os.path.join(util.data_dir(), "usage.json"), u)


def _journal(cfg, ev, sid, **kw):
    if cfg["journal"]:
        rec = dict({"ts": int(time.time()), "sid": sid[:8], "ev": ev}, **kw)
        util.append_line(os.path.join(util.data_dir(), "journal.jsonl"), json.dumps(rec, ensure_ascii=False))


def suggest(cfg, cwd, weights, phase):
    """Everything the router knows about this task: strong and related skills, phase pins and skill sets."""
    hidden = set(cfg["ignore"])
    skills = [s for s in inventory.build(cwd) if not s["manual"] and s["name"] not in hidden and s["short"] not in hidden]
    used, shown = usage(), seen()
    boosts = {k: match.usage_boost(used.get(k, 0)) * match.ignored_penalty(shown.get(k, 0), used.get(k, 0))
              for k in set(used) | set(shown)}
    ranked = match.Ranker(skills, cfg["aliases"], cfg["prefer"], boosts).rank(weights)
    strong, also = match.classify(ranked, cfg)
    pinned = match.resolve(skills, cfg["pin"].get(phase, []))
    found = packs.discover(skills, cfg["packs"])
    return {"skills": skills, "ranked": ranked, "strong": strong, "also": also, "pinned": pinned,
            "picks": packs.pick(found, ranked, weights, cfg)}


def _unique(items):
    seen, out = set(), []
    for s in items:
        if s["name"] not in seen:
            seen.add(s["name"])
            out.append(s)
    return out


def _plan_turn(cfg, sug, used):
    first = _unique(sug["pinned"] + sug["strong"])
    pool = _unique(first + sug["also"]) if cfg["mode"] == "strict" else first
    return {
        "show_strong": [s for s in first if s["short"] not in used],
        "show_also": [s for s in sug["also"] if s["short"] not in used and s["name"] not in {x["name"] for x in first}],
        "loaded": [s["short"] for s in _unique(first + sug["also"]) if s["short"] in used],
        "pending": [s["name"] for s in pool if s["short"] not in used],
    }


def on_prompt(data):
    cfg = config.load()
    sid, prompt = str(data.get("session_id") or ""), str(data.get("prompt") or "").strip()
    if cfg["mode"] == "off" or not sid or not prompt or prompt.startswith("<"):
        return None
    cwd = data.get("cwd") or os.getcwd()
    prev = _load(sid) or {}
    used = set(prev.get("used_session", []))
    turn = int(prev.get("turn", 0)) + 1
    if prompt.startswith("/"):                       # the person picked a skill or command themselves
        words = prompt[1:].split()
        short = words[0].split(":")[-1] if words else ""
        if short and any(s["short"] == short for s in inventory.build(cwd)):
            used.add(short)
            _bump(short)
        _save(sid, {"turn": turn, "phase": "build", "pending": [], "skill_called": True, "denials": 0,
                    "used_session": sorted(used), "qweights": {}})
        _journal(cfg, "user-invoked", sid, skill=short)
        return None
    weights = match.query_weights(prompt)
    if not weights:                                  # "ok", "go on": keep the previous state
        return None
    phase = match.detect_phase(prompt)
    sug = suggest(cfg, cwd, weights, phase)
    plan = _plan_turn(cfg, sug, used)
    light = match.is_light(prompt)
    if light:                                        # still suggested, never blocked
        plan["pending"] = []
    _save(sid, {"turn": turn, "phase": phase, "pending": plan["pending"], "skill_called": False, "denials": 0,
                "used_session": sorted(used), "qweights": weights,
                "suggested": [s["short"] for s in plan["show_strong"] + plan["show_also"]]})
    if not (plan["show_strong"] or plan["show_also"] or sug["picks"] or plan["loaded"]):
        return None
    _count_seen([s["short"] for s in plan["show_strong"]])
    _journal(cfg, "suggested", sid, phase=phase, skills=[s["short"] for s in plan["show_strong"] + plan["show_also"]],
             packs=[p["id"] for p in sug["picks"]], light=light)
    gated = bool(plan["pending"]) and cfg["mode"] in ("guided", "strict")
    ctx = messages.context(cfg, phase, plan["show_strong"], plan["show_also"], sug["picks"], plan["loaded"], gated)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}


def _enter_phase(cfg, data, st, phase):
    weights = dict(st.get("qweights") or {})
    for k, v in match.query_weights(match.PHASE_BOOST[phase]).items():
        weights[k] = max(weights.get(k, 0.0), 0.8)
    used = set(st.get("used_session", []))
    sug = suggest(cfg, data.get("cwd") or os.getcwd(), weights, phase)
    plan = _plan_turn(cfg, sug, used)
    st.update(phase=phase, pending=plan["pending"], skill_called=False, denials=0)
    _save(str(data.get("session_id")), st)
    _journal(cfg, "phase", str(data.get("session_id")), phase=phase, skills=plan["pending"][:5])


def on_pretool(data):
    cfg = config.load()
    if cfg["mode"] not in ("guided", "strict") or data.get("agent_id") or data.get("tool_name") not in WORK_TOOLS:
        return None
    sid = str(data.get("session_id") or "")
    st = _load(sid) if sid else None
    if not st:
        return None
    if data.get("tool_name") == "Bash":
        cmd = str((data.get("tool_input") or {}).get("command") or "")
        m = PHASE_RE.search(cmd)
        if m:
            _enter_phase(cfg, data, st, m.group(1))
            return None
        if shell.is_readonly(cmd):
            return None
    limit = min(1, cfg["max_denials"]) if cfg["mode"] == "guided" else cfg["max_denials"]
    if st.get("skill_called") or not st.get("pending") or st.get("denials", 0) >= limit:
        return None
    st["denials"] = st.get("denials", 0) + 1
    _save(sid, st)
    _journal(cfg, "denied", sid, tool=data.get("tool_name"), skills=st["pending"][:3])
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": messages.deny(cfg, st["pending"])}}


def on_posttool(data):
    cfg = config.load()
    sid = str(data.get("session_id") or "")
    if cfg["mode"] == "off" or not sid or data.get("tool_name") != "Skill":
        return None
    st = _load(sid) or {"turn": 0, "phase": "build", "pending": [], "denials": 0, "used_session": []}
    inp = data.get("tool_input") or {}
    name = str(inp.get("skill") or "")
    short = name.split(":")[-1]
    st["skill_called"] = True
    if short == "none-fits":
        _journal(cfg, "none-fits", sid, reason=str(inp.get("args") or "")[:200])
    elif short:
        used = set(st.get("used_session", []))
        used.add(short)
        st["used_session"] = sorted(used)
        _bump(short)
        _journal(cfg, "used", sid, skill=short, hit=short in st.get("suggested", []))
    _save(sid, st)
    return None

"""Settings. Precedence: profile.json (written by /skill-router:setup) > plugin options > defaults."""
import os

from . import util

MODES = ("off", "suggest", "guided", "strict")
PHASES = ("plan", "build", "verify", "ship")
DEFAULTS = {
    "mode": "guided",        # off | suggest (never blocks) | guided (blocks once, only for strong matches) | strict
    "language": "en",        # language of the messages Claude sees: en or ru
    "top_n": 8,              # skills shown per request: strong ones with a reason, the rest by name only
    "min_score": 2.0,        # absolute floor for a match
    "strong_score": 6.0,     # score from which a match is strong enough to be worth blocking for
    "pack_n": 2,             # skill sets (packs) named per request
    "min_pack_score": 6.5,   # floor for a skill set
    "min_tokens": 1,         # prompts with no meaningful word ("ok", "go on") are not routed
    "max_denials": 3,        # strict mode: blocks per phase before work goes through (guided always blocks once)
    "journal": True,         # local log of suggested/used skills (names only), powers `skill-router status`
    "ignore": [],            # skills never suggested
    "prefer": [],            # skills ranked higher
    "pin": {},               # phase -> skills always suggested in that phase
    "aliases": {},           # skill -> extra keywords in any language (written by /skill-router:setup)
    "packs": {},             # your own skill sets: id -> {"members": [names or globs], "about": "keywords"}
}
NUMBERS = {"top_n": (1, 15, int), "min_tokens": (1, 10, int), "max_denials": (0, 10, int), "pack_n": (0, 4, int),
           "min_score": (0.0, 50.0, float), "strong_score": (0.0, 99999.0, float), "min_pack_score": (0.0, 99999.0, float)}


def profile_path():
    return os.path.join(util.data_dir(), "profile.json")


def _strs(v):
    return [str(x) for x in v] if isinstance(v, list) else []


def _norm(cfg):
    if cfg["mode"] == "nudge":
        cfg["mode"] = "suggest"
    if cfg["mode"] not in MODES:
        cfg["mode"] = "suggest"  # an unreadable value must never turn on blocking
    if cfg["language"] not in ("en", "ru"):
        cfg["language"] = "en"
    for key, (lo, hi, cast) in NUMBERS.items():
        try:
            cfg[key] = min(hi, max(lo, cast(cfg[key])))
        except (TypeError, ValueError):
            cfg[key] = DEFAULTS[key]
    cfg["journal"] = bool(cfg["journal"])
    cfg["ignore"], cfg["prefer"] = _strs(cfg["ignore"]), _strs(cfg["prefer"])
    cfg["pin"] = {p: _strs(v) for p, v in cfg["pin"].items() if p in PHASES} if isinstance(cfg["pin"], dict) else {}
    cfg["aliases"] = {str(k): _strs(v) for k, v in cfg["aliases"].items()} if isinstance(cfg["aliases"], dict) else {}
    cfg["packs"] = {str(k): {"members": _strs(v.get("members")), "about": str(v.get("about", k))}
                    for k, v in cfg["packs"].items() if isinstance(v, dict)} if isinstance(cfg["packs"], dict) else {}
    return cfg


def load():
    cfg = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in DEFAULTS.items()}
    sources = {}
    for key in ("mode", "language"):
        env = os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper())
        if env:
            cfg[key], sources[key] = env.strip().lower(), "plugin option"
    prof = util.read_json(profile_path(), {})
    if isinstance(prof, dict):
        for key in DEFAULTS:
            if key in prof:
                cfg[key], sources[key] = prof[key], "profile"
    cfg = _norm(cfg)
    cfg["_sources"] = sources
    return cfg


def read_profile():
    prof = util.read_json(profile_path(), {})
    return prof if isinstance(prof, dict) else {}


def write_profile(prof):
    util.write_json(profile_path(), prof)

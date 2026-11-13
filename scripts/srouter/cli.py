"""Command line: the hook entry points plus `suggest`, `phase`, `status`, `index`, `doctor` and `profile`."""
import json
import os
import sys

from . import __version__, config, hooks, inventory, match, packs, util

HOOKS = {"prompt": hooks.on_prompt, "pretool": hooks.on_pretool, "posttool": hooks.on_posttool}


def run_hook(kind, raw):
    try:
        out = HOOKS[kind](json.loads(raw or "{}"))
        if out:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception as exc:  # fail open
        util.log_error("%s: %r" % (kind, exc))
    return 0


def _line(s, score=None):
    d = s["desc"].split(". ")[0][:100]
    return "  %-34s %s%s" % (s["name"], d, "" if score is None else "  [%.1f]" % score)


def _show(cfg, sug):
    scores = {s["name"]: sc for sc, s in sug["ranked"]}
    if sug["pinned"]:
        print("phase pins:")
        print("\n".join(_line(s) for s in sug["pinned"]))
    print("strong matches:" if sug["strong"] else "strong matches: none")
    print("\n".join(_line(s, scores.get(s["name"])) for s in sug["strong"]))
    if sug["also"]:
        print("also relevant:")
        print("\n".join(_line(s, scores.get(s["name"])) for s in sug["also"]))
    for p in sug["picks"]:
        print("skill set: %s (%d skills) -> %s" % (p["id"], p["size"], ", ".join(s["name"] for s in p["entry"])))


def cmd_suggest(text):
    cfg = config.load()
    weights = match.query_weights(text)
    phase = match.detect_phase(text)
    print("phase: %s" % phase)
    _show(cfg, hooks.suggest(cfg, os.getcwd(), weights, phase))
    return 0


def cmd_phase(name, query):
    if name not in config.PHASES:
        print("phase must be one of: %s" % ", ".join(config.PHASES))
        return 2
    cfg = config.load()
    weights = match.query_weights(query or "")
    for k, v in match.query_weights(match.PHASE_BOOST[name]).items():
        weights[k] = max(weights.get(k, 0.0), 0.8)
    print("phase: %s" % name)
    _show(cfg, hooks.suggest(cfg, os.getcwd(), weights, name))
    return 0


def _journal():
    path = os.path.join(util.data_dir(), "journal.jsonl")
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def cmd_status():
    cfg = config.load()
    skills = inventory.build(os.getcwd())
    by_source = {}
    for s in skills:
        by_source[s["source"]] = by_source.get(s["source"], 0) + 1
    print("skill-router %s" % __version__)
    print("mode: %s · language: %s · data: %s" % (cfg["mode"], cfg["language"], util.data_dir()))
    print("skills: %d total · %d manual-only · %s" % (len(skills), sum(s["manual"] for s in skills),
                                                      ", ".join("%s %d" % kv for kv in sorted(by_source.items()))))
    print("listing: ~%d tokens of descriptions in every session; %d descriptions over 1536 chars are cut" % (
        sum(min(s["desc_len"], 1536) for s in skills) // 4, sum(s["desc_len"] > 1536 for s in skills)))
    found = packs.discover([s for s in skills if not s["manual"]], cfg["packs"])
    print("skill sets: %s" % (", ".join("%s(%d)" % (p["id"], len(p["members"])) for p in found) or "none"))
    log = _journal()
    sug = [e for e in log if e["ev"] == "suggested"]
    used = [e for e in log if e["ev"] == "used"]
    print("journal: %d requests routed · %d skill calls (%d from suggestions) · %d blocks · %d none-fits" % (
        len(sug), len(used), sum(bool(e.get("hit")) for e in used), sum(e["ev"] == "denied" for e in log),
        sum(e["ev"] == "none-fits" for e in log)))
    if sug:
        count = {}
        for e in sug:
            for k in e.get("skills", []):
                count[k] = count.get(k, 0) + 1
        used_names = {e.get("skill") for e in used}
        never = [k for k, _ in sorted(count.items(), key=lambda kv: -kv[1]) if k not in used_names][:8]
        print("suggested often, never called: %s" % (", ".join(never) or "-"))
        seen = set(count) | used_names
        if len(sug) >= 20:
            print("never suggested, never called (prune candidates after %d requests): %s" % (
                len(sug), ", ".join(sorted(s["short"] for s in skills if s["short"] not in seen))[:600] or "-"))
    return 0


def cmd_index():
    skills = inventory.build(os.getcwd())
    print("indexed %d skills (%d manual-only)" % (len(skills), sum(s["manual"] for s in skills)))
    return 0


def cmd_doctor():
    cfg = config.load()
    print("python %s · skill-router %s" % (sys.version.split()[0], __version__))
    print("data dir: %s (%s)" % (util.data_dir(), "writable" if os.access(util.data_dir(), os.W_OK) else "NOT writable"))
    print("claude home: %s" % util.claude_home())
    print("mode: %s %s" % (cfg["mode"], {k: v for k, v in cfg["_sources"].items()}))
    cmd_index()
    print("sample, 'fix the bug on my website':")
    cmd_suggest("fix the bug on my website")
    return 0


SCALARS = {"mode": str, "language": str, "journal": lambda v: v.lower() in ("1", "true", "yes", "on")}
SCALARS.update({k: spec[2] for k, spec in config.NUMBERS.items()})


def cmd_profile(args):
    sub = args[0] if args else "show"
    prof = config.read_profile()
    if sub == "show":
        print(json.dumps(dict(config.load(), _sources=None), ensure_ascii=False, indent=1, default=str))
        return 0
    if sub == "reset":
        config.write_profile({})
        return 0
    if sub == "set" and len(args) == 3 and args[1] in SCALARS:
        try:
            val = SCALARS[args[1]](args[2])
        except ValueError:
            print("bad value for %s" % args[1])
            return 2
        if args[1] == "mode" and val not in config.MODES or args[1] == "language" and val not in ("en", "ru"):
            print("bad value for %s: %s" % (args[1], val))
            return 2
        prof[args[1]] = val
    elif sub in ("ignore", "unignore", "prefer") and len(args) > 1:
        key = "prefer" if sub == "prefer" else "ignore"
        cur = [x for x in prof.get(key, []) if sub != "unignore" or x not in args[1:]]
        prof[key] = cur + ([x for x in args[1:] if x not in cur] if sub != "unignore" else [])
    elif sub in ("pin", "unpin") and len(args) > 2 and args[1] in config.PHASES:
        pins = prof.setdefault("pin", {})
        cur = [x for x in pins.get(args[1], []) if sub != "unpin" or x not in args[2:]]
        pins[args[1]] = cur + ([x for x in args[2:] if x not in cur] if sub == "pin" else [])
    elif sub == "alias" and len(args) > 2:
        al = prof.setdefault("aliases", {})
        cur = al.get(args[1], [])
        al[args[1]] = cur + [x for x in args[2:] if x not in cur]
    elif sub == "pack" and len(args) > 2:
        about = prof.setdefault("packs", {}).get(args[1], {}).get("about", args[1])
        prof["packs"][args[1]] = {"members": args[2:], "about": about}
    elif sub == "about" and len(args) > 2:
        pk = prof.setdefault("packs", {}).setdefault(args[1], {"members": []})
        pk["about"] = " ".join(args[2:])
    else:
        print("usage: profile show | set <key> <value> | alias <skill> <words...> | pin|unpin <phase> <skills...> | "
              "ignore|unignore|prefer <skills...> | pack <id> <members...> | about <pack> <words...> | reset")
        return 2
    config.write_profile(prof)
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("skill-router %s: hook <prompt|pretool|posttool> | suggest <text> | phase <name> [--query text] | "
              "status | index | doctor | profile ..." % __version__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "hook" and rest:
        return run_hook(rest[0], sys.stdin.read())
    if cmd == "suggest":
        return cmd_suggest(" ".join(rest))
    if cmd == "phase" and rest:
        query = " ".join(rest[rest.index("--query") + 1:]) if "--query" in rest else ""
        return cmd_phase(rest[0], query)
    if cmd == "status":
        return cmd_status()
    if cmd == "index":
        return cmd_index()
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "profile":
        return cmd_profile(rest)
    print("unknown command: %s" % cmd)
    return 2

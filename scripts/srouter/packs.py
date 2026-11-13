"""Skill sets ("packs"): the meta level. A task is matched against sets of skills, not only single skills."""
import fnmatch

from . import match

BUILTIN = [
    {"id": "business", "about": "startup founder business idea validation offer pricing marketing launch plan unit "
     "economics market competitors customers strategy product",
     "members": ["founder-*", "*:founder-*", "pm-product-*:*", "startup-business-analyst:*", "before-you-build",
                 "jobs-to-be-done", "mom-test", "monetizing-innovation", "lean-canvas", "*business-model*",
                 "*business-case*", "*market-sizing*", "pricing-strategy", "market-research", "*:market-research",
                 "product-lens", "office-hours", "plan-ceo-review"],
     "entry": ["founder-board", "founder-plan", "before-you-build", "office-hours"]},
    {"id": "orchestration", "about": "loop orchestration parallel agents subagents workflow autonomous long-running "
     "goal delegate multi-agent plan execute",
     "members": ["sadd:*", "*subagent*", "*parallel*", "autonomous-*", "loop", "*:loop", "*orchestrat*", "workflow-authoring",
                 "*multi-agent*", "dispatching-*", "executing-plans", "autopilot", "writing-plans", "*:team-*"],
     "entry": ["subagent-driven-development", "dispatching-parallel-agents", "autonomous-loops", "executing-plans"]},
    {"id": "web-design", "about": "website landing page ui ux visual design frontend animation css responsive layout "
     "typography accessibility premium",
     "members": ["frontend-design", "*:frontend-design", "taste-skill:*", "impeccable*", "ui-ux-pro-max:*", "gsap-*",
                 "web-design-guidelines", "scroll-animations", "accessible-motion", "animate", "awwwards-*",
                 "modern-web-guidance:*", "threejs-*", "nextjs-*", "emil-design-eng", "accessibility-review"],
     "entry": ["frontend-design", "impeccable", "taste-skill:taste-skill"]},
    {"id": "debugging", "about": "bug debug fix error failing test root cause regression review verify quality "
     "check audit",
     "members": ["systematic-debugging", "*debug*", "verification-before-completion", "test-driven-development",
                 "code-review*", "review", "investigate", "qa", "qa-only", "*:code-review"],
     "entry": ["systematic-debugging", "verification-before-completion"]},
    {"id": "research", "about": "research analysis sources competitors market evidence compare study report deep dive",
     "members": ["research*", "market-research", "*:market-research", "*:deep-research", "the-fool",
                 "citation-integrity-auditor", "competitive-*", "*-scraper", "customer-discovery"],
     "entry": ["research-ops", "market-research", "the-fool"]},
    {"id": "writing", "about": "writing text copy edit humanize russian article email landing page content",
     "members": ["avoid-ai-writing*", "humanizer*", "antiplagiat", "*copywriting", "*copy-editing", "content-*",
                 "landing-page-copy", "email-sequences", "*:writing-*", "writing-*"],
     "entry": ["avoid-ai-writing-russian", "landing-page-copy"]},
    {"id": "growth", "about": "marketing growth seo ads advertising campaign outreach email sales customers funnel",
     "members": ["marketing-skills:*", "ads*", "seo*", "cold-email*", "email-sequences", "*outreach*",
                 "pricing-strategy", "*:pricing", "sales-*"],
     "entry": ["marketing-skills:marketing-plan", "cold-email-writer"]},
    {"id": "learning", "about": "study learn teach exam memory practice explain tutor course",
     "members": ["study-*", "learn", "*:learn", "mom-test", "*teach*", "*tutor*"],
     "entry": ["study-habits", "learn"]},
    {"id": "media", "about": "video audio image generation editing film clip music voice thumbnail render",
     "members": ["ffmpeg*", "higgsfield*", "kling*", "seedance*", "remotion*", "youtube-*", "hyperframes:*",
                 "video*", "*-video"],
     "entry": ["higgsfield-generate", "ffmpeg"]},
    {"id": "automation", "about": "automation workflow n8n integration scheduled task api script pipeline",
     "members": ["n8n*", "schedule", "*:schedule", "loop", "*:loop", "workflow-*", "*:workflow-*"],
     "entry": ["n8n-workflow-patterns"]},
]


def _members(skills, patterns):
    out, seen = [], set()
    for s in skills:
        if s.get("manual") or s["name"] in seen:
            continue
        if any(fnmatch.fnmatchcase(s["name"], p) or fnmatch.fnmatchcase(s["short"], p) for p in patterns):
            seen.add(s["name"])
            out.append(s)
    return out


def discover(skills, user_packs):
    """Sets available right now: built-in ones with at least two installed members, every plugin with three or more
    skills, every name family (founder-*, threejs-*) with four or more, and the person's own sets."""
    found = []
    for b in BUILTIN:
        m = _members(skills, b["members"])
        if len(m) >= 2:
            found.append({"id": b["id"], "about": b["about"], "members": m, "entry": b["entry"], "kind": "builtin"})
    curated = [{s["name"] for s in p["members"]} for p in found]
    by_plugin, by_family = {}, {}
    for s in skills:
        if s.get("manual"):
            continue
        if s["source"] == "plugin":
            by_plugin.setdefault(s["plugin"], []).append(s)
        head = s["short"].split("-")[0]
        if "-" in s["short"] and len(head) > 2:
            by_family.setdefault(head, []).append(s)
    auto = [{"id": "plugin:" + k, "about": k.replace("-", " "), "members": v, "entry": [], "kind": "plugin"}
            for k, v in by_plugin.items() if len(v) >= 3]
    auto += [{"id": "family:" + k, "about": k, "members": v, "entry": [], "kind": "family"}
             for k, v in by_family.items() if len(v) >= 4]
    for a in auto:
        names = {s["name"] for s in a["members"]}
        if not any(names <= c for c in curated):
            found.append(a)
    for pid, spec in (user_packs or {}).items():
        m = _members(skills, spec.get("members", []))
        if m:
            found.append({"id": pid, "about": spec.get("about", pid), "members": m,
                          "entry": spec.get("members", []), "kind": "user"})
    return found


def _entry(pack, scores, limit=3):
    entry = sorted((m for m in pack["members"] if scores.get(m["name"], 0) > 0), key=lambda m: -scores[m["name"]])[:limit]
    for pat in pack["entry"]:
        for m in pack["members"]:
            if len(entry) < limit and m not in entry and (fnmatch.fnmatchcase(m["name"], pat)
                                                          or fnmatch.fnmatchcase(m["short"], pat)):
                entry.append(m)
    for m in pack["members"]:
        if len(entry) < limit and m not in entry:
            entry.append(m)
    return entry[:limit]


def pick(found, ranked, weights, cfg):
    """The best one or two sets for this task, each with the skills to enter it by."""
    if not found or not cfg.get("pack_n"):
        return []
    scores = {s["name"]: sc for sc, s in ranked}
    docs = [{"name": p["id"], "short": p["id"], "manual": False,
             "desc": p["about"] + " " + " ".join(m["short"] for m in p["members"])} for p in found]
    own = {s["name"]: sc for sc, s in match.Ranker(docs).rank(weights)}
    scored = []
    for p in found:
        top3 = sorted((scores.get(m["name"], 0.0) for m in p["members"]), reverse=True)[:3]
        scored.append((own.get(p["id"], 0.0) + 0.6 * sum(top3), p))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] <= 0:
        return []
    floor = max(cfg["min_pack_score"], 0.5 * scored[0][0])
    return [{"id": p["id"], "size": len(p["members"]), "entry": _entry(p, scores), "score": sc}
            for sc, p in scored if sc >= floor][:cfg["pack_n"]]

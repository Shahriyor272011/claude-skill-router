"""The words Claude reads. Short, concrete, and written to be acted on rather than obeyed."""
import re

TEXT = {
    "en": {
        "head": "skill-router · phase: {phase} · mode: {mode}",
        "strong": "Start with these skills:",
        "also": "Also relevant: {names}",
        "pack": "Skill set: {id} ({size}) → {entry}",
        "loaded": "Already loaded this session: {names}",
        "use_gate": "Call the skills that fit before you change anything, and skip the ones that don't. If none fits, "
                    "call skill-router:none-fits with a one-line reason.",
        "use_soft": "Use what fits and skip the rest.",
        "phase": "Moving to another phase (plan, build, verify, ship)? Run: skill-router phase <name> --query \"<one line>\"",
        "deny": "skill-router ({mode}): this task has matching skills you have not loaded yet. Call {names} with the "
                "Skill tool, or call skill-router:none-fits with a one-line reason if none really fits. The next "
                "attempt goes through.",
    },
    "ru": {
        "head": "skill-router · фаза: {phase} · режим: {mode}",
        "strong": "Подходящие скиллы (начните с них):",
        "also": "Также подходят: {names}",
        "pack": "Набор скиллов: {id} ({size}) → {entry}",
        "loaded": "Уже загружены в этой сессии: {names}",
        "use_gate": "Вызовите подходящие скиллы до любых изменений, неподходящие пропустите. Если ничего не подходит, "
                    "вызовите skill-router:none-fits с причиной в одну строку.",
        "use_soft": "Используйте то, что подходит, остальное пропустите.",
        "phase": "Переходите к другой фазе (plan, build, verify, ship)? Выполните: skill-router phase <имя> --query \"<одна строка>\"",
        "deny": "skill-router ({mode}): у задачи есть подходящие скиллы, которые ещё не загружены. Вызовите {names} через "
                "инструмент Skill или вызовите skill-router:none-fits с причиной в одну строку, если ничего не подходит. "
                "Следующая попытка пройдёт.",
    },
}


def clip(desc, n=90):
    first = re.split(r"(?<=[.;])\s", desc.strip())[0]
    return first if len(first) <= n else first[:n - 1].rstrip() + "…"


def context(cfg, phase, strong, also, picks, loaded, gated):
    t = TEXT[cfg["language"]]
    lines = [t["head"].format(phase=phase, mode=cfg["mode"])]
    if strong:
        lines.append(t["strong"])
        lines += ["- %s: %s" % (s["name"], clip(s["desc"])) for s in strong[:4]]
        also = list(strong[4:]) + list(also)
    if also:
        lines.append(t["also"].format(names=", ".join(s["name"] for s in also)))
    for p in picks:
        lines.append(t["pack"].format(id=p["id"], size=p["size"], entry=", ".join(s["name"] for s in p["entry"])))
    if loaded:
        lines.append(t["loaded"].format(names=", ".join(loaded)))
    if strong or also or picks:
        lines.append(t["use_gate"] if gated else t["use_soft"])
    lines.append(t["phase"])
    return "\n".join(lines)


def deny(cfg, names):
    return TEXT[cfg["language"]]["deny"].format(mode=cfg["mode"], names=", ".join(names[:3]))

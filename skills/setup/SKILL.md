---
name: setup
description: Tunes skill-router to one person. Learns what they work on, picks the mode, teaches the matcher their language and pins skills per phase. Run once after installing and again when the work changes.
disable-model-invocation: true
allowed-tools: Bash(skill-router *)
---

# Tune skill-router to this person

The router should suggest the right skills for this person's work, in their words and language, without nagging. The setup is done when `skill-router suggest "<a real task of theirs>"` returns skills they would pick themselves, for three different tasks.

Ask one question at a time, in the person's language. Run everything through `skill-router`; it keeps all settings in one profile, so leave `settings.json` alone.

1. **See what exists.** Run `skill-router status`. It lists installed skills, the skill sets found, the current mode and how much the skill list costs every session.
2. **Learn the work.** Ask what they do week to week. Ask for three or four tasks in the exact words they would type or dictate.
3. **Choose the mode.** Recommend `guided`: every task gets suggestions, one change is held back per phase and only when a skill fits strongly, tiny edits are never held back. `suggest` never holds anything back, `strict` holds back until a skill is used, `off` pauses the router. Apply with `skill-router profile set mode <mode>` and `skill-router profile set language <en|ru>`.
4. **Run their tasks.** Run `skill-router suggest "<task>"` for each. For every skill that should have matched but did not, teach the matcher the person's own vocabulary: `skill-router profile alias <skill> <word> <word> ...`, five to eight words they would actually say. Stemming covers inflections, so one form of each word is enough.
5. **Pin phase skills.** Offer at most two installed skills per phase (plan, build, verify, ship), for example a verification skill for verify. Apply with `skill-router profile pin <phase> <skill>`. Offer only skills that `skill-router suggest` or `status` showed as installed.
6. **Define their sets.** When their work has a recurring shape that spans several skills, name it: `skill-router profile pack <id> <skill> <skill> ...` and `skill-router profile about <id> <keywords>`.
7. **Silence noise.** Skills they never want to see: `skill-router profile ignore <skill>`.
8. **Confirm.** Re-run their tasks, show the result, adjust until it looks right to them. Close with three lines: what changed, where the profile lives (`skill-router doctor` prints it), and how to undo (`skill-router profile reset`).

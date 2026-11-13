# Skill Router

A Claude Code plugin that finds the skills that fit **each task and each work phase**, shows them to Claude on every request, and, in the default mode, holds back the first change until a skill has been used. It never blocks tiny edits and never blocks twice.

[Русская версия](README.ru.md)

## Why

With a few hundred skills installed, Claude Code cannot show every description: when the list outgrows its budget, descriptions are dropped, starting with the skills you use least, and a skill without a description is almost never picked. Telling Claude to "check all your skills" does not help, because there is nothing left to check against. Forcing a skill call on every turn does worse: it produces ritual calls that cost time and add nothing.

Skill Router searches the *full* set of skills on your side, in a hook, and gives Claude a short ranked answer. A skill call is requested only when the match is strong.

## What it does on every prompt

1. **Ranks your installed skills** (user, project and plugin skills) against the request: BM25 over skill name, description and your own aliases. Skills you actually use rank a little higher; skills suggested again and again but never used fade, down to half.
2. **Shows tiers.** Strong matches (at most four) with a one-line reason, related skills by name only, so recall stays high and the context small (under 1.8 KB).
3. **Picks one or two skill sets.** A set is a group of skills that belong together: built-in ones (`business`, `orchestration`, `web-design`, `debugging`, `research`, `writing`, `growth`, `learning`, `media`, `automation`), every plugin with three or more skills, every name family such as `founder-*`, and sets you define. Claude gets the set's name and the skills to enter it by.
4. **Knows the phase** (plan, build, verify, ship). Skills you pinned to a phase are added, and Claude is told to run `skill-router phase <name>` when the work moves on, which reopens the check for the next phase.
5. **Understands Russian.** A built-in lexicon maps common Russian task words to the English terms skills use; `/skill-router:setup` teaches it your own words for any language.

## Modes

| Mode | Suggestions | Holds back changes |
|---|---|---|
| `off` | none | never |
| `suggest` | every task | never |
| `guided` (default) | every task | once per phase, only when a strong match exists and no skill was used, never for tiny edits (typo, rename, format) |
| `strict` | every task | until a skill is used, up to three times per phase |

"Holding back" means a `PreToolUse` denial on Edit, Write, MultiEdit, NotebookEdit, Agent and Bash commands that change things. Read-only commands (`ls`, `git status`, `grep`, ...) always pass. Claude can leave at any time with the `skill-router:none-fits` skill and a one-line reason, so a wrong match never traps it. Subagents are not gated. A skill you type yourself (`/frontend-design ...`) counts as your choice.

## Install

```
/plugin marketplace add Shahriyor272011/claude-skill-router
/plugin install skill-router@skill-router
```

Then run `/skill-router:setup` once. It asks what you work on, picks a mode, teaches the matcher your vocabulary, pins phase skills and defines your own sets.

Requirements: Claude Code 2.1.271 or newer, `python3` on the PATH (standard library only, no network access, developed on 3.14).

## Commands

| Command | What it does |
|---|---|
| `/skill-router:setup` | One-time tuning for you |
| `/skill-router:status` | Skills installed, what the list costs per session, suggested vs used, prune candidates |
| `/skill-router:phase <phase> <task>` | Skills for the next phase |
| `skill-router suggest "<task>"` | Dry run: what would be suggested, with scores |
| `skill-router doctor` | Checks the install and shows a sample |
| `skill-router profile ...` | `set`, `alias`, `pin`, `ignore`, `prefer`, `pack`, `about`, `reset` |

The profile lives in the plugin data directory (`skill-router doctor` prints it). Plugin options and `profile.json` both set the mode; `profile.json` wins.

## Privacy

Everything stays on your machine. The router makes no network calls. Its journal records skill names, phases and events only, never prompt text. `journal` can be turned off with `skill-router profile set journal false`.

## Limits

- Matching is lexical, on skill descriptions. A skill with a vague description is found less reliably; add aliases for it.
- The built-in lexicon covers common Russian task words. Other languages work through aliases.
- Intent handling is a heuristic: bug and failure words raise debugging skills above topic words, and tiny edits are recognised by a short word list.
- Plugin commands (`commands/*.md`) are not indexed, skills only.
- Not tested on Windows. Verified: 57 unit tests, the hook entry points driven with the JSON Claude Code sends, and a real Claude Code process loading the plugin and running the prompt hook. A full model-in-the-loop session is the next thing to try, and reports are welcome.

## Troubleshooting

- Silent? Run `skill-router doctor`. Check `errors.log` in the data directory: every hook fails open, so a bug logs there instead of blocking you.
- Too strict or too chatty? `skill-router profile set mode suggest`, or `off`.
- A skill keeps appearing and you never want it: `skill-router profile ignore <skill>`.

## Development

```
python3 -m unittest discover -s tests
claude plugin validate .
```

## License

MIT

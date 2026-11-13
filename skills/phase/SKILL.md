---
name: phase
description: Use when the work moves to another phase (plan, build, verify or ship) to get the skills for that phase. Takes the phase name and a one-line summary of the task.
allowed-tools: Bash(skill-router *)
---

# Skills for the next phase

Arguments: `$ARGUMENTS` (the phase, then the task in one line).

Run `skill-router phase <phase> --query "<the task in one line>"`. The phase is one of plan, build, verify, ship. It prints the skills pinned for that phase, the best matches for the task and the skill sets worth entering.

Call the ones that fit before continuing. When none fits, call `skill-router:none-fits` with a one-line reason.

---
name: status
description: Shows what skill-router knows. Installed skills and their listing cost, skill sets found, which suggestions were used and which were ignored, and skills that could be pruned.
disable-model-invocation: true
allowed-tools: Bash(skill-router *)
---

Run `skill-router status` and explain the result in plain words: how many skills are installed, what the skill list costs every session, which suggested skills the person never used, and, once at least twenty requests have been routed, which installed skills were never suggested or used.

Offer to hide skills that were suggested often and never used with `skill-router profile ignore <skill>`. Recommend pruning only from this evidence, and never delete or move skills yourself.

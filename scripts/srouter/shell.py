"""Decides whether a Bash command only reads. Anything unclear counts as a change."""
import os
import re
import shlex

READONLY = {"ls", "cat", "head", "tail", "wc", "pwd", "echo", "which", "whoami", "date", "stat", "file", "du", "df",
            "grep", "rg", "tree", "jq", "sort", "uniq", "cut", "tr", "type", "env", "printenv", "test", "[", "true",
            "false", "basename", "dirname", "realpath", "readlink", "uname", "hostname", "id", "cd", "less", "more",
            "diff", "cmp", "column", "nl", "tac", "shasum", "sha256sum", "md5", "skill-router"}
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "ls-files", "blame", "describe", "ls-remote", "shortlog",
            "reflog"}
GIT_LIST_ONLY = {"branch", "tag"}
JOINERS = {"&&", "||", "|", ";", "&"}


def is_readonly(cmd):
    cmd = re.sub(r"\d*>\s*/dev/null|\d*>&\d+|&>\s*/dev/null", "", cmd or "")
    if ">" in cmd or "<<" in cmd or "$(" in cmd or "`" in cmd:
        return False
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return False
    segments, cur = [], []
    for t in toks:
        if t in JOINERS:
            segments.append(cur)
            cur = []
        else:
            cur.append(t)
    segments.append(cur)
    for seg in segments:
        while seg and re.match(r"^[A-Za-z_]\w*=", seg[0]):
            seg = seg[1:]
        if not seg:
            continue
        first = os.path.basename(seg[0])
        if first == "git":
            sub, rest = (seg[1] if len(seg) > 1 else ""), seg[2:]
            if sub in GIT_READ or (sub in GIT_LIST_ONLY and all(a.startswith("-") for a in rest)):
                continue
            return False
        if first not in READONLY:
            return False
    return True

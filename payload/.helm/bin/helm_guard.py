#!/usr/bin/env python3
"""HELM hook guard. One entry point for every Cursor hook; mode is argv[1].

  shell    beforeShellExecution   -> allow/deny
  mcp      beforeMCPExecution     -> allow/deny
  tool     preToolUse             -> allow/deny   (writes, reads, web, task)
  read     beforeReadFile         -> allow/deny
  subagent subagentStart          -> allow/deny   (default: audit only)
  session  sessionStart           -> additional_context (best effort)
  postedit afterFileEdit          -> records a violation if a pre-hook was bypassed

Permission modes FAIL CLOSED: any internal error returns deny.
This is a speed bump for a cooperating model, not a security boundary against a determined
adversary. See docs/THREAT-MODEL.md for what is and is not enforced.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True  # never leave untracked .pyc in the workspace
import json
import os
import re
import shlex
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helm_lib as L  # noqa: E402

PERMISSION_MODES = {"shell", "mcp", "tool", "read", "subagent"}
CANARY = "HELM_CANARY_DENY"

SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
INTERP = {"python", "python3", "node", "nodejs", "deno", "bun", "perl", "ruby", "php", "lua"}
WRAPPERS = {"env", "nohup", "time", "command", "exec", "nice", "timeout", "xargs", "stdbuf", "setsid", "ionice", "builtin"}
XARGS_ARG_OPTS = {"-n", "-I", "-P", "-L", "-s", "-d", "-E", "-a", "-l", "-i"}
MUTATORS = {"rm", "rmdir", "mv", "cp", "chmod", "chown", "chgrp", "ln", "truncate", "dd", "tee", "install",
            "rsync", "touch", "mkdir", "shred", "unlink", "patch"}
READ_ONLY = {"cat", "head", "tail", "less", "more", "ls", "grep", "egrep", "fgrep", "rg", "ag", "wc", "diff", "cmp",
             "stat", "file", "find", "sha256sum", "sha1sum", "md5sum", "shasum", "tree", "du", "realpath", "basename",
             "dirname", "jq", "echo", "printf", "test", "[", "sort", "uniq", "cut", "awk", "readlink", "nl", "column",
             "tr", "xxd", "od", "strings", "bat", "git", "pwd", "cd", "true", "false", "which", "type", "date", "sed"}
FIND_DANGER = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
HELM_NAMES = {"helm", "helm.py", "helm_lib.py", "helm_guard.py"}
HELM_AGENT_OK = {"status", "check", "verify", "metrics", "log", "version", "--version", "help", "--help", "-h"}

ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
STATE_RE = re.compile(r"(\.helm/(state|key)\b|~/\.helm\b|\bHELM_HOME\b|\$\{?HOME\}?/\.helm\b)")
GIT_RAW_RE = re.compile(
    r"\bgit\b[^\n]{0,200}?\b(commit|push|merge|rebase|reset|checkout|switch|restore|clean|cherry-pick|revert|am|apply|"
    r"pull|fetch|clone|init|worktree|submodule|update-ref|add|rm|mv|stash|tag)\b")
NET_RAW_RE = re.compile(r"\b(curl|wget|ssh|scp|nc|ncat|netcat|gh|glab)\b|urllib|requests\.|http\.client|socket\.|fetch\(|XMLHttpRequest")
SEP = {";", "&&", "||", "|", "&", "|&", "(", ")", ";;"}
CODE_FLAGS = {"-c", "-e", "-p", "--eval", "--print", "-pe", "-ne"}

GIT_RO = {"status", "diff", "log", "show", "rev-parse", "rev-list", "ls-files", "ls-tree", "blame", "shortlog",
          "describe", "grep", "cat-file", "merge-base", "name-rev", "for-each-ref", "show-ref", "diff-tree",
          "diff-index", "diff-files", "check-ignore", "count-objects", "version", "help", "whatchanged",
          "range-diff", "cherry", "show-branch", "annotate"}
GIT_SKIP_GLOBAL = {"--no-pager", "-P", "--paginate", "-p", "--no-optional-locks", "--literal-pathspecs",
                   "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs", "--no-replace-objects"}
GIT_DANGER_FLAGS = ("--output", "--open-files-in-pager", "--ext-diff", "--exec", "--upload-pack", "--receive-pack")

PM = {"npm", "pnpm", "yarn", "bun"}
PM_RUNNERS = {"npx", "pnpx", "bunx"}
PM_STRICT = {"add", "remove", "rm", "uninstall", "un", "unlink", "link", "publish", "login", "logout", "adduser",
             "token", "owner", "dist-tag", "deprecate", "unpublish", "access", "team", "org", "update", "upgrade",
             "up", "dedupe", "dlx", "create", "patch", "patch-commit"}
OTHER_PM = {"pip": {"install", "uninstall"}, "pip3": {"install", "uninstall"}, "poetry": {"add", "remove", "publish"},
            "cargo": {"add", "install", "publish", "remove"}, "gem": {"install", "push"},
            "composer": {"require", "remove"}, "dotnet": {"add", "publish", "nuget"}, "uv": {"add", "remove", "publish"}}

READ_TOOLS = {"read", "readfile", "grep", "glob", "globfilesearch", "ls", "listdir", "listdirectory", "readlints",
              "semanticsearch", "codebasesearch", "filesearch", "search", "todowrite", "askquestion", "switchmode",
              "createplan", "readnotebook", "notebookread"}
DELETE_TOOLS = {"delete", "deletefile", "removefile", "remove"}
WRITE_TOOLS = {"write", "edit", "editfile", "strreplace", "searchreplace", "multiedit", "applypatch", "patch",
               "notebookedit", "editnotebook", "createfile", "newfile", "writefile", "movefile", "renamefile"} | DELETE_TOOLS


# --------------------------------------------------------------------------- responses
def allow():
    return {"continue": True, "permission": "allow"}


def deny(reason, hint=""):
    msg = (f"HELM POLICY_BLOCK: {reason}. {hint}Do not retry or look for another route. "
           "Report POLICY_BLOCK with this reason to the human and stop.")
    return {"continue": True, "permission": "deny", "user_message": f"HELM blocked: {reason}", "agent_message": msg}


class Ctx:
    def __init__(self, root, pol, cwd=None):
        self.root = Path(root)
        self.pol = pol
        self.cwd = cwd or str(root)
        self.active, self.tampered = L.load_active(self.root)
        self._info = None

    @property
    def task(self):
        return self.active.get("task") if self.active and self.active.get("kind") == "task" else None

    @property
    def info(self):
        if self._info is None and self.task:
            self._info = L.derive(self.root, self.pol, self.active)
        return self._info


# --------------------------------------------------------------------------- shell analysis
def base(t: str) -> str:
    return os.path.basename(t)


def tokenize(cmd: str):
    cmd = cmd.replace("\r", "").replace("\n", " ; ")
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        toks = cmd.split()
    segs = [[]]
    for t in toks:
        if t in SEP:
            segs.append([])
        else:
            segs[-1].append(t)
    return [s for s in segs if s]


def strip_wrappers(argv):
    while argv and ENV_RE.match(argv[0]):
        argv = argv[1:]
    while argv and base(argv[0]) in WRAPPERS:
        w, argv = base(argv[0]), argv[1:]
        while argv:
            a = argv[0]
            if ENV_RE.match(a) or a.startswith("-"):
                argv = argv[2:] if (w == "xargs" and a in XARGS_ARG_OPTS) else argv[1:]
            elif w in ("timeout", "nice") and re.match(r"^[0-9.]+[smhd]?$", a):
                argv = argv[1:]
            else:
                break
        while argv and ENV_RE.match(argv[0]):
            argv = argv[1:]
    return argv


def git_policy(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-C":
            i += 2
            continue
        if a == "-c" or a.startswith(("--config-env", "--git-dir", "--work-tree", "--exec-path", "--namespace",
                                      "--super-prefix", "--attr-source")):
            return [f"git global option `{a}` is not allowed"]
        if a in GIT_SKIP_GLOBAL:
            i += 1
            continue
        if a.startswith("-"):
            return [f"unknown git global option `{a}`"]
        break
    else:
        return []
    sub, rest = args[i], args[i + 1:]
    for t in rest:
        if t.startswith(GIT_DANGER_FLAGS):
            return [f"git flag `{t}` is not allowed"]
    flags = {t for t in rest if t.startswith("-")}
    pos = [t for t in rest if not t.startswith("-")]
    bad = lambda: [f"`git {sub}` can change repository state — Git belongs to the developer (read-only git only)"]
    if sub in GIT_RO:
        return []
    if sub == "branch":
        if flags & {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "--force", "--delete", "--move", "--copy", "-u",
                    "--set-upstream-to", "--unset-upstream", "--edit-description", "--track", "--no-track", "-t"}:
            return bad()
        listing = flags & {"--list", "-l", "--contains", "--merged", "--no-merged", "--points-at", "--show-current"}
        return [] if (not pos or listing) else bad()
    if sub == "stash":
        return [] if pos[:1] in (["list"], ["show"]) else bad()
    if sub == "remote":
        return [] if (not pos or pos[0] in ("show", "get-url")) else bad()
    if sub == "config":
        if flags & {"--add", "--unset", "--unset-all", "--replace-all", "--edit", "-e", "--rename-section",
                    "--remove-section", "--global", "--system"} and not flags & {"--get", "--get-all", "--list", "-l"}:
            return bad()
        return [] if flags & {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin"} else bad()
    if sub == "worktree":
        return [] if pos[:1] == ["list"] else bad()
    if sub == "reflog":
        return [] if (not pos or pos[0] in ("show", "exists")) else bad()
    if sub == "tag":
        return [] if (not pos or flags & {"-l", "--list", "--contains", "--points-at", "-n", "-v", "--verify", "--sort"}) \
            and not flags & {"-d", "-a", "-s", "-f", "-m", "--delete"} else bad()
    return bad()


def helm_policy(args):
    pos = [a for a in args if not a.startswith("-")]
    sub = pos[0] if pos else (args[0] if args else "")
    if not sub or sub in HELM_AGENT_OK:
        return []
    if sub == "doctor":
        return [] if "--live" not in args else ["`helm doctor --live` launches Cursor and is human-only"]
    if sub == "skills" and len(pos) > 1 and pos[1] in ("verify", "list"):
        return []
    return [f"`helm {sub}` is a human-only command (approvals/state are never agent-operated)"]


def pm_policy(b, args):
    if b in PM_RUNNERS:
        return [] if ("--no-install" in args or "--no" in args) else \
            [f"`{b}` executes arbitrary packages; use the project's scripts"]
    pos = [a for a in args if not a.startswith("-")]
    hit = [a for a in pos if a in PM_STRICT]
    if hit:
        return [f"`{b} {hit[0]}` changes dependencies/registry state — needs a human decision"]
    for i, a in enumerate(pos):
        if a in ("install", "i") and pos[i + 1:]:
            return [f"`{b} {a} <package>` adds dependencies — needs a human decision (plain `install`/`ci` is fine)"]
        if a == "config" and pos[i + 1:i + 2] and pos[i + 1] in ("set", "delete", "edit"):
            return [f"`{b} config {pos[i + 1]}` is not allowed"]
    return []


def other_pm_policy(b, args):
    pos = [a for a in args if not a.startswith("-")]
    hit = [a for a in pos if a in OTHER_PM[b]]
    if not hit:
        return []
    if b in ("pip", "pip3") and any(a in ("-r", "--requirement") for a in args):
        return []
    return [f"`{b} {hit[0]}` changes dependencies — needs a human decision"]


def raw_code_scan(code, ctx):
    v = []
    if GIT_RAW_RE.search(code):
        v.append("interpreted code appears to run a state-changing git command")
    if NET_RAW_RE.search(code):
        v.append("interpreted code appears to use network/forge tooling")
    if STATE_RE.search(code):
        v.append("interpreted code references HELM state/key")
    for g in ctx.pol.get("protected_paths", []):
        lit = L.static_prefix(g)
        if lit and lit in code:
            v.append(f"interpreted code references protected path `{lit}`")
            break
    return v


def iter_paths(args):
    """yield (token, is_write_redirect)"""
    i = 0
    while i < len(args):
        a = args[i]
        if a and set(a) <= set("<>&|") and ("<" in a or ">" in a):
            tgt = args[i + 1] if i + 1 < len(args) else ""
            if tgt and not re.fullmatch(r"[0-9-]+", tgt):
                yield tgt, ">" in a
            i += 2
            continue
        if a.startswith("-"):
            if "=" in a:
                yield a.split("=", 1)[1], False
        else:
            yield a, False
        i += 1


def path_checks(argv, b, ctx):
    v = []
    args = argv[1:]
    mut = b in MUTATORS
    if b in ("rm", "rmdir", "unlink", "shred"):
        v.append(f"file deletion via `{b}` is prohibited for AI agents (human verification required)")
    if b in ("sed", "perl") and any(a == "--in-place" or (a.startswith("-") and not a.startswith("--") and "i" in a[1:])
                                    for a in args):
        mut = True
    if b == "find" and any(a in FIND_DANGER for a in args):
        v.append("`find` with -exec/-delete/-fprint is not allowed")
    for tok, is_w in iter_paths(args):
        if b == "dd" and "=" in tok:
            tok, is_w = tok.split("=", 1)[1], True
        if not tok or tok == "-":
            continue
        q = L.resolve(ctx.root, tok, ctx.cwd)
        c = L.classify(ctx.root, ctx.pol, q)
        write = mut or is_w
        if c["state"]:
            v.append(f"touches HELM state ({tok})")
        elif c["secret"]:
            v.append(f"touches a secret path ({tok})")
        elif c["git"] and write:
            v.append(f"writes inside .git ({tok})")
        elif c["protected"] and (write or b not in READ_ONLY):
            v.append(f"modifies/executes protected path ({tok})")
        elif c["outside"] and write and not L.is_tmp(q):
            v.append(f"writes outside the repository ({tok})")
        elif write and not c["outside"] and ctx.active is not None:
            ok, why = L.check_write(ctx.root, ctx.pol, q, ctx.active, ctx.tampered, ctx.info)
            if not ok:
                v.append(f"write to {tok} not allowed: {why}")
    return v


def check_segment(argv, ctx, depth):
    argv = strip_wrappers(argv)
    if not argv:
        return []
    b = base(argv[0])
    deny_cmds = set(ctx.pol.get("shell", {}).get("deny_commands", []))
    if b in HELM_NAMES:
        return helm_policy(argv[1:])
    if b in INTERP and len(argv) > 1 and base(argv[1]) in HELM_NAMES:
        return helm_policy(argv[2:])
    if b in deny_cmds:
        return [f"command `{b}` is denied by policy"]
    v = []
    if b == "git":
        v += git_policy(argv[1:])
    elif b in SHELLS:
        for i, a in enumerate(argv[1:], 1):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:] and i + 1 < len(argv):
                v += analyze_shell(argv[i + 1], ctx, depth + 1)
                break
    elif b in INTERP:
        for i, a in enumerate(argv[1:], 1):
            if a in CODE_FLAGS and i + 1 < len(argv):
                v += raw_code_scan(argv[i + 1], ctx)
    elif b in PM or b in PM_RUNNERS:
        v += pm_policy(b, argv[1:])
    elif b in OTHER_PM:
        v += other_pm_policy(b, argv[1:])
    v += path_checks(argv, b, ctx)
    return v


def analyze_shell(cmd, ctx, depth=0):
    if depth > 4:
        return ["shell nesting too deep"]
    if CANARY in cmd:
        return ["canary"]
    v = []
    if STATE_RE.search(cmd) or str(L.helm_home()) in cmd:
        v.append("references HELM state/key (human-only)")
    for m in re.finditer(r"`([^`]*)`", cmd):
        v += analyze_shell(m.group(1), ctx, depth + 1)
    for seg in tokenize(cmd):
        v += check_segment(seg, ctx, depth)
    return v


# --------------------------------------------------------------------------- handlers
def h_shell(p, ctx):
    cmd = p.get("command", "") or ""
    if p.get("cwd"):
        ctx.cwd = p["cwd"]
    v = analyze_shell(cmd, ctx)
    if v == ["canary"]:
        m = re.search(r"HELM_CANARY_DENY_(\w+)", cmd)
        L.audit(ctx.root, "_doctor", {"k": "canary", "nonce": m.group(1) if m else "", "via": "shell"})
        return deny("canary command (doctor self-test) — hooks are active")
    L.audit(ctx.root, ctx.task, {"k": "shell", "c": cmd[:200], "ok": not v})
    return allow() if not v else deny("; ".join(dict.fromkeys(v))[:400])


def h_mcp(p, ctx):
    m = ctx.pol.get("mcp", {})
    server = p.get("mcp_server_name") or p.get("server") or ""
    tool = p.get("tool_name") or ""
    if not server:
        return deny("MCP call without a server name (unknown server → deny)")
    if server not in m.get("allow_servers", []):
        return deny(f"MCP server `{server}` is not on the allowlist")
    t = re.sub(rf"^(?:mcp[_-])?{re.escape(server)}[_-]", "", tool, flags=re.I)
    if not re.search(m.get("allow_tool_regex", r"^$"), t):
        return deny(f"MCP tool `{tool}` is not a read-only tool (writes to Jira/Confluence are human-only)")
    task = ctx.task
    n = L.bump_counter(ctx.root, task, "mcp")
    if n > int(m.get("max_calls_per_task", 60)):
        return deny("MCP call budget for this task exhausted", "Ask the human how to proceed. ")
    if re.search(m.get("confluence_regex", r"(?i)confluence"), t):
        c = L.bump_counter(ctx.root, task, "confluence")
        if c > int(m.get("confluence_max_calls", 6)):
            return deny("Confluence call budget exhausted (Confluence is an escalation path)",
                        "Record the open question in BLOCKED.md instead. ")
    L.audit(ctx.root, task, {"k": "mcp", "s": server, "t": tool})
    return allow()


def _norm(n):
    return re.sub(r"[^a-z]", "", (n or "").lower())


def _find_url(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in ("url", "uri", "href") and isinstance(v, str):
                return v
            r = _find_url(v)
            if r:
                return r
    return ""


def h_web(name, inp, ctx):
    w = ctx.pol.get("web", {})
    if name == "websearch":
        return allow() if w.get("allow_search") else deny("built-in web search is disabled by policy")
    url = _find_url(inp)
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host:
        return deny("web fetch needs an https URL")
    if any(host == d or host.endswith("." + d) for d in w.get("fetch_domains", [])):
        L.audit(ctx.root, ctx.task, {"k": "web", "h": host})
        return allow()
    return deny(f"web fetch to `{host}` is not on the domain allowlist")


def h_tool(p, ctx):
    name = _norm(p.get("tool_name"))
    inp = p.get("tool_input") or {}
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            inp = {"raw": inp}
    if name in ("shell", "bash", "terminal", "runterminalcmd", "task") or name.startswith("mcp"):
        return allow()  # covered by dedicated hooks
    if name in ("webfetch", "fetchurl", "websearch"):
        return h_web(name, inp, ctx)
    paths = L.extract_paths(inp)
    cwd = p.get("cwd") or ctx.cwd
    if name in READ_TOOLS:
        for pp in paths[:20]:
            c = L.classify(ctx.root, ctx.pol, L.resolve(ctx.root, pp, cwd))
            if c["secret"] or c["state"]:
                return deny(f"reading `{pp}` is not allowed (secret/state path)")
            if c["rel"] is not None:
                L.audit(ctx.root, ctx.task, {"k": "read", "p": c["rel"]})
        return allow()
    is_write = name in WRITE_TOOLS or (bool(paths) and name not in READ_TOOLS)
    if not is_write:
        return allow()
    if not paths:
        if name in WRITE_TOOLS and ctx.pol.get("unknown_payload", "deny") == "deny":
            return deny(f"cannot determine the target path of tool `{p.get('tool_name')}`",
                        "The human can inspect payloads with `helm doctor --probe`. ")
        return allow()
    for pp in paths:
        q = L.resolve(ctx.root, pp, cwd)
        ok, why = L.check_write(ctx.root, ctx.pol, q, ctx.active, ctx.tampered, ctx.info, is_delete=name in DELETE_TOOLS)
        if not ok:
            L.audit(ctx.root, ctx.task, {"k": "write_denied", "p": pp, "why": why})
            return deny(f"write to `{pp}` not allowed: {why}")
        c = L.classify(ctx.root, ctx.pol, q)
        if ctx.task and c["rel"] and c["rel"].endswith(f"{L.WORK_REL}/{ctx.task}/BLOCKED.md") and name not in DELETE_TOOLS:
            L.append_record(ctx.root, ctx.task, {"gate": "block", "decision": "raise", "note": "agent wrote BLOCKED.md"})
    return allow()


def h_read(p, ctx):
    fp = p.get("file_path") or p.get("path") or ""
    if not fp:
        return allow()
    c = L.classify(ctx.root, ctx.pol, L.resolve(ctx.root, fp, ctx.cwd))
    if c["secret"] or c["state"]:
        return deny(f"reading `{fp}` is not allowed (secret/state path)")
    return allow()


def h_subagent(p, ctx):
    sa = ctx.pol.get("subagents", {})
    mode = sa.get("mode", "audit")
    st = p.get("subagent_type") or p.get("name") or ""
    L.audit(ctx.root, ctx.task, {"k": "subagent", "t": st, "mode": mode})
    if mode == "deny_all":
        return deny("subagents are disabled by policy", "Do the role's work inline, following its .cursor/agents file. ")
    if mode == "allowlist" and st not in sa.get("allow", []):
        return deny(f"subagent `{st}` is not on the allowlist")
    return allow()


def h_session(p, ctx):
    if ctx.tampered:
        msg = "HELM: active-task state failed signature check. Do not write files; ask the human to run `helm doctor`."
    elif ctx.active and ctx.active.get("kind") == "bootstrap":
        msg = f"HELM bootstrap mode: write only under {L.BOOT_REL}/. Follow .cursor/agents/bootstrapper.md."
    elif ctx.task:
        i = ctx.info
        sc = L.write_scope(ctx.root, ctx.pol, i)
        w = ", ".join(sc["files"]) + (" + source" if sc["source"] else "")
        msg = (f"HELM task {i['task']} tier {i['tier']} phase {i['phase']}. Writable: {w or 'none'}. "
               "Run `helm status` for the next action. Human gates are never yours to pass.")
    else:
        msg = "HELM installed, no active task. Hard guardrails apply (no Git writes, no secrets, read-only Atlassian)."
    return {"additional_context": msg}


def h_postedit(p, ctx):
    fp = p.get("file_path") or ""
    if not fp:
        return {}
    q = L.resolve(ctx.root, fp, ctx.cwd)
    c = L.classify(ctx.root, ctx.pol, q)
    why = ""
    if c["git"] or c["state"] or c["secret"] or c["protected"] or (c["outside"] and not L.is_tmp(q)):
        why = "edit hit a protected/secret/outside path"
    elif ctx.task and c["rel"] is not None:
        i, rel = ctx.info, c["rel"]
        wd = i["work_dir"]
        if rel.startswith(L.WORK_REL + "/"):
            name = rel[len(wd) + 1:] if rel.startswith(wd + "/") else None
            if name is None or not (name in L.ARTIFACT_FILES or re.fullmatch(r"REVIEW-[\w.-]+\.md", name)):
                why = "edit to an unexpected work-dir path"
        elif not L.write_scope(ctx.root, ctx.pol, i)["source"] and not (
                i["phase"] == "TEST_ANALYSIS" and L.any_match(ctx.pol.get("test_globs", []), rel)):
            why = f"source edit in phase {i['phase']}"
    if why:
        L.audit(ctx.root, ctx.task, {"k": "violation", "p": fp, "why": why})
        if ctx.task:
            L.append_record(ctx.root, ctx.task, {"gate": "violation", "decision": "raise", "note": f"{fp}: {why}"})
    return {}


HANDLERS = {"shell": h_shell, "mcp": h_mcp, "tool": h_tool, "read": h_read, "subagent": h_subagent,
            "session": h_session, "postedit": h_postedit}


def run(mode, payload):
    try:
        start = os.environ.get("CURSOR_PROJECT_DIR") or (payload.get("workspace_roots") or [None])[0] or payload.get("cwd")
        root = L.find_root(start)
        pol = L.load_policy(root)
        ctx = Ctx(root, pol, payload.get("cwd"))
        h = HANDLERS.get(mode)
        if h is None:
            return deny(f"unknown guard mode `{mode}`") if mode in PERMISSION_MODES else {}
        return h(payload, ctx)
    except Exception as e:  # fail closed for permission hooks
        if mode in PERMISSION_MODES:
            return deny(f"guard internal error ({type(e).__name__}: {str(e)[:120]}) — failing closed")
        return {}


# --------------------------------------------------------------------------- self-test (used by `helm doctor`)
SELFTEST = [
    ("shell", {"command": "git status"}, True), ("shell", {"command": "git diff HEAD~1 -- src | head"}, True),
    ("shell", {"command": "git log --oneline -5"}, True), ("shell", {"command": "git branch --list"}, True),
    ("shell", {"command": "git stash list"}, True), ("shell", {"command": "git config --get user.name"}, True),
    ("shell", {"command": "git commit -m x"}, False), ("shell", {"command": "git -C . commit -m x"}, False),
    ("shell", {"command": "/usr/bin/git push origin HEAD"}, False), ("shell", {"command": "env git add ."}, False),
    ("shell", {"command": "bash -c 'git commit -m x'"}, False), ("shell", {"command": "git branch feature/x"}, False),
    ("shell", {"command": "git stash"}, False), ("shell", {"command": "git checkout main"}, False),
    ("shell", {"command": "git -c core.hooksPath=/x status"}, False),
    ("shell", {"command": "python3 -c \"import subprocess;subprocess.run(['git','commit'])\""}, False),
    ("shell", {"command": "gh pr create"}, False), ("shell", {"command": "curl https://example.com"}, False),
    ("shell", {"command": "sudo ls"}, False), ("shell", {"command": "npm install left-pad"}, False),
    ("shell", {"command": "pnpm --filter web add zod"}, False), ("shell", {"command": "npx jest"}, False),
    ("shell", {"command": "npm ci"}, True), ("shell", {"command": "pnpm test"}, True),
    ("shell", {"command": "cat .env"}, False), ("shell", {"command": "cat .env.example"}, True),
    ("shell", {"command": "echo x > .cursor/hooks.json"}, False), ("shell", {"command": "cat .cursor/hooks.json"}, True),
    ("shell", {"command": "sed -i s/a/b/ AGENTS.md"}, False),
    ("shell", {"command": "helm approve plan"}, False), ("shell", {"command": "python3 .helm/bin/helm approve final"}, False),
    ("shell", {"command": "helm status --json"}, True), ("shell", {"command": ".helm/bin/helm verify"}, True),
    ("shell", {"command": "cat ~/.helm/key"}, False), ("shell", {"command": "ls ~/.ssh"}, False),
    ("shell", {"command": "rm -rf /"}, False), ("shell", {"command": "rm -rf /etc/helm-selftest"}, False),
    ("shell", {"command": "echo hi > /tmp/helm-selftest"}, True),
    ("shell", {"command": "echo HELM_CANARY_DENY_selftest"}, False),
    ("mcp", {"mcp_server_name": "atlassian", "tool_name": "getJiraIssue"}, True),
    ("mcp", {"mcp_server_name": "atlassian", "tool_name": "searchJiraIssuesUsingJql"}, True),
    ("mcp", {"mcp_server_name": "atlassian", "tool_name": "createJiraIssue"}, False),
    ("mcp", {"mcp_server_name": "atlassian", "tool_name": "addCommentToJiraIssue"}, False),
    ("mcp", {"mcp_server_name": "other", "tool_name": "getThing"}, False), ("mcp", {"tool_name": "getJiraIssue"}, False),
    ("read", {"file_path": ".env"}, False), ("read", {"file_path": "src/index.ts"}, True),
    ("tool", {"tool_name": "Read", "tool_input": {"path": "id_rsa"}}, False),
    ("tool", {"tool_name": "Write", "tool_input": {"path": ".cursor/hooks.json"}}, False),
    ("tool", {"tool_name": "Write", "tool_input": {"path": "AGENTS.md"}}, False),
    ("tool", {"tool_name": "WebFetch", "tool_input": {"url": "https://evil.example/x"}}, False),
]


def selftest(root):
    """Run the static policy table. Returns list of failure strings (empty = all good).
    Cases are evaluated as if NO task were active, so they test hard guardrails only."""
    pol = L.load_policy(root)
    fails = []
    for mode, payload, want in SELFTEST:
        ctx = Ctx(root, pol, str(root))
        ctx.active, ctx.tampered = None, False
        if mode == "mcp":  # do not pollute counters
            orig = L.bump_counter
            L.bump_counter = lambda *a, **k: 0
        try:
            out = HANDLERS[mode](payload, ctx)
        finally:
            if mode == "mcp":
                L.bump_counter = orig
        got = out.get("permission") == "allow"
        if got != want:
            fails.append(f"{mode} {json.dumps(payload)[:90]} → expected {'allow' if want else 'deny'}, got {'allow' if got else 'deny'}")
    return fails


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if os.environ.get("HELM_PROBE"):  # record payload SHAPE (keys only) to learn the real schema
        try:
            root = L.find_root(os.environ.get("CURSOR_PROJECT_DIR"))
            def shape(o):
                return {k: shape(v) for k, v in o.items()} if isinstance(o, dict) else type(o).__name__
            L.audit(root, "_probe", {"k": "probe", "mode": mode, "shape": shape(payload)})
        except Exception:
            pass
    sys.stdout.write(json.dumps(run(mode, payload)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

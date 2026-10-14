#!/usr/bin/env python3
"""HELM shared library (stdlib only).

Design rules
  * Workflow state is DERIVED from signed human decisions + artifact hashes, never stored as a
    mutable "current phase" the agent could flip.
  * Everything the agent must not forge (approvals, active task, verification results) lives in
    HELM_HOME (outside the workspace) or is HMAC-signed with a key in HELM_HOME.
  * Same-OS-user caveat: this is defence in depth, not a sandbox. See docs/THREAT-MODEL.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import time
from pathlib import Path

FRAMEWORK_VERSION = "1.0.0"
WORK_REL = ".helm/work"
BOOT_REL = ".helm/bootstrap/proposal"
OVERLAY_REL = ".helm/repo"
ARTIFACT_FILES = ["WORK.md", "PLAN.md", "TEST-PLAN.md", "IMPL.md", "REVIEW.md", "BLOCKED.md", "DIFF-DIGEST.md"]
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
VERIFY_ERROR_RE = re.compile(
    r"(?:\bFAIL(?:ED|URE)?\b|\bERROR\b|Traceback \(most recent call last\):|"
    r"\b(?:AssertionError|Exception|RuntimeError|ValueError|TypeError|KeyError|SyntaxError|ImportError)\b|"
    r"^E\s+|File \".+\", line \d+|\berror(?:\[E\d+\]|\s+TS\d+|:)|\bpanic:|✘|×)",
    re.MULTILINE,
)

ROLE_STEERING = {
    "discovery": {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "concise"},
    "planner": {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "detailed"},
    "test-analyst": {"model": "claude-haiku-5-5", "reasoning_effort": "medium", "verbosity": "concise"},
    "implementer": {"model": "claude-haiku-5-5", "reasoning_effort": "medium", "verbosity": "concise"},
    "reviewer": {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "thorough"},
    "specialist-reviewer": {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "thorough"},
    "bootstrapper": {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "detailed"},
}


def get_role_steering(role_name: str, pol: dict | None = None) -> dict[str, str]:
    pol = pol or {}
    pol_steering = (pol.get("steering") or {}).get(role_name, {})
    default = ROLE_STEERING.get(role_name, {"model": "claude-opus-5-5", "reasoning_effort": "medium", "verbosity": "concise"})
    return {
        "model": pol_steering.get("model", default.get("model", "claude-opus-5-5")),
        "reasoning_effort": pol_steering.get("reasoning_effort", default.get("reasoning_effort", "medium")),
        "verbosity": pol_steering.get("verbosity", default.get("verbosity", "concise")),
    }


def estimate_tokens_from_bytes(n: int) -> int:
    return (max(0, int(n)) + 3) // 4


def compress_verify_log(
    raw: str,
    raw_log_rel: str,
    max_lines: int = 120,
    head: int = 15,
    tail: int = 25,
    before: int = 3,
    after: int = 8,
) -> dict:
    raw_str = raw or ""
    raw_bytes = len(raw_str.encode("utf-8", "replace"))
    raw_tokens = estimate_tokens_from_bytes(raw_bytes)

    raw_lines_list: list[str] = []
    split_lines = raw_str.split("\n")
    if split_lines and split_lines[-1] == "":
        split_lines.pop()
    for line in split_lines:
        if line.endswith("\r"):
            line = line[:-1]
        if "\r" in line:
            parts = [p for p in line.split("\r") if p]
            line = parts[-1] if parts else ""
        raw_lines_list.append(ANSI_ESCAPE_RE.sub("", line))

    raw_line_count = len(raw_lines_list)
    if raw_line_count == 0:
        return {
            "text": "",
            "raw_lines": 0,
            "compressed_lines": 0,
            "raw_tokens": 0,
            "compressed_tokens": 0,
            "saved_tokens": 0,
            "raw_log": raw_log_rel,
        }

    collapsed: list[tuple[int, int, str, bool]] = []
    i = 0
    while i < raw_line_count:
        line_text = raw_lines_list[i]
        start_line = i + 1
        j = i + 1
        while j < raw_line_count and raw_lines_list[j] == line_text:
            j += 1
        run_len = j - i
        collapsed.append((start_line, start_line, line_text, False))
        if run_len > 1:
            collapse_note = f"... [collapsed {run_len - 1} identical lines] ..."
            collapsed.append((start_line + 1, j, collapse_note, True))
        i = j

    total_collapsed = len(collapsed)
    if total_collapsed <= max_lines:
        keep_indices = set(range(total_collapsed))
    else:
        keep_indices = set()
        for idx in range(min(head, total_collapsed)):
            keep_indices.add(idx)
        for idx in range(max(0, total_collapsed - tail), total_collapsed):
            keep_indices.add(idx)
        error_indices = []
        for idx, (_, _, text, _) in enumerate(collapsed):
            if VERIFY_ERROR_RE.search(text):
                for k in range(max(0, idx - before), min(total_collapsed, idx + after + 1)):
                    error_indices.append(k)

        avail_for_errors = max(0, max_lines - len(keep_indices))
        unique_error_indices = sorted(set(error_indices) - keep_indices)
        for idx in unique_error_indices[:avail_for_errors]:
            keep_indices.add(idx)

    result_lines: list[str] = []
    idx = 0
    while idx < total_collapsed:
        if idx in keep_indices:
            result_lines.append(collapsed[idx][2])
            idx += 1
        else:
            gap_start = idx
            while idx < total_collapsed and idx not in keep_indices:
                idx += 1
            gap_end = idx - 1
            orig_start = collapsed[gap_start][0]
            orig_end = collapsed[gap_end][1]
            omitted_count = orig_end - orig_start + 1
            result_lines.append(
                f"[... CCR: omitted {omitted_count} low-signal lines -> {raw_log_rel}#L{orig_start}-L{orig_end} ...]"
            )

    temp_text = "\n".join(result_lines)
    temp_bytes = len(temp_text.encode("utf-8", "replace"))
    pre_saved = max(0, raw_tokens - estimate_tokens_from_bytes(temp_bytes))
    footer = f"[CCR: Compressed {raw_line_count} -> {len(result_lines) + 1} lines (~{pre_saved} tokens saved). Full log: {raw_log_rel}]"
    result_lines.append(footer)

    final_text = "\n".join(result_lines) + "\n"
    final_bytes = len(final_text.encode("utf-8", "replace"))
    compressed_tokens = estimate_tokens_from_bytes(final_bytes)
    saved_tokens = max(0, raw_tokens - compressed_tokens)

    if saved_tokens != pre_saved:
        result_lines[-1] = f"[CCR: Compressed {raw_line_count} -> {len(result_lines)} lines (~{saved_tokens} tokens saved). Full log: {raw_log_rel}]"
        final_text = "\n".join(result_lines) + "\n"
        final_bytes = len(final_text.encode("utf-8", "replace"))
        compressed_tokens = estimate_tokens_from_bytes(final_bytes)
        saved_tokens = max(0, raw_tokens - compressed_tokens)

    return {
        "text": final_text,
        "raw_lines": raw_line_count,
        "compressed_lines": len(result_lines),
        "raw_tokens": raw_tokens,
        "compressed_tokens": compressed_tokens,
        "saved_tokens": saved_tokens,
        "raw_log": raw_log_rel,
    }


def store_ccr_log(wd: Path, check_name: str, raw_output: str, root: Path | None = None) -> dict:
    vdir = wd / "verify"
    vdir.mkdir(parents=True, exist_ok=True)
    raw_path = vdir / f"{check_name}.raw.log"
    log_path = vdir / f"{check_name}.log"
    raw_path.write_text(raw_output or "", encoding="utf-8")
    raw_log_rel = f"verify/{check_name}.raw.log"
    res = compress_verify_log(raw_output or "", raw_log_rel)
    log_path.write_text(res["text"], encoding="utf-8")
    return res


# --------------------------------------------------------------------------- basics
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def dump_json(p, obj) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def helm_home() -> Path:
    return Path(os.environ.get("HELM_HOME") or (Path.home() / ".helm")).expanduser()


hcaf_home = helm_home


def git_run(root, args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, env=env, timeout=120)
    except Exception:
        return 1, b""
    return r.returncode, r.stdout


def git_out(root, args) -> str:
    rc, out = git_run(root, args)
    return out.decode("utf-8", "replace").strip() if rc == 0 else ""


def find_root(start=None) -> Path:
    s = Path(start or os.environ.get("CURSOR_PROJECT_DIR") or os.getcwd()).resolve()
    if s.is_file():
        s = s.parent
    top = git_out(s, ["rev-parse", "--show-toplevel"]) if s.exists() else ""
    return Path(top).resolve() if top else s


def repo_id(root) -> str:
    return sha256_bytes(str(Path(root).resolve()).encode())[:12]


def state_dir(root) -> Path:
    return helm_home() / "state" / repo_id(root)


# --------------------------------------------------------------------------- signing
def key_path() -> Path:
    return helm_home() / "key"


def ensure_key() -> Path:
    p = key_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(p.parent, 0o700)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, os.urandom(32).hex().encode())
        os.close(fd)
    return p


def _key():
    try:
        return key_path().read_bytes().strip() or None
    except OSError:
        return None


def sign(obj: dict) -> str:
    k = _key()
    if not k:
        return ""
    body = json.dumps({a: b for a, b in obj.items() if a != "hmac"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(k, body.encode(), hashlib.sha256).hexdigest()


def verify_sig(obj: dict) -> bool:
    s = obj.get("hmac", "")
    exp = sign(obj)
    return bool(s) and bool(exp) and hmac.compare_digest(s, exp)


def signed(obj: dict) -> dict:
    o = dict(obj)
    o.pop("hmac", None)
    o["hmac"] = sign(o)
    return o


# --------------------------------------------------------------------------- policy
class PolicyError(Exception):
    pass


def merge_policy(a, b, lists_only=False):
    """Dicts merge recursively, lists union, scalars: b wins (unless lists_only -> a wins)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = merge_policy(out[k], v, lists_only) if k in out else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + [x for x in b if x not in a]
    return a if lists_only else b


OVERLAY_ALLOWED = {
    "protected_paths", "secret_globs", "test_globs", "staleness_watch",
    "shell", "mcp", "web",
}
OVERLAY_ALLOWED_NESTED = {"shell": {"deny_commands"}, "mcp": {"allow_servers"}, "web": {"fetch_domains"}}


def sanitize_overlay(loc: dict) -> dict:
    out = {}
    for k, v in (loc or {}).items():
        if k not in OVERLAY_ALLOWED:
            continue
        if k in OVERLAY_ALLOWED_NESTED and isinstance(v, dict):
            v = {kk: vv for kk, vv in v.items() if kk in OVERLAY_ALLOWED_NESTED[k] and isinstance(vv, list)}
        elif not isinstance(v, list):
            continue
        out[k] = v
    return out


def load_policy(root) -> dict:
    root = Path(root)
    core = load_json(root / ".helm/policy/policy.json")
    if not isinstance(core, dict):
        raise PolicyError("missing or invalid .helm/policy/policy.json")
    pol = core
    sysp = Path(os.environ.get("HELM_SYSTEM_POLICY", "/etc/helm/policy.json"))
    sys_pol = load_json(sysp)
    if isinstance(sys_pol, dict):
        pol = merge_policy(pol, sys_pol)
    loc = load_json(root / OVERLAY_REL / "policy.local.json")
    if isinstance(loc, dict):
        pol = merge_policy(pol, sanitize_overlay(loc), lists_only=True)
    return pol


# --------------------------------------------------------------------------- globs & paths
def glob_re(pat: str):
    i, out = 0, ""
    while i < len(pat):
        c = pat[i]
        if c == "*":
            if pat[i:i + 3] == "**/":
                out += "(?:.*/)?"
                i += 3
                continue
            if pat[i:i + 2] == "**":
                out += ".*"
                i += 2
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$", re.IGNORECASE)


_RE: dict = {}


def gmatch(pat: str, s: str) -> bool:
    r = _RE.get(pat)
    if r is None:
        r = _RE[pat] = glob_re(pat)
    return bool(r.match(s))


def any_match(pats, s) -> bool:
    """Match s, or s as a directory (so `dir/**` also covers `dir` itself)."""
    return any(gmatch(p, s) or gmatch(p, s.rstrip("/") + "/") for p in pats)


def expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def resolve(root, p: str, cwd=None) -> Path:
    p = expand(p)
    base = Path(cwd) if cwd else Path(root)
    q = Path(p) if os.path.isabs(p) else base / p
    try:
        return q.resolve()
    except Exception:
        return Path(os.path.abspath(q))


def static_prefix(g: str) -> str:
    m = re.search(r"[*?]", g)
    return g[:m.start()] if m else g


ALLOWED_VIRTUAL_DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr"}
_RESOLVED_ALLOWED_DEVICES = {
    "/dev/null", "/dev/stdout", "/dev/stderr",
    "/dev/fd/1", "/dev/fd/2",
    "/proc/self/fd/1", "/proc/self/fd/2",
}


def is_tmp(q: Path) -> bool:
    s = q.as_posix()
    tmp = (os.environ.get("TMPDIR") or "/tmp").rstrip("/")
    resolved_tmp = Path(tmp).resolve().as_posix().rstrip("/")
    resolved_slash_tmp = Path("/tmp").resolve().as_posix().rstrip("/")
    return (s.startswith("/tmp/") or s.startswith("/private/tmp/") or
            s in _RESOLVED_ALLOWED_DEVICES or
            (bool(tmp) and s.startswith(tmp + "/")) or
            (bool(resolved_tmp) and s.startswith(resolved_tmp + "/")) or
            (bool(resolved_slash_tmp) and s.startswith(resolved_slash_tmp + "/")))


def classify(root, pol, q: Path) -> dict:
    root = Path(root)
    if str(q).startswith("~"):
        try:
            q = Path(expand(str(q))).resolve()
        except Exception:
            q = Path(expand(str(q)))
    try:
        rel = q.relative_to(root).as_posix()
    except ValueError:
        rel = None
    c = {"rel": rel, "outside": rel is None, "git": False, "state": False, "secret": False, "protected": False}
    s = q.as_posix()
    alt_s = s[8:] if s.startswith("/private/") else ("/private" + s)
    if rel is not None and (rel == ".git" or rel.startswith(".git/")):
        c["git"] = True
    try:
        home = helm_home().resolve()
        if q == home or home in q.parents:
            c["state"] = True
    except Exception:
        pass
    probe = rel if rel is not None else s
    alt_probe = rel if rel is not None else alt_s
    for pat in pol.get("secret_globs", []):
        absolute = pat.startswith(("~", "/"))
        if pat.startswith("~"):
            resolved_home = Path(expand("~")).resolve().as_posix()
            subpath = pat[1:].lstrip("/")
            ep = f"{resolved_home}/{subpath}"
        elif absolute:
            ep = expand(pat)
        else:
            ep = pat
        tgt = s if absolute else probe
        alt_tgt = alt_s if absolute else alt_probe
        if (gmatch(ep, tgt) or gmatch(ep, tgt.rstrip("/") + "/") or
            gmatch(ep, alt_tgt) or gmatch(ep, alt_tgt.rstrip("/") + "/")):
            c["secret"] = True
            break
    if c["secret"] and (any_match(pol.get("secret_allow_globs", []), probe) or any_match(pol.get("secret_allow_globs", []), alt_probe)):
        c["secret"] = False
    if rel is not None and any_match(pol.get("protected_paths", []), rel):
        c["protected"] = True
    return c


PATH_KEYS = {"path", "filepath", "targetfile", "file", "filename", "notebookpath", "targetnotebook",
             "directory", "targetdirectory", "dir", "paths", "files", "oldpath", "newpath",
             "source", "destination", "absolutepath"}
PATCH_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def extract_paths(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            kk = re.sub(r"[^a-z]", "", str(k).lower())
            if kk in PATH_KEYS and isinstance(v, str):
                out.append(v)
            elif kk in PATH_KEYS and isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            elif isinstance(v, (dict, list)):
                extract_paths(v, out)
            elif isinstance(v, str) and "*** Begin Patch" in v:
                out += PATCH_RE.findall(v)
    elif isinstance(obj, list):
        for x in obj:
            extract_paths(x, out)
    elif isinstance(obj, str) and "*** Begin Patch" in obj:
        out += PATCH_RE.findall(obj)
    return out


# --------------------------------------------------------------------------- git state
def git_snapshot(root) -> dict:
    sha = lambda s: sha256_bytes(s.encode())[:16]
    return {
        "head": git_out(root, ["rev-parse", "HEAD"]),
        "branch": git_out(root, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "refs": sha(git_out(root, ["for-each-ref", "--format=%(refname) %(objectname)"])),
        "stash": sha(git_out(root, ["stash", "list"])),
        "worktrees": sha(git_out(root, ["worktree", "list", "--porcelain"])),
        "hooks_path": git_out(root, ["config", "--get", "core.hooksPath"]),
    }


def git_violations(base: dict, cur: dict):
    return [k for k in base if base.get(k) != cur.get(k)]


def diff_sha(root, base_head: str) -> str:
    h = hashlib.sha256()
    rc, d = git_run(root, ["diff", "--binary", "--no-ext-diff", "--no-color", base_head, "--"])
    h.update(d if rc == 0 else b"diff-error")
    rc, o = git_run(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    for f in sorted(x for x in o.decode("utf-8", "replace").split("\0") if x):
        p = Path(root) / f
        try:
            hh = sha256_file(p) if p.is_file() else "dir"
        except OSError:
            hh = "unreadable"
        h.update(f"\0U {f} {hh}".encode())
    return h.hexdigest()


def changed_files(root, base_head: str):
    files = set(git_out(root, ["diff", "--name-only", base_head, "--"]).splitlines())
    files |= set(git_out(root, ["ls-files", "--others", "--exclude-standard"]).splitlines())
    return sorted(f for f in files if f)


# --------------------------------------------------------------------------- integrity
def protected_files(root, pol):
    root = Path(root)
    seen = {}
    for g in pol.get("protected_paths", []):
        pre = static_prefix(g)
        base = root / (pre if pre.endswith("/") or "/" not in pre else pre.rsplit("/", 1)[0])
        if base.is_file():
            cands = [base]
        elif base.is_dir():
            cands = []
            for dp, dn, fn in os.walk(base):
                dn[:] = [d for d in dn if d not in (".git", "node_modules", "work", "bootstrap", "__pycache__")]
                cands += [Path(dp) / f for f in fn if (Path(dp) / f).is_file()]
        else:
            continue
        for p in cands:
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if gmatch(g, rel):
                seen[rel] = None
    for rel in ("AGENTS.md",):
        if (root / rel).is_file():
            seen[rel] = None
    return sorted(seen)


def integrity_manifest(root, pol) -> dict:
    out = {}
    for rel in protected_files(root, pol):
        try:
            out[rel] = sha256_file(Path(root) / rel)
        except OSError:
            pass
    return out


def integrity_path(root) -> Path:
    return state_dir(root) / "integrity.json"


def integrity_check(root, pol):
    saved = load_json(integrity_path(root))
    if not isinstance(saved, dict) or not verify_sig(saved):
        return ["<no valid integrity manifest: run `helm integrity refresh`>"]
    cur = integrity_manifest(root, pol)
    old = saved.get("files", {})
    diffs = [f"changed: {k}" for k in cur if k in old and cur[k] != old[k]]
    diffs += [f"added: {k}" for k in cur if k not in old]
    diffs += [f"removed: {k}" for k in old if k not in cur]
    return sorted(diffs)


def integrity_refresh(root, pol):
    dump_json(integrity_path(root), signed({"files": integrity_manifest(root, pol), "ts": now()}))


# --------------------------------------------------------------------------- active task & records
def active_path(root) -> Path:
    return state_dir(root) / "active.json"


def load_active(root):
    """-> (active|None, tampered:bool)"""
    p = active_path(root)
    if not p.exists():
        return None, False
    o = load_json(p)
    if not isinstance(o, dict) or not verify_sig(o):
        return None, True
    return o, False


def set_active(root, obj: dict) -> None:
    dump_json(active_path(root), signed(obj))


def clear_active(root) -> None:
    active_path(root).unlink(missing_ok=True)


def task_dir(root, task) -> Path:
    return state_dir(root) / "tasks" / task


def load_task(root, task):
    o = load_json(task_dir(root, task) / "task.json")
    return o if isinstance(o, dict) and verify_sig(o) else None


def save_task(root, task, obj: dict) -> None:
    dump_json(task_dir(root, task) / "task.json", signed(obj))


def append_record(root, task, rec: dict) -> dict:
    rec = dict(rec)
    rec.setdefault("ts", now())
    rec["task"] = task
    rec["hmac"] = sign(rec)
    p = task_dir(root, task) / "records.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def load_records(root, task, all_runs: bool = False):
    p = task_dir(root, task) / "records.jsonl"
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if verify_sig(r):
            out.append(r)
    if not all_runs:
        for idx in range(len(out) - 1, -1, -1):
            if out[idx].get("gate") == "task" and out[idx].get("decision") == "start":
                out = out[idx:]
                break
    return out


def audit(root, task, rec: dict) -> None:
    try:
        p = state_dir(root) / "audit" / f"{task or '_none'}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 20 * 1024 * 1024:
            return
        rec = dict(rec, ts=now())
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def bump_counter(root, task, name: str) -> int:
    p = task_dir(root, task or "_none") / "counters.json"
    c = load_json(p, {}) or {}
    c[name] = int(c.get(name, 0)) + 1
    dump_json(p, c)
    return c[name]


# --------------------------------------------------------------------------- artifacts
SPECS = {
    "WORK": {"file": "WORK.md", "max_lines": 160, "headings": [
        "Objective", "Acceptance Criteria", "Scope", "Relevant Files", "Existing Patterns",
        "Component Library", "Testing", "External Knowledge", "Decisions", "Assumptions", "Open Questions"]},
    "PLAN": {"file": "PLAN.md", "max_lines": 120, "headings": [
        "Objective", "Approach", "Affected Areas", "Files Likely To Change", "Testing Strategy",
        "Risks", "Alternatives Considered", "Open Questions", "Required Skills"]},
    "TEST-PLAN": {"file": "TEST-PLAN.md", "max_lines": 100, "headings": [
        "Behaviours", "Fixtures And Utilities", "Test Cases", "Gaps"]},
    "IMPL": {"file": "IMPL.md", "max_lines": 60, "headings": [
        "Summary", "Deviations From Plan", "Verification Notes"]},
    "REVIEW": {"file": "REVIEW.md", "max_lines": 150, "headings": [
        "Verdict", "Findings", "Traceability", "Scope", "Residual Risk"]},
}


def read_meta(path):
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    meta, body = {}, txt
    if txt.startswith("---\n"):
        end = txt.find("\n---", 4)
        if end != -1:
            for line in txt[4:end].splitlines():
                if ":" in line and not line.lstrip().startswith("#"):
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            body = txt[end + 4:]
    return meta, body


def section(body: str, heading: str) -> str:
    m = re.search(rf"^#{{2,3}}\s+{re.escape(heading)}\s*$", body, re.I | re.M)
    if not m:
        return ""
    rest = body[m.end():]
    n = re.search(r"^#{2,3}\s+\S", rest, re.M)
    return (rest[:n.start()] if n else rest).strip()


HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
INVISIBLE_UNICODE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
ARTIFACT_INJECTION_RE = re.compile(
    r"(?i)ignore (all |any )?(previous|prior) instructions|"
    r"</?(system|system_instruction|user_message|assistant)\b|"
    r"<!--\s*HELM:(BEGIN|END)"
)


def template_comments(root: Path, filename: str) -> set[str]:
    """Return the exact stock HTML comments present in .helm/templates/<filename>."""
    for cand in (Path(root) / ".helm/templates" / filename, Path(__file__).resolve().parent.parent / "templates" / filename):
        if cand.is_file():
            try:
                return {m.strip() for m in HTML_COMMENT_RE.findall(cand.read_text(encoding="utf-8", errors="replace"))}
            except OSError:
                pass
    return set()


def validate(wd: Path, name: str, tier: int = 2, root=None):
    spec = SPECS[name]
    root = Path(root) if root else Path(wd).resolve().parents[2]
    p = Path(wd) / spec["file"]
    if not p.exists():
        return [f"{spec['file']} does not exist"]
    meta, body = read_meta(p)
    probs = []
    if meta.get("status") not in ("draft", "ready"):
        probs.append("front matter `status` must be draft|ready")
    heads = list(spec["headings"]) + (["Plan"] if name == "WORK" and tier == 1 else [])
    for h in heads:
        if not re.search(rf"^#{{2,3}}\s+{re.escape(h)}\s*$", body, re.I | re.M):
            probs.append(f"missing section: ## {h}")
    nlines = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    if nlines > spec["max_lines"]:
        probs.append(f"too long: {nlines} lines (max {spec['max_lines']}) — compress, use references")
    if meta.get("status") == "ready":
        if "{{" in body:
            probs.append("unfilled template placeholder `{{...}}` remains")
        allowed_comments = template_comments(root, spec["file"])
        extra_comments = [m.strip() for m in HTML_COMMENT_RE.findall(body) if m.strip() not in allowed_comments]
        if extra_comments:
            probs.append("unexpected HTML comment `<!-- ... -->` in ready artifact (hidden prompt-injection risk)")
        if INVISIBLE_UNICODE_RE.search(body):
            probs.append("invisible/bidirectional Unicode control characters detected in artifact (obfuscation risk)")
        if ARTIFACT_INJECTION_RE.search(body):
            probs.append("prompt-injection override phrase or fake instruction boundary tag detected in artifact")
        if name == "IMPL":
            allow_empty = str(meta.get("allow_empty_diff", "")).lower() in ("true", "1")
            if not allow_empty:
                trec = load_task(root, wd.name)
                if trec and "baseline" in trec:
                    base_head = trec["baseline"]["head"]
                    mod_files = set(changed_files(root, base_head))
                    framework_prefixes = (".helm/", ".cursor/", ".agents/", ".claude/", ".codex/", "AGENTS.md", f"{WORK_REL}/")
                    repo_src_changes = [f for f in mod_files if not any(f.startswith(pfx) or f == pfx for pfx in framework_prefixes)]
                    if not repo_src_changes:
                        probs.append(
                            "IMPL cannot be marked ready: 0 repository source files were modified relative to task baseline. "
                            "Agents must write changes to the working tree for developer review (or set allow_empty_diff: true in front matter if verification-only)."
                        )
        if name == "WORK" and not section(body, "Acceptance Criteria"):
            probs.append("Acceptance Criteria is empty")
        if name == "REVIEW":
            if meta.get("verdict") not in ("APPROVE", "CHANGES_REQUIRED", "BLOCKED"):
                probs.append("REVIEW front matter `verdict` must be APPROVE|CHANGES_REQUIRED|BLOCKED")
            if not meta.get("diff_sha"):
                probs.append("REVIEW front matter `diff_sha` is required (from `helm status --json`)")
            allow_empty = str(meta.get("allow_empty_diff", "")).lower() in ("true", "1")
            if not allow_empty:
                impl_p = wd / "IMPL.md"
                if impl_p.exists():
                    imeta, _ = read_meta(impl_p)
                    allow_empty = str(imeta.get("allow_empty_diff", "")).lower() in ("true", "1")
            if meta.get("verdict") == "APPROVE" and not allow_empty:
                trec = load_task(root, wd.name)
                if trec and "baseline" in trec:
                    base_head = trec["baseline"]["head"]
                    mod_files = set(changed_files(root, base_head))
                    framework_prefixes = (".helm/", ".cursor/", ".agents/", ".claude/", ".codex/", "AGENTS.md", f"{WORK_REL}/")
                    repo_src_changes = [f for f in mod_files if not any(f.startswith(pfx) or f == pfx for pfx in framework_prefixes)]
                    if not repo_src_changes:
                        probs.append(
                            "verdict cannot be APPROVE when 0 repository source files were modified relative to task baseline. "
                            "Use CHANGES_REQUIRED or BLOCKED (agents cannot approve tasks without working tree changes)."
                        )
            tr = traceability(root, wd)
            probs += tr["problems"]
            bad = tr["counts"]["fail"] + tr["counts"]["unproven"]
            if meta.get("verdict") == "APPROVE" and bad:
                probs.append(f"verdict APPROVE but {bad} acceptance criteria are fail/unproven — use CHANGES_REQUIRED (or BLOCKED)")
    return probs


def ac_items(work_body: str):
    """Acceptance criteria as an ordered list (numbered/bulleted lines; else each non-empty line)."""
    sec = section(work_body, "Acceptance Criteria")
    lines = [re.sub(r"^\s*>\s?", "", l).strip() for l in sec.splitlines()]
    lines = [l for l in lines if l and not l.startswith("<!--")]
    items = [m.group(1) for l in lines for m in [re.match(r"^(?:\d+[.)]|[-*])\s+(.*)$", l)] if m]
    return items or lines


def traceability(root, wd) -> dict:
    """Parse REVIEW.md's `## Traceability` table (AC | Implementation | Test | Result) against WORK.md."""
    root, wd = Path(root), Path(wd)
    n = len(ac_items(read_meta(wd / "WORK.md")[1]))
    rmeta, rbody = read_meta(wd / "REVIEW.md")
    rows, probs = {}, []
    counts = {"pass": 0, "manual": 0, "fail": 0, "unproven": 0}
    for line in section(rbody, "Traceability").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or re.fullmatch(r"[-: ]+", cells[0]):
            continue
        m = re.search(r"\d+", cells[0])
        if m:
            rows.setdefault(int(m.group(0)), []).append(cells)
    for i in range(1, n + 1):
        if i not in rows:
            probs.append(f"Traceability: acceptance criterion {i} has no row")
    for i, rs in sorted(rows.items()):
        if not 1 <= i <= n:
            probs.append(f"Traceability: row {i} matches none of the {n} acceptance criteria")
        for cells in rs:
            res, test = cells[3].lower().strip("`* "), cells[2]
            if res == "pass":
                if test.lower().startswith("manual:"):
                    counts["manual"] += 1
                else:
                    mm = re.search(r"`([^`]+)`", test)
                    p = mm.group(1).split("#")[0] if mm else ""
                    if p and (root / p).exists():
                        counts["pass"] += 1
                    else:
                        counts["unproven"] += 1
                        probs.append(f"Traceability: criterion {i} claims pass but cites no existing test file ({p or 'none cited'}); use `path` or `manual: reason`")
            elif res == "fail":
                counts["fail"] += 1
            elif res == "unproven":
                counts["unproven"] += 1
            else:
                probs.append(f"Traceability: criterion {i} result must be pass|fail|unproven (got '{cells[3]}')")
    return {"criteria": n, "counts": counts, "problems": probs, "verdict": rmeta.get("verdict")}


def decision_candidates(root, task):
    """Human decisions made during a task: tagged [human] bullets in WORK.md + unblock notes."""
    root = Path(root)
    wd = root / WORK_REL / task
    out = []
    if (wd / "WORK.md").exists():
        raw_sec = HTML_COMMENT_RE.sub("", section(read_meta(wd / "WORK.md")[1], "Decisions"))
        for l in raw_sec.splitlines():
            l = re.sub(r"  +", " ", INVISIBLE_UNICODE_RE.sub("", l)).strip()
            if l[:1] in "-*" and "[human]" in l and not ARTIFACT_INJECTION_RE.search(l):
                out.append(re.sub(r"^[-*]\s*", "", l))
    for r in load_records(root, task):
        if r.get("gate") == "block" and r.get("decision") == "resolve" and r.get("note"):
            note = re.sub(r"  +", " ", INVISIBLE_UNICODE_RE.sub("", HTML_COMMENT_RE.sub("", str(r["note"])))).strip()
            if note and not ARTIFACT_INJECTION_RE.search(note):
                out.append(f"[human] {note}")
    return list(dict.fromkeys(out))


def promote_decisions(root, pol, task, items):
    """Append chosen decisions to the repo's decision log. Returns the log path."""
    root = Path(root)
    rel = pol.get("decisions_log", "docs/decisions.md")
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8") if p.exists() else \
        "# Decisions\n\nHuman decisions promoted from HELM tasks. Append-only; humans edit this file.\n\n"
    nums = [int(x) for x in re.findall(r"DEC-(\d+)", existing)]
    n = max(nums, default=0)
    with open(p, "w", encoding="utf-8") as f:
        f.write(existing.rstrip("\n") + "\n")
        for it in items:
            n += 1
            clean_it = INVISIBLE_UNICODE_RE.sub("", HTML_COMMENT_RE.sub("", it)).replace("\n", " ")
            text = re.sub(r"\s*\[human\]\s*", " ", clean_it).strip()
            f.write(f"- **DEC-{n:03d}** ({time.strftime('%Y-%m-%d')}, {task}): {text}\n")
    return rel


def art_sha(wd: Path, name: str):
    p = Path(wd) / SPECS[name]["file"] if name in SPECS else Path(wd) / name
    return sha256_file(p) if p.exists() else None


def verify_record(wd: Path):
    o = load_json(Path(wd) / "VERIFY.json")
    return o if isinstance(o, dict) and verify_sig(o) else None


def tier_cfg(pol, tier):
    cfg = {"plan_stage": True, "test_analysis": True, "review_required": True}
    cfg.update((pol.get("tiers") or {}).get(str(tier), {}))
    return cfg


def gate_inputs(wd: Path, gate: str, diff=None):
    if gate == "discovery":
        return {"WORK": art_sha(wd, "WORK")}
    if gate == "plan":
        return {"WORK": art_sha(wd, "WORK"), "PLAN": art_sha(wd, "PLAN")}
    if gate == "final":
        return {"DIFF": diff, "REVIEW": art_sha(wd, "REVIEW") or "none"}
    raise ValueError(gate)


def latest(decs, gate, inputs):
    for d in reversed(decs):
        if d.get("gate") == gate and d.get("decision") in ("approve", "reject") and d.get("inputs") == inputs:
            return d
    return None


def _count(decs, gate, dec):
    return sum(1 for d in decs if d.get("gate") == gate and d.get("decision") == dec)


def derive(root, pol, active) -> dict:
    """Derive the workflow phase from signed records + artifacts. Pure function of disk state."""
    root = Path(root)
    task, tier = active["task"], int(active.get("tier", 2))
    wd = root / WORK_REL / task
    out = {"task": task, "tier": tier, "work_dir": f"{WORK_REL}/{task}", "phase": "", "diff_sha": None}
    trec = load_task(root, task)
    if not trec:
        out["phase"] = "STATE_TAMPERED"
        return out
    base = trec["baseline"]["head"]
    out["base"] = base
    decs = load_records(root, task)
    for idx in range(len(decs) - 1, -1, -1):
        if decs[idx].get("gate") == "task" and decs[idx].get("decision") == "start":
            decs = decs[idx + 1:]
            break
    cfg = tier_cfg(pol, tier)

    if _count(decs, "task", "abort"):
        out["phase"] = "ABORTED"
        return out
    if _count(decs, "task", "finish"):
        out["phase"] = "FINISHED"
        return out
    if _count(decs, "violation", "raise") > _count(decs, "violation", "ack"):
        out["phase"] = "POLICY_BLOCK"
        return out
    if _count(decs, "block", "raise") > _count(decs, "block", "resolve") or (wd / "BLOCKED.md").exists():
        out["phase"] = "BLOCKED"
        return out

    W = wd / "WORK.md"
    if not W.exists() or read_meta(W)[0].get("status") != "ready":
        out["phase"] = "DISCOVERY"
        return out
    d = latest(decs, "discovery", gate_inputs(wd, "discovery"))
    if d is None:
        out["phase"] = "AWAITING_DISCOVERY_APPROVAL"
        return out
    if d["decision"] == "reject":
        out["phase"] = "DISCOVERY"
        return out

    if cfg["plan_stage"]:
        P = wd / "PLAN.md"
        if not P.exists() or read_meta(P)[0].get("status") != "ready":
            out["phase"] = "PLANNING"
            return out
        d = latest(decs, "plan", gate_inputs(wd, "plan"))
        if d is None:
            out["phase"] = "AWAITING_PLAN_APPROVAL"
            return out
        if d["decision"] == "reject":
            out["phase"] = "PLANNING"
            return out
    if cfg["test_analysis"]:
        T = wd / "TEST-PLAN.md"
        if not T.exists() or read_meta(T)[0].get("status") != "ready":
            out["phase"] = "TEST_ANALYSIS"
            return out
    I = wd / "IMPL.md"
    if not I.exists() or read_meta(I)[0].get("status") != "ready":
        out["phase"] = "IMPLEMENTATION"
        return out

    diff = diff_sha(root, base)
    out["diff_sha"] = diff
    V = verify_record(wd)
    if not V or V.get("diff_sha") != diff or not V.get("passed"):
        out["phase"] = "VERIFICATION"
        return out
    R = wd / "REVIEW.md"
    rmeta = read_meta(R)[0] if R.exists() else {}
    review_ok = R.exists() and rmeta.get("status") == "ready" and rmeta.get("diff_sha") == diff
    if cfg["review_required"] and not review_ok:
        out["phase"] = "REVIEW"
        return out
    inputs = final_inputs(wd, diff)
    d = latest(decs, "final", inputs)
    if d is None:
        out["phase"] = "AWAITING_FINAL_APPROVAL"
        return out
    out["phase"] = "IMPLEMENTATION" if d["decision"] == "reject" else "READY_FOR_DEVELOPER"
    return out


def final_inputs(wd: Path, diff: str) -> dict:
    """Inputs bound by the final gate (a stale/missing review counts as 'none')."""
    R = Path(wd) / "REVIEW.md"
    rmeta = read_meta(R)[0] if R.exists() else {}
    ok = R.exists() and rmeta.get("status") == "ready" and rmeta.get("diff_sha") == diff
    return {"DIFF": diff, "REVIEW": art_sha(wd, "REVIEW") if ok else "none"}


def write_scope(root, pol, info: dict) -> dict:
    """What may the agent write right now? {'files': [...], 'globs': [...], 'source': bool}"""
    ph, wd = info["phase"], info["work_dir"]
    files, globs, source = [], [], False
    if ph == "DISCOVERY":
        files = [f"{wd}/WORK.md"]
    elif ph == "PLANNING":
        files = [f"{wd}/PLAN.md"]
    elif ph == "TEST_ANALYSIS":
        files = [f"{wd}/TEST-PLAN.md"]
        meta = read_meta(Path(root) / wd / "PLAN.md")[0]
        if meta.get("test_first", "").lower() == "true":
            globs += list(pol.get("test_globs", []))
    elif ph in ("IMPLEMENTATION", "VERIFICATION"):
        source, files = True, [f"{wd}/IMPL.md"]
    elif ph == "REVIEW" or (ph == "AWAITING_FINAL_APPROVAL" and not tier_cfg(pol, info["tier"])["review_required"]):
        # (tier without a mandatory review may still run an OPTIONAL review before the final gate)
        globs = [f"{wd}/REVIEW.md", f"{wd}/REVIEW-*.md"]
    if ph not in ("ABORTED", "FINISHED", "STATE_TAMPERED", "POLICY_BLOCK"):
        files.append(f"{wd}/BLOCKED.md")
    return {"files": files, "globs": globs, "source": source}


def check_write(root, pol, rel_or_path, active, tampered, info=None, is_delete=False):
    """Decide whether the agent may write/delete a path. -> (allowed, reason)"""
    root = Path(root)
    q = rel_or_path if isinstance(rel_or_path, Path) else resolve(root, rel_or_path)
    c = classify(root, pol, q)
    if c["git"]:
        return False, "writing inside .git is not allowed (Git belongs to the developer)"
    if c["state"]:
        return False, "HELM state/key directory is off limits"
    if c["secret"]:
        return False, "path matches a secret-file pattern"
    if c["outside"]:
        return (True, "") if is_tmp(q) else (False, "path is outside the repository")
    rel = c["rel"]
    if rel.endswith("/DIFF-DIGEST.md") or rel == "DIFF-DIGEST.md":
        return False, "DIFF-DIGEST.md is generated by HELM and read-only for agents"
    if c["protected"]:
        return False, "protected framework/config path — the human edits these directly"
    if tampered:
        return False, "HELM active-task state failed signature check (STATE_TAMPERED); ask the human to run `helm doctor`"
    if active is None:
        if rel.startswith(WORK_REL + "/") or rel.startswith(".helm/bootstrap/"):
            return False, "no active HELM task/bootstrap; the human must run `helm start` / `helm bootstrap start`"
        if pol.get("require_task_for_source_writes"):
            return False, "policy requires an active HELM task for repository writes (`helm start <ID>`)"
        return True, ""
    if active.get("kind") == "bootstrap":
        ok = rel.startswith(BOOT_REL + "/")
        return ok, "" if ok else f"bootstrap mode: only {BOOT_REL}/ is writable"
    if info is None:
        return False, "no phase information"
    sc = write_scope(root, pol, info)
    wd = info["work_dir"]
    if is_delete:
        if rel.endswith("/BLOCKED.md"):
            return False, "only the human can resolve BLOCKED (`helm unblock`)"
        return False, "file deletion by AI agents is prohibited without explicit human verification"
    if rel in sc["files"] or any_match(sc["globs"], rel):
        return True, ""
    if rel.startswith(WORK_REL + "/"):
        return False, f"phase {info['phase']}: this work artifact is not writable now (allowed: {', '.join(sc['files']) or 'none'})"
    if sc["source"]:
        return True, ""
    return False, f"phase {info['phase']}: repository writes are not allowed in this phase"


# --------------------------------------------------------------------------- metrics & waste signals
def section_paths(text: str) -> set[str]:
    found = set(re.findall(r"`([^`\s]+)`", text or ""))
    found |= set(re.findall(r"^[-*]\s+([^\s`]+/[^\s`]*|[^\s`]+\.[A-Za-z0-9]+)\s*$", text or "", re.M))
    return {f.rstrip("/") for f in found if f}


def is_planned(f: str, planned: set[str]) -> bool:
    return any(f == p or f.startswith(p + "/") for p in planned)


def compute_task_metrics(root: Path, task: str, pol: dict | None = None) -> dict:
    root = Path(root)
    audit_file = state_dir(root) / "audit" / f"{task}.jsonl"
    ev = []
    if audit_file.exists():
        for line in audit_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev.append(json.loads(line))
            except ValueError:
                continue

    wd = root / WORK_REL / task
    planned_paths = set()
    if (wd / "WORK.md").exists():
        try:
            _, wbody = read_meta(wd / "WORK.md")
            planned_paths |= section_paths(section(wbody, "Relevant Files"))
            planned_paths |= section_paths(section(wbody, "Scope"))
        except Exception:
            pass
    if (wd / "PLAN.md").exists():
        try:
            _, pbody = read_meta(wd / "PLAN.md")
            planned_paths |= section_paths(section(pbody, "Files Likely To Change"))
            planned_paths |= section_paths(section(pbody, "Plan"))
        except Exception:
            pass

    read_events = [e for e in ev if e.get("k") == "read"]
    reads_by_path: dict[str, int] = {}
    bytes_by_path: dict[str, int] = {}

    in_scope_reads = 0
    in_scope_tokens = 0
    out_of_scope_reads = 0
    out_of_scope_tokens = 0
    framework_reads = 0
    framework_tokens = 0

    for e in read_events:
        p = e.get("p") or ""
        reads_by_path[p] = reads_by_path.get(p, 0) + 1
        b = e.get("bytes")
        if b is None or b == 0:
            try:
                b = (root / p).stat().st_size
            except OSError:
                b = 0
        b_int = int(b) if b is not None else 0
        bytes_by_path[p] = max(bytes_by_path.get(p, 0), b_int)
        tok = estimate_tokens_from_bytes(b_int)

        is_framework = p.startswith((".helm/", ".cursor/", ".agents/", ".claude/", ".codex/")) or p == "AGENTS.md" or p.startswith(f"{WORK_REL}/")
        if is_framework:
            framework_reads += 1
            framework_tokens += tok
        elif is_planned(p, planned_paths):
            in_scope_reads += 1
            in_scope_tokens += tok
        else:
            out_of_scope_reads += 1
            out_of_scope_tokens += tok

    total_read_tokens = in_scope_tokens + out_of_scope_tokens + framework_tokens

    task_artifacts_written_tokens = 0
    task_artifacts_count = 0
    if wd.exists():
        for p in wd.rglob("*"):
            if p.is_file():
                task_artifacts_count += 1
                try:
                    task_artifacts_written_tokens += estimate_tokens_from_bytes(p.stat().st_size)
                except OSError:
                    pass

    dup_files = []
    wasted_reads_total = 0
    wasted_tokens_total = 0
    for p, cnt in sorted(reads_by_path.items(), key=lambda x: -x[1]):
        if cnt > 1:
            wasted_r = cnt - 1
            file_tok = estimate_tokens_from_bytes(bytes_by_path.get(p, 0))
            wasted_t = wasted_r * file_tok
            wasted_reads_total += wasted_r
            wasted_tokens_total += wasted_t
            dup_files.append({"path": p, "count": cnt, "wasted_reads": wasted_r, "wasted_tokens": wasted_t})

    trec = load_task(root, task)
    base_head = trec.get("baseline", {}).get("head") if trec else "HEAD"
    modified_set = set(changed_files(root, base_head)) if base_head else set()

    unmodified_oos_files = []
    unmodified_oos_tokens = 0
    for p in sorted(reads_by_path.keys()):
        is_framework = p.startswith((".helm/", ".cursor/", ".agents/", ".claude/", ".codex/")) or p == "AGENTS.md" or p.startswith(f"{WORK_REL}/")
        if not is_framework and not is_planned(p, planned_paths):
            if p not in modified_set:
                t = estimate_tokens_from_bytes(bytes_by_path.get(p, 0))
                unmodified_oos_files.append(p)
                unmodified_oos_tokens += t

    shell_events = [e for e in ev if e.get("k") == "shell"]
    denied_shell = sum(1 for e in shell_events if not e.get("ok", True))
    shell_cmds = [e.get("cmd") or "" for e in shell_events]
    repeated_shell = max(0, len(shell_cmds) - len(set(shell_cmds)))
    writes_denied = sum(1 for e in ev if e.get("k") == "write_denied")
    violations = sum(1 for e in ev if e.get("k") == "violation")

    ccr_events = [e for e in ev if e.get("k") == "ccr"]
    ccr_raw_tokens = sum(e.get("raw_tokens", 0) for e in ccr_events)
    ccr_compressed_tokens = sum(e.get("compressed_tokens", 0) for e in ccr_events)
    ccr_saved_tokens = sum(e.get("saved_tokens", 0) for e in ccr_events)
    ccr_saved_percent = round((ccr_saved_tokens / ccr_raw_tokens * 100), 1) if ccr_raw_tokens > 0 else 0.0

    return {
        "task": task,
        "reads": {
            "total_reads": len(read_events),
            "unique_reads": len(reads_by_path),
            "in_scope_reads": in_scope_reads,
            "out_of_scope_reads": out_of_scope_reads,
            "framework_reads": framework_reads,
        },
        "tokens": {
            "in_scope_read_tokens": in_scope_tokens,
            "out_of_scope_read_tokens": out_of_scope_tokens,
            "framework_read_tokens": framework_tokens,
            "total_read_tokens": total_read_tokens,
            "task_artifacts_written_tokens": task_artifacts_written_tokens,
            "task_artifacts_count": task_artifacts_count,
        },
        "waste": {
            "duplicate_reads": {
                "files": dup_files,
                "count": len(dup_files),
                "wasted_reads": wasted_reads_total,
                "wasted_tokens": wasted_tokens_total,
            },
            "unmodified_oos_reads": {
                "files": unmodified_oos_files,
                "count": len(unmodified_oos_files),
                "wasted_tokens": unmodified_oos_tokens,
            },
            "churn": {
                "denied_shell": denied_shell,
                "repeated_shell": repeated_shell,
                "writes_denied": writes_denied,
                "violations": violations,
                "total_churn_events": denied_shell + repeated_shell + writes_denied + violations,
            },
            "ccr_savings": {
                "raw_tokens": ccr_raw_tokens,
                "compressed_tokens": ccr_compressed_tokens,
                "saved_tokens": ccr_saved_tokens,
                "saved_percent": ccr_saved_percent,
            },
        },
    }


# --------------------------------------------------------------------------- learning & failure-to-success correlation
def sanitize_learning_text(text: str) -> str | None:
    if not text:
        return None
    t = INVISIBLE_UNICODE_RE.sub("", text)
    t = HTML_COMMENT_RE.sub("", t)
    if ARTIFACT_INJECTION_RE.search(t):
        return None
    t = " ".join(t.split()).strip()
    if not t:
        return None
    if not t.startswith("- "):
        t = f"- {t}"
    return t


def correlate_task_learnings(root: Path, task: str, pol: dict | None = None) -> dict:
    root = Path(root)
    trec = load_task(root, task)
    base_head = trec.get("baseline", {}).get("head") if trec else "HEAD"
    modified_files = set(changed_files(root, base_head)) if base_head else set()

    wd = root / WORK_REL / task
    planned_paths = set()
    if (wd / "WORK.md").exists():
        try:
            _, wbody = read_meta(wd / "WORK.md")
            planned_paths |= section_paths(section(wbody, "Relevant Files"))
            planned_paths |= section_paths(section(wbody, "Scope"))
        except Exception:
            pass
    if (wd / "PLAN.md").exists():
        try:
            _, pbody = read_meta(wd / "PLAN.md")
            planned_paths |= section_paths(section(pbody, "Files Likely To Change"))
            planned_paths |= section_paths(section(pbody, "Plan"))
        except Exception:
            pass

    # 1. Co-Change / Coupled Files
    coupled_candidates: list[str] = []
    framework_prefixes = (".helm/", ".cursor/", ".agents/", ".claude/", ".codex/", "AGENTS.md", f"{WORK_REL}/")
    for m in sorted(modified_files):
        if any(m.startswith(pfx) or m == pfx for pfx in framework_prefixes):
            continue
        if planned_paths and not is_planned(m, planned_paths):
            pl_str = ", ".join(f"`{p}`" for p in sorted(planned_paths)[:3])
            c_text = sanitize_learning_text(f"When modifying {pl_str}, also inspect `{m}` (co-modified in {task}).")
            if c_text and c_text not in coupled_candidates:
                coupled_candidates.append(c_text)

    # 2. Guardrail, shell denial recovery & verification transitions
    convention_candidates: list[str] = []
    audit_file = state_dir(root) / "audit" / f"{task}.jsonl"
    ev = []
    if audit_file.exists():
        for line in audit_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    ev.append(json.loads(line))
                except ValueError:
                    pass

    denied_shells = [e for e in ev if e.get("k") == "shell" and not e.get("ok", True)]
    successful_shells = [e for e in ev if e.get("k") == "shell" and e.get("ok", True)]
    if denied_shells and successful_shells:
        for ds in denied_shells:
            cmd = ds.get("cmd", "").strip()
            if cmd:
                c_text = sanitize_learning_text(f"Avoid command `{cmd}` (denied by policy guardrails during {task}).")
                if c_text and c_text not in convention_candidates:
                    convention_candidates.append(c_text)

    denied_writes = [e for e in ev if e.get("k") == "write_denied"]
    for dw in denied_writes:
        p = dw.get("p", "").strip()
        why = dw.get("why", "").strip()
        if p:
            c_text = sanitize_learning_text(f"Do not modify `{p}` directly ({why or 'write restricted by policy'}).")
            if c_text and c_text not in convention_candidates:
                convention_candidates.append(c_text)

    ccr_events = [e for e in ev if e.get("k") == "ccr"]
    failed_checks = {e.get("check") for e in ccr_events if e.get("exit") != 0}
    passed_checks = {e.get("check") for e in ccr_events if e.get("exit") == 0}
    fixed_checks = failed_checks & passed_checks
    for fc in sorted(fixed_checks):
        if fc:
            c_text = sanitize_learning_text(f"Verification check `{fc}` must be verified before handoff (failed and resolved in {task}).")
            if c_text and c_text not in convention_candidates:
                convention_candidates.append(c_text)

    # 3. Gate rejection & unblock feedback
    recs = load_records(root, task)
    for r in recs:
        if r.get("decision") == "reject" or r.get("gate") == "block":
            note = str(r.get("note", "")).strip()
            if note:
                c_text = sanitize_learning_text(f"Gate {r.get('gate', 'review')} requirement: {note}")
                if c_text and c_text not in convention_candidates:
                    convention_candidates.append(c_text)

    return {
        "task": task,
        "conventions": convention_candidates,
        "couplings": coupled_candidates,
    }


def apply_learnings_to_overlay(root: Path, pol: dict, task: str, learnings: dict) -> dict:
    root = Path(root)
    overlay_dir = root / OVERLAY_REL
    overlay_dir.mkdir(parents=True, exist_ok=True)

    added_conventions = []
    added_couplings = []

    # 1. Conventions (max 80 lines)
    conv_path = overlay_dir / "conventions.md"
    existing_conv_lines = conv_path.read_text(encoding="utf-8").splitlines() if conv_path.exists() else [
        "# Repository Architectural Conventions & Skill Guidance",
        "",
        "## Learned Conventions",
    ]
    if not any(re.match(r"^##\s+Learned Conventions", l) for l in existing_conv_lines):
        existing_conv_lines += ["", "## Learned Conventions"]

    existing_conv_set = set(existing_conv_lines)
    for c in learnings.get("conventions", []):
        if c not in existing_conv_set:
            existing_conv_lines.append(c)
            existing_conv_set.add(c)
            added_conventions.append(c)

    if len(existing_conv_lines) > 80:
        excess = len(existing_conv_lines) - 80
        l_idx = -1
        for idx, line in enumerate(existing_conv_lines):
            if re.match(r"^##\s+Learned Conventions", line):
                l_idx = idx
                break
        if l_idx != -1 and l_idx + 1 < len(existing_conv_lines):
            trim_start = l_idx + 1
            trim_end = min(len(existing_conv_lines), trim_start + excess)
            existing_conv_lines = existing_conv_lines[:trim_start] + existing_conv_lines[trim_end:]

    conv_path.write_text("\n".join(existing_conv_lines) + "\n", encoding="utf-8")

    # 2. Repository Map (max 120 lines)
    map_path = overlay_dir / "repository-map.md"
    existing_map_lines = map_path.read_text(encoding="utf-8").splitlines() if map_path.exists() else [
        "# Repository Map & File Couplings",
        "",
        "## Learned File Couplings",
    ]
    if not any(re.match(r"^##\s+Learned File Couplings", l) for l in existing_map_lines):
        existing_map_lines += ["", "## Learned File Couplings"]

    existing_map_set = set(existing_map_lines)
    for c in learnings.get("couplings", []):
        if c not in existing_map_set:
            existing_map_lines.append(c)
            existing_map_set.add(c)
            added_couplings.append(c)

    if len(existing_map_lines) > 120:
        excess = len(existing_map_lines) - 120
        l_idx = -1
        for idx, line in enumerate(existing_map_lines):
            if re.match(r"^##\s+Learned File Couplings", line):
                l_idx = idx
                break
        if l_idx != -1 and l_idx + 1 < len(existing_map_lines):
            trim_start = l_idx + 1
            trim_end = min(len(existing_map_lines), trim_start + excess)
            existing_map_lines = existing_map_lines[:trim_start] + existing_map_lines[trim_end:]

    map_path.write_text("\n".join(existing_map_lines) + "\n", encoding="utf-8")

    ensure_key()
    integrity_refresh(root, pol)

    return {
        "conventions_added": added_conventions,
        "couplings_added": added_couplings,
        "status": "updated",
    }


# --------------------------------------------------------------------------- diff digest
def generate_diff_digest(root: Path, task: str, base_head: str, wd: Path, pol: dict | None = None) -> Path:
    root = Path(root)
    wd = Path(wd)
    wd.mkdir(parents=True, exist_ok=True)
    digest_path = wd / "DIFF-DIGEST.md"

    pol = pol if pol is not None else load_policy(root)
    d_sha = diff_sha(root, base_head)
    gen_time = now()

    # Planned files from WORK.md and PLAN.md
    planned_paths = set()
    if (wd / "WORK.md").exists():
        try:
            _, wbody = read_meta(wd / "WORK.md")
            planned_paths |= section_paths(section(wbody, "Relevant Files"))
            planned_paths |= section_paths(section(wbody, "Scope"))
        except Exception:
            pass
    if (wd / "PLAN.md").exists():
        try:
            _, pbody = read_meta(wd / "PLAN.md")
            planned_paths |= section_paths(section(pbody, "Files Likely To Change"))
            planned_paths |= section_paths(section(pbody, "Plan"))
        except Exception:
            pass

    # Modified files
    modified_files = set(changed_files(root, base_head))
    # Untracked files
    untracked_out = git_out(root, ["ls-files", "--others", "--exclude-standard"])
    untracked_files = [f for f in untracked_out.splitlines() if f and not f.startswith((".helm/", f"{WORK_REL}/"))]

    framework_prefixes = (".helm/", ".cursor/", ".agents/", ".claude/", ".codex/", "AGENTS.md", f"{WORK_REL}/")
    repo_modified = sorted(f for f in modified_files if not any(f.startswith(pfx) or f == pfx for pfx in framework_prefixes))

    planned_and_modified = [f for f in repo_modified if is_planned(f, planned_paths)]
    planned_and_untouched = sorted(p for p in planned_paths if not any(f == p or f.startswith(p + "/") for f in repo_modified))
    unplanned_modified = [f for f in repo_modified if not is_planned(f, planned_paths)]

    # Numstat
    numstat_rc, numstat_out = git_run(root, ["diff", "--numstat", base_head, "--"])
    numstat_lines = numstat_out.decode("utf-8", "replace").splitlines()

    lockfile_patterns = (
        "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "poetry.lock",
        "Gemfile.lock", "composer.lock", ".min.js", ".min.css"
    )

    def classify_file(p: str) -> str:
        if any(p.endswith(lp) or lp in p for lp in lockfile_patterns):
            return "Lockfiles/Generated"
        p_lower = p.lower()
        if "test" in p_lower or "spec" in p_lower or any_match(pol.get("test_globs", []), p):
            return "Tests"
        if p.endswith((".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".rst")) or p.startswith("docs/"):
            return "Config/Docs"
        return "Source"

    numstat_rows = []
    for line in numstat_lines:
        parts = line.split("\t")
        if len(parts) >= 3:
            added, deleted, p = parts[0], parts[1], parts[2]
            cat = classify_file(p)
            numstat_rows.append(f"| `{p}` | +{added} | -{deleted} | {cat} |")

    for u in untracked_files:
        cat = classify_file(u)
        numstat_rows.append(f"| `{u}` | (new) | - | {cat} |")

    # Static review signals: added signatures and risk markers
    _, raw_diff_b = git_run(root, ["diff", "-U3", base_head, "--"])
    raw_diff = raw_diff_b.decode("utf-8", "replace")

    sig_re = re.compile(r"^\+\s*(?:export\s+)?(?:def\s+[A-Za-z0-9_]+|class\s+[A-Za-z0-9_]+|function\s+[A-Za-z0-9_]+|const\s+[A-Za-z0-9_]+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)", re.M)
    risk_re = re.compile(r"\b(TODO|FIXME|@ts-ignore|eslint-disable|eval\(|subprocess|SELECT \*|exec\(|unsafe)\b")

    found_sigs = []
    found_risks = []
    for line in raw_diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            for sig in sig_re.findall(line):
                cleaned_sig = sig.lstrip("+").strip()
                if cleaned_sig and cleaned_sig not in found_sigs:
                    found_sigs.append(cleaned_sig)
            m = risk_re.search(content)
            if m:
                found_risks.append(f"`{m.group(0)}` in: `{content.strip()[:80]}`")

    # Unified Diff Hunks (folding lockfiles into CCR pointers)
    diff_hunk_lines = []
    current_file = None
    file_lines = []

    def flush_file_hunks():
        nonlocal current_file, file_lines, diff_hunk_lines
        if not current_file:
            return
        if any(current_file.endswith(lp) or lp in current_file for lp in lockfile_patterns):
            diff_hunk_lines.append(
                f"[... CCR: lockfile/generated diff omitted ({len(file_lines)} lines, folded: lockfile) -> git diff {base_head} -- {current_file} ...]"
            )
        else:
            diff_hunk_lines.extend(file_lines)
        file_lines = []

    for line in raw_diff.splitlines():
        if line.startswith("diff --git "):
            flush_file_hunks()
            m = re.search(r" b/(.+)$", line)
            current_file = m.group(1) if m else None
            file_lines = [line]
        else:
            file_lines.append(line)
    flush_file_hunks()

    for u in untracked_files:
        if any(u.endswith(lp) or lp in u for lp in lockfile_patterns):
            diff_hunk_lines.append(
                f"[... CCR: lockfile/generated file omitted (untracked, folded: lockfile) -> {u} ...]"
            )
        else:
            try:
                p_obj = root / u
                if p_obj.is_file():
                    u_lines = p_obj.read_text(encoding="utf-8", errors="replace").splitlines()
                    diff_hunk_lines.append(f"diff --git a/{u} b/{u}\nnew file mode 100644\n--- /dev/null\n+++ b/{u}\n@@ -0,0 +1,{len(u_lines)} @@")
                    diff_hunk_lines.extend("+" + ul for ul in u_lines[:50])
                    if len(u_lines) > 50:
                        diff_hunk_lines.append(f"[... omitted {len(u_lines) - 50} lines of new file ...]")
            except Exception:
                pass

    max_diff_lines = 1000
    if len(diff_hunk_lines) > max_diff_lines:
        omitted = len(diff_hunk_lines) - max_diff_lines
        diff_hunk_lines = diff_hunk_lines[:max_diff_lines]
        diff_hunk_lines.append(f"\n[... CCR: omitted {omitted} diff lines -> run git diff {base_head} ...]")

    rendered_diff = "\n".join(diff_hunk_lines)

    content = [
        "---",
        "status: ready",
        f"task: {task}",
        f"base_head: {base_head}",
        f"diff_sha: {d_sha}",
        f"files_changed: {len(repo_modified)}",
        f"unplanned_files: {len(unplanned_modified)}",
        f"generated: {gen_time}",
        "---",
        f"# Reviewer Diff Digest: {task}",
        "",
        "## Summary",
        f"- **Files Changed**: {len(repo_modified)}",
        f"- **Unplanned Changes**: {len(unplanned_modified)}",
        "",
        "## Scope Analysis",
        f"- **Planned & Modified** ({len(planned_and_modified)}): " + (", ".join(f"`{f}`" for f in planned_and_modified) if planned_and_modified else "None"),
        f"- **Planned & Untouched** ({len(planned_and_untouched)}): " + (", ".join(f"`{f}`" for f in planned_and_untouched) if planned_and_untouched else "None"),
        f"- **Unplanned Modified (Scope Creep Warning)** ({len(unplanned_modified)}): " + (", ".join(f"`{f}` [⚠️ UNPLANNED (scope creep)]" for f in unplanned_modified) if unplanned_modified else "None (Clean Scope)"),
        f"- **Untracked Files** ({len(untracked_files)}): " + (", ".join(f"`{f}`" for f in untracked_files) if untracked_files else "None"),
        "",
        "## Classification",
        "| File | Added | Deleted | Classification |",
        "|---|---|---|---|",
    ]
    if numstat_rows:
        content.extend(numstat_rows)
    else:
        content.append("| None | 0 | 0 | - |")

    content.extend([
        "",
        "## Static Review Signals",
        "### Modified Signatures",
    ])
    if found_sigs:
        content.extend([f"- `{s}`" for s in found_sigs[:25]])
    else:
        content.append("- None detected")

    content.extend([
        "",
        "### Risk Markers Found in Diff",
    ])
    if found_risks:
        content.extend([f"- {r}" for r in found_risks[:25]])
    else:
        content.append("- None (Clean)")

    content.extend([
        "",
        "## Per-File Summary & Unified Diff Hunks",
        "```diff",
        rendered_diff if rendered_diff.strip() else "(no diff)",
        "```",
        "",
    ])

    digest_text = "\n".join(content)
    digest_path.write_text(digest_text, encoding="utf-8")
    return digest_path

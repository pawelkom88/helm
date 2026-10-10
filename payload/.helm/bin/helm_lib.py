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
ARTIFACT_FILES = ["WORK.md", "PLAN.md", "TEST-PLAN.md", "IMPL.md", "REVIEW.md", "BLOCKED.md"]
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


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
    return re.compile("^" + out + "$")


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


def is_tmp(q: Path) -> bool:
    s = q.as_posix()
    tmp = (os.environ.get("TMPDIR") or "/tmp").rstrip("/")
    resolved_tmp = Path(tmp).resolve().as_posix().rstrip("/")
    resolved_slash_tmp = Path("/tmp").resolve().as_posix().rstrip("/")
    return (s.startswith("/tmp/") or s.startswith("/private/tmp/") or
            s.startswith("/dev/") or
            (bool(tmp) and s.startswith(tmp + "/")) or
            (bool(resolved_tmp) and s.startswith(resolved_tmp + "/")) or
            (bool(resolved_slash_tmp) and s.startswith(resolved_slash_tmp + "/")))


def classify(root, pol, q: Path) -> dict:
    root = Path(root)
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
             "source", "destination"}
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
                cands += [Path(dp) / f for f in fn]
        else:
            continue
        for p in cands:
            rel = p.relative_to(root).as_posix()
            if gmatch(g, rel):
                seen[rel] = None
    for rel in ("AGENTS.md",):
        if (root / rel).is_file():
            seen[rel] = None
    return sorted(seen)


def integrity_manifest(root, pol) -> dict:
    return {rel: sha256_file(Path(root) / rel) for rel in protected_files(root, pol)}


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


def load_records(root, task):
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
        if name == "WORK" and not section(body, "Acceptance Criteria"):
            probs.append("Acceptance Criteria is empty")
        if name == "REVIEW":
            if meta.get("verdict") not in ("APPROVE", "CHANGES_REQUIRED", "BLOCKED"):
                probs.append("REVIEW front matter `verdict` must be APPROVE|CHANGES_REQUIRED|BLOCKED")
            if not meta.get("diff_sha"):
                probs.append("REVIEW front matter `diff_sha` is required (from `helm status --json`)")
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
        for l in section(read_meta(wd / "WORK.md")[1], "Decisions").splitlines():
            l = l.strip()
            if l[:1] in "-*" and "[human]" in l:
                out.append(re.sub(r"^[-*]\s*", "", l))
    for r in load_records(root, task):
        if r.get("gate") == "block" and r.get("decision") == "resolve" and r.get("note"):
            out.append(f"[human] {r['note']}")
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
            text = re.sub(r"\s*\[human\]\s*", " ", it).strip()
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

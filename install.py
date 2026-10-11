#!/usr/bin/env python3
"""Install or update HELM in a git repository (idempotent, merge-aware, stdlib only).

  python3 install.py /path/to/repo            install or update
  python3 install.py /path/to/repo --reset-policy   also overwrite .helm/policy/policy.json
  python3 install.py --print-system-hooks     print a managed /etc/cursor/hooks.json for IT

Never overwritten: .helm/repo/ (accepted overlay), .helm/skills.lock.json, .cursor/skills/, your
existing hooks/permissions entries (merged), the rest of your AGENTS.md (block is replaced in place).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"
BEGIN, END = "<!-- HELM:BEGIN", "<!-- HELM:END -->"


def read_payload_bytes(p: Path) -> bytes:
    try:
        return p.read_bytes()
    except OSError:
        rel = p.relative_to(HERE).as_posix()
        res = subprocess.run(["git", "show", f":{rel}"], cwd=HERE, capture_output=True, check=True)
        return res.stdout


def read_payload_text(p: Path) -> str:
    return read_payload_bytes(p).decode("utf-8")


def copy_payload_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
    except OSError:
        data = read_payload_bytes(src)
        dst.write_bytes(data)


def ctext(text: str, style: str) -> str:
    if not (sys.stdout.isatty() or os.environ.get("FORCE_COLOR")):
        return text
    codes = {
        "bold": "\033[1m", "dim": "\033[2m", "cyan": "\033[36m",
        "bold_cyan": "\033[1;36m", "green": "\033[32m", "bold_green": "\033[1;32m",
        "blue": "\033[34m", "bold_blue": "\033[1;34m", "reset": "\033[0m"
    }
    return f"{codes.get(style, '')}{text}{codes['reset']}"


def print_next_steps():
    c_blue = ctext("", "bold_blue")[:7] if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""
    c_green = ctext("", "bold_green")[:7] if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""
    c_cyan = ctext("", "bold_cyan")[:7] if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""
    c_bold = "\033[1m" if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""
    c_dim = "\033[2m" if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""
    c_reset = "\033[0m" if sys.stdout.isatty() or os.environ.get("FORCE_COLOR") else ""

    w = 70
    top = "┌" + "─" * w + "┐"
    div = "├" + "─" * w + "┤"
    bot = "└" + "─" * w + "┘"

    def vlen(s):
        clean = re.sub(r"\x1b\[[0-9;]*m", "", s)
        extra = sum(1 for ch in clean if ord(ch) > 0x2000)
        return len(clean) + extra

    lines = [
        f"{c_blue}🚀 HELM Next Steps{c_reset}",
        "---",
        f"{c_green}✔{c_reset} {c_bold}Local-Only Governance{c_reset}: Framework files are gitignored.",
        f"  {c_dim}Only your actual code changes will ever be committed.{c_reset}",
        "",
        f"{c_bold}1. Verify Live Agent Interception{c_reset} {c_dim}(proves hooks are active){c_reset}:",
        f"   {c_cyan}$ .helm/bin/helm doctor --live{c_reset}",
        "",
        f"{c_bold}2. Put helm on your PATH{c_reset} {c_dim}(optional convenience){c_reset}:",
        f"   {c_cyan}$ ln -s \"$PWD/.helm/bin/helm\" ~/.local/bin/helm{c_reset}",
        "",
        f"{c_bold}3. Start a governed engineering task{c_reset}:",
        f"   {c_cyan}$ helm start <TASK_ID>{c_reset}",
    ]

    print("\n" + top)
    for item in lines:
        if item == "---":
            print(div)
        else:
            pad = max(0, w - vlen(item) - 1)
            print("│ " + item + (" " * pad) + "│")
    print(bot + "\n")
def get_platform_gitignores(platforms: list[str]) -> list[str]:
    ignores = [
        ".helm/",
        "AGENTS.md",
        "mcp_jira_config.json",
        "__pycache__/",
        "*.py[cod]",
    ]
    if "antigravity" in platforms:
        ignores.append(".agents/")
    if "claude" in platforms:
        ignores.append(".claude/")
    if "codex" in platforms:
        ignores.append(".codex/")
    if "cursor" in platforms:
        ignores.extend([
            ".cursor/agents/",
            ".cursor/commands/",
            ".cursor/skills/",
            ".cursor/cli.json",
            ".cursor/hooks.json",
            ".cursor/mcp.json",
        ])
    return ignores


MERGED = {".cursor/hooks.json", ".cursor/cli.json", ".cursor/mcp.json"}
KEEP_IF_EXISTS: set[str] = set()


def say(msg):
    print(f"  {msg}")


def merge_skills_lock(dst: Path, src: Path) -> bool:
    try:
        ours = json.loads(read_payload_text(src)) if src.exists() else {"skills": []}
    except Exception:
        ours = {"skills": []}
    try:
        cur = json.loads(dst.read_text()) if dst.exists() else {"skills": []}
    except Exception:
        cur = {"skills": []}
    if not isinstance(ours, dict) or not isinstance(ours.get("skills"), list):
        ours = {"skills": []}
    if not isinstance(cur, dict) or not isinstance(cur.get("skills"), list):
        cur = {"skills": []}
    existing_names = {s.get("name") for s in cur["skills"] if isinstance(s, dict) and "name" in s}
    added = False
    for s in ours["skills"]:
        if isinstance(s, dict) and s.get("name") and s["name"] not in existing_names:
            cur["skills"].append(s)
            existing_names.add(s["name"])
            added = True
    if not dst.exists() or added:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(cur, indent=2) + "\n")
    return added


def merge_hooks(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {"version": 1, "hooks": {}}
    cur.setdefault("version", 1)
    hooks = cur.setdefault("hooks", {})
    for ev, entries in ours["hooks"].items():
        kept = [e for e in hooks.get(ev, []) if "helm_guard.py" not in e.get("command", "")]
        hooks[ev] = kept + entries
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_cli(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {"permissions": {"allow": [], "deny": []}}
    cur.pop("version", None)
    perms = cur.setdefault("permissions", {})
    for k in ("allow", "deny"):
        lst = perms.setdefault(k, [])
        lst += [x for x in ours["permissions"].get(k, []) if x not in lst]
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_mcp(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {"mcpServers": {}}
    servers = cur.setdefault("mcpServers", {})
    for k, v in ours.get("mcpServers", {}).items():
        if k not in servers:
            servers[k] = v
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_antigravity_hooks(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {}
    cur["helm-guard"] = ours["helm-guard"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_claude_settings(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {}
    hooks = cur.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    kept = [e for e in pre if "helm_guard.py" not in e.get("command", "")]
    hooks["PreToolUse"] = kept + ours["hooks"]["PreToolUse"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_codex_hooks(dst: Path, src: Path):
    ours = json.loads(read_payload_text(src))
    cur = json.loads(dst.read_text()) if dst.exists() else {"hooks": {}}
    hooks = cur.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    kept = []
    for entry in pre:
        h_list = [h for h in entry.get("hooks", []) if "helm_guard.py" not in h.get("command", "")]
        if h_list:
            entry["hooks"] = h_list
            kept.append(entry)
    hooks["PreToolUse"] = kept + ours["hooks"]["PreToolUse"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def prompt_platform(repo: Path) -> list[str]:
    has_ag = (repo / ".agents").exists()
    has_cl = (repo / ".claude").exists()
    has_cx = (repo / ".codex").exists()
    has_cu = (repo / ".cursor").exists()

    default_choice = "4"
    if has_ag:
        default_choice = "1"
    elif has_cl:
        default_choice = "2"
    elif has_cx:
        default_choice = "3"
    elif has_cu:
        default_choice = "4"

    print("\n" + "=" * 68)
    print("  🔍 AI Platform Configuration")
    print("=" * 68)
    print("  Which AI coding platform(s) would you like to configure HELM for?")
    print(f"  [1] Google Antigravity {'(detected .agents/)' if has_ag else ''}")
    print(f"  [2] Anthropic Claude Code {'(detected .claude/)' if has_cl else ''}")
    print(f"  [3] OpenAI Codex CLI {'(detected .codex/)' if has_cx else ''}")
    print(f"  [4] Cursor {'(detected .cursor/)' if has_cu else ''}")
    print("  [5] Multi-Platform (All platforms)")

    try:
        choice = input(f"\nSelect platform [1-5, default: {default_choice}]: ").strip() or default_choice
    except (EOFError, KeyboardInterrupt):
        choice = default_choice

    mapping = {
        "1": ["antigravity"],
        "2": ["claude"],
        "3": ["codex"],
        "4": ["cursor"],
        "5": ["antigravity", "claude", "codex", "cursor"],
    }
    selected = mapping.get(choice, ["cursor"])
    print(f"  ✔ Configured for: {', '.join(selected)}\n")
    return selected


def insert_block(agents: Path, block: str):
    block = block.strip() + "\n"
    if agents.exists():
        txt = agents.read_text()
        if BEGIN in txt and END in txt:
            a, b = txt.index(BEGIN), txt.index(END) + len(END)
            txt = txt[:a] + block.rstrip("\n") + txt[b:]
        else:
            txt = txt.rstrip("\n") + "\n\n" + block
    else:
        txt = block
    agents.write_text(txt)


def print_system_hooks():
    cfg = json.loads((PAYLOAD / ".cursor/hooks.json").read_text())
    for entries in cfg["hooks"].values():
        for e in entries:
            e["command"] = e["command"].replace("python3 .helm/bin/", "python3 /opt/helm/bin/")
    print(json.dumps(cfg, indent=2))
    print("\n# For IT — deploy outside the developer-writable area:\n"
          "#   1. copy payload/.helm/bin/*  ->  /opt/helm/bin/   (root-owned, read-only)\n"
          "#   2. save the JSON above as    /etc/cursor/hooks.json  (managed hooks outrank project hooks)\n"
          "#   3. optional scalar overrides (e.g. subagents.mode) in /etc/helm/policy.json; lists there are unioned\n"
          "#   The guard still reads the repo's .helm/policy/policy.json and .helm/repo overlay.", file=sys.stderr)


def setup_global():
    PAYLOAD_DST = Path.home() / ".helm/blueprint"
    PAYLOAD_DST.mkdir(parents=True, exist_ok=True)
    try:
        payload_files = [p for p in PAYLOAD.rglob("*") if p.is_file()]
    except OSError:
        payload_files = []
    if not payload_files:
        try:
            res = subprocess.run(["git", "ls-files", "payload"], cwd=HERE, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout:
                payload_files = [HERE / line.strip() for line in res.stdout.splitlines() if line.strip() and (HERE / line.strip()).is_file()]
        except Exception:
            pass

    for src in sorted(payload_files):
        rel = src.relative_to(PAYLOAD).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        dst = PAYLOAD_DST / rel
        copy_payload_file(src, dst)
    for f in ("helm", "helm_guard.py", "helm_lib.py"):
        p = PAYLOAD_DST / ".helm/bin" / f
        if p.exists():
            os.chmod(p, 0o755)

    bin_dir = Path.home() / ".local/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    launcher = bin_dir / "helm"
    launcher_script = f"""#!/usr/bin/env bash
exec python3 "{PAYLOAD_DST}/.helm/bin/helm" "$@"
"""
    launcher.write_text(launcher_script)
    os.chmod(launcher, 0o755)

    print("\n" + "=" * 68)
    print("  ✔ HELM 1.0.0 installed globally!")
    print(f"  • Global CLI launcher : {launcher}")
    print(f"  • Master blueprint    : {PAYLOAD_DST}")
    print("=" * 68)
    print("\nYou can now open ANY repository in your terminal and simply type:")
    print("  helm\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?")
    ap.add_argument("--global", dest="global_install", action="store_true", help="Install HELM globally so 'helm' works everywhere")
    ap.add_argument("--platform", choices=["antigravity", "claude", "codex", "cursor", "all"], help="Target AI agent platform")
    ap.add_argument("--ag", dest="platform_ag", action="store_true", help="Shortcut for --platform antigravity")
    ap.add_argument("--reset-policy", action="store_true")
    ap.add_argument("--print-system-hooks", action="store_true")
    a = ap.parse_args()
    if a.platform_ag:
        a.platform = "antigravity"
    if a.print_system_hooks:
        return print_system_hooks()
    if a.global_install:
        return setup_global()
    if not a.repo:
        ap.error("repo path required (or use --global to install system-wide)")
    repo = Path(a.repo).resolve()
    top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        sys.exit(f"{repo} is not inside a git repository")
    if Path(top.stdout.strip()).resolve() != repo:
        sys.exit(f"open/install at the repository root: {top.stdout.strip()}")
    if sys.version_info < (3, 9):
        sys.exit("python >= 3.9 required")

    existing = (repo / ".helm/VERSION").read_text().strip() if (repo / ".helm/VERSION").exists() else None
    print(f"{'Updating' if existing else 'Installing'} HELM into {repo}" + (f" (was {existing})" if existing else ""))

    # Determine platform(s)
    if a.platform:
        platforms = ["antigravity", "claude", "codex", "cursor"] if a.platform == "all" else [a.platform]
    elif sys.stdin.isatty():
        platforms = prompt_platform(repo)
    else:
        platforms = []
        if (repo / ".agents").exists():
            platforms.append("antigravity")
        if (repo / ".claude").exists():
            platforms.append("claude")
        if (repo / ".codex").exists():
            platforms.append("codex")
        if (repo / ".cursor").exists() or not platforms:
            platforms.append("cursor")

    try:
        payload_files = [p for p in PAYLOAD.rglob("*") if p.is_file()]
    except OSError:
        payload_files = []
    if not payload_files:
        try:
            res = subprocess.run(["git", "ls-files", "payload"], cwd=HERE, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout:
                payload_files = [HERE / line.strip() for line in res.stdout.splitlines() if line.strip() and (HERE / line.strip()).is_file()]
        except Exception:
            pass

    for src in sorted(payload_files):
        rel = src.relative_to(PAYLOAD).as_posix()
        if rel == "AGENTS.helm.md" or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        if rel.startswith(".agents/") and "antigravity" not in platforms:
            continue
        if rel.startswith(".claude/") and "claude" not in platforms:
            continue
        if rel.startswith(".codex/") and "codex" not in platforms:
            continue
        if rel.startswith(".cursor/") and "cursor" not in platforms:
            continue
        if rel.startswith((".cursor/skills/", ".agents/skills/", ".claude/skills/", ".codex/skills/", ".helm/repo/")):
            continue

        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == ".agents/hooks.json":
            merge_antigravity_hooks(dst, src)
            ag_helm = repo / ".agents/.helm"
            if ag_helm.is_symlink() and not ag_helm.exists():
                try:
                    ag_helm.unlink()
                except Exception:
                    pass
            if not ag_helm.exists() and not ag_helm.is_symlink():
                try:
                    ag_helm.symlink_to("../.helm")
                    say("linked .agents/.helm -> ../.helm")
                except Exception:
                    pass
            say("configured .agents/hooks.json (Antigravity fail-closed hooks)")
        elif rel == ".claude/settings.json":
            merge_claude_settings(dst, src)
            say("configured .claude/settings.json (Claude Code fail-closed hooks)")
        elif rel == ".codex/hooks.json":
            merge_codex_hooks(dst, src)
            say("configured .codex/hooks.json (OpenAI Codex fail-closed hooks)")
        elif rel == ".cursor/hooks.json":
            merge_hooks(dst, src)
            say("merged .cursor/hooks.json (your own hooks preserved)")
        elif rel == ".cursor/cli.json":
            merge_cli(dst, src)
            say("merged .cursor/cli.json (your own permissions preserved)")
        elif rel == ".cursor/mcp.json":
            merge_mcp(dst, src)
            say("initialized .cursor/mcp.json (set JIRA_URL, JIRA_USERNAME & JIRA_API_TOKEN for Jira integration)")
        elif rel == ".helm/skills.lock.json":
            had_dst = dst.exists()
            added = merge_skills_lock(dst, src)
            if not had_dst:
                say("initialized .helm/skills.lock.json with bundled skills")
            elif added:
                say("merged .helm/skills.lock.json (bundled skills registered)")
        elif rel in KEEP_IF_EXISTS and dst.exists():
            continue
        elif rel == ".helm/policy/policy.json" and dst.exists() and dst.read_bytes() != read_payload_bytes(src) and not a.reset_policy:
            copy_payload_file(src, dst.with_name("policy.json.new"))
            say("policy.json differs from the new default → wrote policy.json.new (diff and merge by hand, or --reset-policy)")
        else:
            copy_payload_file(src, dst)

    # Ensure skill directories exist for active platforms
    platform_skills_dirs = []
    if "antigravity" in platforms:
        ag_skills = repo / ".agents/skills"
        ag_skills.mkdir(parents=True, exist_ok=True)
        platform_skills_dirs.append(ag_skills)
    if "claude" in platforms:
        cl_skills = repo / ".claude/skills"
        cl_skills.mkdir(parents=True, exist_ok=True)
        platform_skills_dirs.append(cl_skills)
    if "codex" in platforms:
        cx_skills = repo / ".codex/skills"
        cx_skills.mkdir(parents=True, exist_ok=True)
        platform_skills_dirs.append(cx_skills)
    if "cursor" in platforms:
        cu_skills = repo / ".cursor/skills"
        cu_skills.mkdir(parents=True, exist_ok=True)
        platform_skills_dirs.append(cu_skills)

    # Copy bundled skills to active platform directories if not already present
    bundled_skills_src = PAYLOAD / ".cursor/skills"
    if bundled_skills_src.exists():
        copied_skills = set()
        skill_dirs = []
        try:
            skill_dirs = [s for s in sorted(bundled_skills_src.iterdir()) if s.is_dir()]
        except OSError:
            try:
                res = subprocess.run(["git", "ls-files", "payload/.cursor/skills"], cwd=HERE, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout:
                    s_names = {line.strip().split("/")[3] for line in res.stdout.splitlines() if line.strip().startswith("payload/.cursor/skills/") and len(line.strip().split("/")) > 3}
                    skill_dirs = [bundled_skills_src / name for name in sorted(s_names)]
            except Exception:
                pass

        for s_dir in skill_dirs:
            for p_dir in platform_skills_dirs:
                target_skill = p_dir / s_dir.name
                if not target_skill.exists():
                    try:
                        shutil.copytree(s_dir, target_skill, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
                    except OSError:
                        res = subprocess.run(["git", "ls-files", f"payload/.cursor/skills/{s_dir.name}"], cwd=HERE, capture_output=True, text=True)
                        if res.returncode == 0 and res.stdout:
                            for f in res.stdout.splitlines():
                                f = f.strip()
                                if f:
                                    rel_in_skill = f[len(f"payload/.cursor/skills/{s_dir.name}/"):]
                                    dst_f = target_skill / rel_in_skill
                                    dst_f.parent.mkdir(parents=True, exist_ok=True)
                                    copy_payload_file(HERE / f, dst_f)
                    copied_skills.add(s_dir.name)
        if copied_skills:
            say(f"copied bundled skills to active platform(s): {', '.join(sorted(copied_skills))}")

    for f in ("helm", "helm_guard.py", "helm_lib.py"):
        os.chmod(repo / ".helm/bin" / f, 0o755)
    say("copied agents, commands, templates, bin/")

    cfg_path = repo / ".helm/config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    cfg["platforms"] = platforms
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    say(f"configured platform(s): {', '.join(platforms)}")

    insert_block(repo / "AGENTS.md", read_payload_text(PAYLOAD / "AGENTS.helm.md"))
    say("AGENTS.md: HELM constitution block inserted/updated between markers")

    gi = repo / ".gitignore"
    cur = gi.read_text() if gi.exists() else ""
    platform_ignores = get_platform_gitignores(platforms)
    add = [l for l in platform_ignores if l not in cur.splitlines()]
    if add:
        gi.write_text(cur.rstrip("\n") + ("\n" if cur else "") + "# HELM local developer governance files\n" + "\n".join(add) + "\n")
        say(f".gitignore += {', '.join(add)}")

    env = dict(os.environ)
    if sys.stdout.isatty():
        env["FORCE_COLOR"] = "1"
    r = subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "init"], cwd=repo, env=env, capture_output=True, text=True)
    say(r.stdout.strip().splitlines()[0] if r.returncode == 0 else f"helm init FAILED: {r.stderr.strip()}")

    print("\n" + ctext("--- helm doctor ---", "bold"))
    if sys.stdout.isatty():
        subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "doctor"], cwd=repo, env=env)
    else:
        r = subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "doctor"], cwd=repo, env=env, capture_output=True, text=True)
        print(r.stdout)

    print_next_steps()

    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            ans = input("\nWould you like to configure specialized models for Planner/Reviewer now? [y/N]: ").strip().lower()
            if ans in ("y", "yes"):
                subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "setup"], cwd=repo)
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\n✖ Cancelled by user.", file=sys.stderr)
        sys.exit(130)

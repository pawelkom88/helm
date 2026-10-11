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
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"
BEGIN, END = "<!-- HELM:BEGIN", "<!-- HELM:END -->"
GITIGNORE = [
    ".helm/",
    ".cursor/agents/",
    ".cursor/commands/",
    ".cursor/skills/",
    ".cursor/cli.json",
    ".cursor/hooks.json",
    ".cursor/mcp.json",
    "AGENTS.md",
    "mcp_jira_config.json",
    "__pycache__/",
    "*.py[cod]",
]
MERGED = {".cursor/hooks.json", ".cursor/cli.json", ".cursor/mcp.json"}
KEEP_IF_EXISTS = {".helm/skills.lock.json"}


def say(msg):
    print(f"  {msg}")


def merge_hooks(dst: Path, src: Path):
    ours = json.loads(src.read_text())
    cur = json.loads(dst.read_text()) if dst.exists() else {"version": 1, "hooks": {}}
    cur.setdefault("version", 1)
    hooks = cur.setdefault("hooks", {})
    for ev, entries in ours["hooks"].items():
        kept = [e for e in hooks.get(ev, []) if "helm_guard.py" not in e.get("command", "")]
        hooks[ev] = kept + entries
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_cli(dst: Path, src: Path):
    ours = json.loads(src.read_text())
    cur = json.loads(dst.read_text()) if dst.exists() else {"permissions": {"allow": [], "deny": []}}
    cur.pop("version", None)
    perms = cur.setdefault("permissions", {})
    for k in ("allow", "deny"):
        lst = perms.setdefault(k, [])
        lst += [x for x in ours["permissions"].get(k, []) if x not in lst]
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_mcp(dst: Path, src: Path):
    ours = json.loads(src.read_text())
    cur = json.loads(dst.read_text()) if dst.exists() else {"mcpServers": {}}
    servers = cur.setdefault("mcpServers", {})
    for k, v in ours.get("mcpServers", {}).items():
        if k not in servers:
            servers[k] = v
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_antigravity_hooks(dst: Path, src: Path):
    ours = json.loads(src.read_text())
    cur = json.loads(dst.read_text()) if dst.exists() else {}
    cur["helm-guard"] = ours["helm-guard"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_claude_settings(dst: Path, src: Path):
    ours = json.loads(src.read_text())
    cur = json.loads(dst.read_text()) if dst.exists() else {}
    hooks = cur.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    kept = [e for e in pre if "helm_guard.py" not in e.get("command", "")]
    hooks["PreToolUse"] = kept + ours["hooks"]["PreToolUse"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cur, indent=2) + "\n")


def merge_codex_hooks(dst: Path, src: Path):
    ours = json.loads(src.read_text())
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
    for src in sorted(p for p in PAYLOAD.rglob("*") if p.is_file()):
        rel = src.relative_to(PAYLOAD).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        dst = PAYLOAD_DST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
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
    ap.add_argument("--reset-policy", action="store_true")
    ap.add_argument("--print-system-hooks", action="store_true")
    a = ap.parse_args()
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

    for src in sorted(p for p in PAYLOAD.rglob("*") if p.is_file()):
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
        if rel.startswith((".cursor/skills/", ".agents/skills/", ".claude/skills/", ".codex/skills/")):
            continue

        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == ".agents/hooks.json":
            merge_antigravity_hooks(dst, src)
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
        elif rel in KEEP_IF_EXISTS and dst.exists():
            continue
        elif rel == ".helm/policy/policy.json" and dst.exists() and dst.read_bytes() != src.read_bytes() and not a.reset_policy:
            shutil.copy2(src, dst.with_name("policy.json.new"))
            say("policy.json differs from the new default → wrote policy.json.new (diff and merge by hand, or --reset-policy)")
        else:
            shutil.copy2(src, dst)

    # Ensure skill directories exist for active platforms
    if "antigravity" in platforms:
        (repo / ".agents/skills").mkdir(parents=True, exist_ok=True)
    if "claude" in platforms:
        (repo / ".claude/skills").mkdir(parents=True, exist_ok=True)
    if "codex" in platforms:
        (repo / ".codex/skills").mkdir(parents=True, exist_ok=True)
    if "cursor" in platforms:
        (repo / ".cursor/skills").mkdir(parents=True, exist_ok=True)

    for f in ("helm", "helm_guard.py", "helm_lib.py"):
        os.chmod(repo / ".helm/bin" / f, 0o755)
    say("copied agents, commands, templates, bin/")

    cfg_path = repo / ".helm/config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    cfg["platforms"] = platforms
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    say(f"configured platform(s): {', '.join(platforms)}")

    insert_block(repo / "AGENTS.md", (PAYLOAD / "AGENTS.helm.md").read_text())
    say("AGENTS.md: HELM constitution block inserted/updated between markers")

    gi = repo / ".gitignore"
    cur = gi.read_text() if gi.exists() else ""
    add = [l for l in GITIGNORE if l not in cur.splitlines()]
    if add:
        gi.write_text(cur.rstrip("\n") + ("\n" if cur else "") + "# HELM task artifacts (may contain Jira content)\n" + "\n".join(add) + "\n")
        say(f".gitignore += {', '.join(add)}")

    env = dict(os.environ)
    r = subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "init"], cwd=repo, env=env, capture_output=True, text=True)
    say(r.stdout.strip().splitlines()[0] if r.returncode == 0 else f"helm init FAILED: {r.stderr.strip()}")
    r = subprocess.run([sys.executable, str(repo / ".helm/bin/helm"), "doctor"], cwd=repo, env=env, capture_output=True, text=True)
    print("\n--- helm doctor ---\n" + r.stdout)

    pdirs = []
    if "antigravity" in platforms: pdirs.append(".agents")
    if "claude" in platforms: pdirs.append(".claude")
    if "codex" in platforms: pdirs.append(".codex")
    if "cursor" in platforms: pdirs.append(".cursor")
    p_add = " ".join(pdirs) if pdirs else ".cursor"
    co_lines = "\n".join(f"       /{d}/   @your-platform-team" for d in pdirs) if pdirs else "       /.cursor/   @your-platform-team"

    print("NEXT STEPS\n"
          "  1. Review and COMMIT the framework files (a clean tree is required to start tasks):\n"
          f"       git add {p_add} .helm AGENTS.md .gitignore && git commit -m 'chore: add HELM framework'\n"
          "  2. Add to CODEOWNERS (so framework changes need review):\n"
          f"{co_lines}\n       /.helm/     @your-platform-team\n       /AGENTS.md  @your-platform-team\n"
          "  3. Configure the Atlassian MCP server (set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)\n"
          "     or leave as placeholders to use Local Story Mode (STORY.md).\n"
          "  4. Put helm on your PATH:  ln -s \"$PWD/.helm/bin/helm\" ~/.local/bin/helm\n"
          "  5. helm doctor --live        # proves hooks really fire through your AI runner (do not skip)\n"
          "  6. helm bootstrap start      # then /bootstrap with your agent: builds the repo-specific layer")

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

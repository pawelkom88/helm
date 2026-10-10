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

    for src in sorted(p for p in PAYLOAD.rglob("*") if p.is_file()):
        rel = src.relative_to(PAYLOAD).as_posix()
        if rel == "AGENTS.helm.md" or rel.startswith(".cursor/skills/") or "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == ".cursor/hooks.json":
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
    (repo / ".cursor/skills").mkdir(parents=True, exist_ok=True)
    for f in ("helm", "helm_guard.py", "helm_lib.py"):
        os.chmod(repo / ".helm/bin" / f, 0o755)
    say("copied agents, commands, templates, bin/")

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

    print("NEXT STEPS\n"
          "  1. Review and COMMIT the framework files (a clean tree is required to start tasks):\n"
          "       git add .cursor .helm AGENTS.md .gitignore && git commit -m 'chore: add HELM framework'\n"
          "  2. Add to CODEOWNERS (so framework changes need review):\n"
          "       /.cursor/   @your-platform-team\n       /.helm/     @your-platform-team\n       /AGENTS.md  @your-platform-team\n"
          "  3. Configure the Atlassian MCP server in .cursor/mcp.json (set JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN)\n"
          "     or leave as placeholders to use Local Story Mode (STORY.md).\n"
          "  4. Put helm on your PATH:  ln -s \"$PWD/.helm/bin/helm\" ~/.local/bin/helm\n"
          "  5. helm doctor --live        # proves hooks really fire through your Cursor CLI (do not skip)\n"
          "  6. helm bootstrap start      # then /bootstrap in Cursor: builds the repo-specific layer")

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

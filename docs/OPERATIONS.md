# Operations runbook

## Daily
`helm status` is the dashboard; it always prints **who acts next** and the exact command. Gates are yours; `/continue` after each.

## `helm doctor`
Static checks (always) + `--live` (launches the real Cursor CLI twice: main agent and a subagent, each told to run a command the guard always denies; passes only if the guard *saw* it). Set `HELM_CLI_CMD` if your invocation differs (default `cursor-agent -p --force --trust`; adjust flags to your CLI version). Run `--live` after: installing, upgrading Cursor, changing hooks, moving machines.

If `--live` FAILS:
1. Hooks are **not** protecting that route. Do not rely on phase gating there.
2. Check `.cursor/hooks.json` is at the repo root you opened, `python3` is on the hook environment's PATH (WSL vs Windows launcher!), and `CURSOR_PROJECT_DIR` is set for hooks.
3. Try `HELM_PROBE=1` in the environment, trigger a few edits/reads, then `helm doctor --probe` to see the real payload shapes; open an issue with Cursor if hooks never fire.
4. Until fixed: run agents in **IDE only if IDE passes**, or use `subagents.mode: "deny_all"` if only subagents fail (the main agent does the roles inline), and lean on the detective checks at each gate.

## Failure runbook
| Symptom | Cause | Do |
|---|---|---|
| Agent says `POLICY_BLOCK` | a guardrail did its job | read the reason; if it's a legitimate need (e.g. a dependency), do it yourself or relax policy deliberately |
| Phase `POLICY_BLOCK` | `afterFileEdit` saw an edit that should have been blocked (a pre-hook was bypassed) | `helm violations`; `git status`/`git diff`; revert; `helm violations --ack -m "…"` |
| Phase `BLOCKED` | agent hit material uncertainty | read `BLOCKED.md`; `helm unblock -m "Decision: …"`; `/continue` |
| `approve` says integrity drift | a protected file changed (hooks, policy, skills, AGENTS.md, CI, overlay) | `git diff`; if it was you: `helm integrity refresh`; if not: investigate before anything else |
| `approve` says Git state changed | HEAD/branch/refs/stash/worktree differ from task start | inspect `git reflog`/`git branch`; if yours: `helm baseline refresh` |
| "working tree changed before implementation was authorised" | something edited files in discovery/planning | `git status`; revert or `helm baseline refresh` |
| Phase `STATE_TAMPERED` | active pointer/task record failed its signature | `helm doctor`; check the key and `~/.helm` permissions |
| Everything denied / shell hangs after enabling `failClosed` | guard crashed (e.g. `python3` missing) so fail-closed blocks | edit `.cursor/hooks.json` **outside Cursor** (editor/terminal), fix the cause, `helm integrity refresh`; a Cursor build bug with fail-closed shell hooks has been reported, so keep a way to edit the file from outside |
| Verify says "tree changed while checks ran" | a check rewrites files (formatter/codegen) | make the check read-only (`--check`), or run the formatter during implementation |
| Overlay STALE | lockfiles/workspace/CI changed since bootstrap | `helm bootstrap start` → `/bootstrap` → review → accept |

## Updating the framework
`python3 /path/to/helm/install.py .` → review `git diff` → commit → `helm integrity refresh` (installer already does it, but commit first) → `helm doctor --live`. `policy.json` is never overwritten silently (a `.new` file is written).

## Rolling out to a team
1. Pilot with 2–3 volunteers for ~10 tickets with metrics (below).
2. Platform team owns `.cursor/**`, `.helm/**`, `AGENTS.md` via CODEOWNERS; skills approvals go through them.
3. Managed hooks (`install.py --print-system-hooks`) and a shared, reviewed `policy.json`.
4. Each repo runs its own `/bootstrap`; the accepted `.helm/repo/` is committed and reviewed like code. Re-bootstrap when `helm status` reports it stale.
5. **CI** (`docs/ci/`): `python3 .helm/bin/helm ci --base origin/<target> --require-overlay` needs no key, no state and no Cursor; it fails the build if any guard hook is not `failClosed`, the constitution block is missing, a skill is unapproved or modified, the MCP regex admits write-looking tools, task artifacts are committed, or the guard self-test fails; it warns when a PR touches protected paths (so CODEOWNERS review is required). Follow it with your project's own gates (`helm verify` runs the accepted `verify.json`). Make the job and code-owner review **required** in branch protection — that, plus no push credentials in the agent environment, is the real push/merge boundary.

## Pilot metrics (decide with data, not opinion)
Replay or run 5–10 tickets; compare against your baseline:
- tokens / cost per ticket (from Cursor usage) and wall-clock to an approved change
- `helm metrics`: files read **outside** WORK.md `Relevant Files` (target: low — otherwise the Work Brief is insufficient)
- gate rejection rate and **why** (scope wrong? plan wrong? missed component?)
- rework loops after review; share of `BLOCKED` events that were genuinely necessary
- guard denials by type (`helm metrics`), violations, integrity/Git detections (target: zero in normal use)
- human review time per gate (approval fatigue early warning)
If gates are rejected mostly for "missed existing component", improve the discovery role/overlay `frontend.md`; if mostly for "unclear acceptance criteria", fix tickets, not the framework.

## Backups / privacy
`~/.helm/state/<repo-id>/` holds signed decisions and the audit log (command prefixes, MCP tool names, read paths — no file contents). `.helm/work/` may contain Jira text: it is gitignored; `helm finish --clean` removes it.

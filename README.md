# HELM — Human-Controlled AI Engineering Framework  `v1.0.0`

A repo-agnostic, installable workflow layer for **Cursor** (CLI first, IDE too) in which agents investigate, propose, implement and verify — and **humans decide, approve and own the Git history**.

> **Agents may investigate, propose, implement and verify; humans decide, approve and own the resulting change.**

You drop it into any repo, run one bootstrap, and it builds a *repo-specific* layer (map, conventions, test and verify commands, policy additions) that you review and commit. After that, every ticket runs through the same gated pipeline with compressed hand-offs instead of repeated discovery.

---

## What you get

```
your-repo/
├── AGENTS.md                     ← constitution block (lean, ~45 lines) inserted between markers
├── .cursor/
│   ├── hooks.json                ← guard wiring (failClosed)
│   ├── cli.json                  ← Cursor CLI permission deny-list (second layer)
│   ├── agents/                   ← bootstrapper · discovery · planner · test-analyst · implementer · reviewer · specialist-reviewer
│   ├── commands/                 ← /bootstrap /work /continue /review /status (+ /approve /reject → "do it in a terminal")
│   └── skills/                   ← YOUR vendored, hash-locked skills (empty at start)
└── .helm/
    ├── bin/                      ← helm (CLI) · helm_guard.py (hook) · helm_lib.py
    ├── policy/policy.json        ← protected paths, secrets, shell/MCP/web rules, tiers
    ├── templates/                ← WORK / PLAN / TEST-PLAN / IMPL / REVIEW / BLOCKED / DISPATCH
    ├── repo/                     ← the repo-specific layer (created by bootstrap, COMMITTED, shared by the team)
    ├── skills.lock.json          ← approved skills: source, commit, licence, reviewer, content hash
    ├── work/<ID>/                ← per-task artifacts (gitignored)
    └── bootstrap/                ← proposal under review (gitignored)

~/.helm/                          ← OUTSIDE the workspace: signing key + signed approvals + audit log
```

## Requirements
Python ≥ 3.9 (stdlib only) · git · Cursor (CLI and/or IDE) · Atlassian MCP configured (optional, read-only enforced).

## Install

```bash
python3 /path/to/helm/install.py /path/to/your-repo     # idempotent; also use it to update
cd /path/to/your-repo
git add .cursor .helm AGENTS.md .gitignore && git commit -m "chore: add HELM framework"
ln -s "$PWD/.helm/bin/helm" ~/.local/bin/helm            # optional convenience
```

Existing hooks, CLI permissions and `AGENTS.md` content are **merged, never overwritten**. Re-running the installer updates the framework files and leaves `.helm/repo/`, `skills.lock.json`, `.cursor/skills/` alone.

### First-time checklist (do not skip step 3)
1. Add `/.cursor/ /.helm/ /AGENTS.md` to `CODEOWNERS` so framework changes need review.
2. Configure the Atlassian MCP (`docs/atlassian-mcp.example.json`); the server key must match `mcp.allow_servers`.
3. **`helm doctor --live`** — proves hooks actually fire through *your* Cursor CLI, including from a subagent. If this fails, enforcement is not active; read `docs/OPERATIONS.md`.
4. `helm bootstrap start` → in Cursor `/bootstrap` → read `.helm/bootstrap/proposal/` → `helm bootstrap accept` → commit `.helm/repo/`.

## Per ticket

```
 YOU (terminal)                         CURSOR (agents)                         STATE
 ──────────────                         ───────────────                         ─────
 helm start PROJ-1 --tier 2
                                        /work PROJ-1       discovery ─▶ WORK.md   AWAITING_DISCOVERY_APPROVAL
 review WORK.md
 helm approve discovery  (types ID)
                                        /continue          planner   ─▶ PLAN.md   AWAITING_PLAN_APPROVAL
 helm approve plan
                                        /continue          test-analyst ─▶ TEST-PLAN.md
                                                           implementer ─▶ code + IMPL.md
                                                           helm verify (signed result bound to the diff)
                                        /review            specialists ∥ → reviewer ─▶ REVIEW.md   AWAITING_FINAL_APPROVAL
 review diff + REVIEW.md
 helm approve final
 git commit / push / PR   ← YOURS      helm finish --clean                         READY_FOR_DEVELOPER → done
```

Anything uncertain → the agent writes `BLOCKED.md` and **stops**; you answer with `helm unblock -m "Decision: …"`, then `/continue`.

### Tiers (the human chooses at `helm start`)
| Tier | Use for | Gates | Stages |
|---|---|---|---|
| — | trivial edits | none (hard guardrails still apply) | just use Cursor, no `helm start` |
| **1** | small, well-understood changes | **discovery (brief + plan together)**, final | WORK.md with `## Plan` → implement → verify → *(optional review)* |
| **2** | everything else | discovery, plan, final | full pipeline |

## Command reference

**You (terminal) — human-only, TTY-gated, denied to agents**

| Command | Purpose |
|---|---|
| `helm start <ID> [--tier 1\|2]` | begin a task (clean tree required; snapshots Git state) |
| `helm approve discovery\|plan\|final` | record approval **bound to the exact artifact/diff hash**; you type the task ID |
| `helm reject <gate> -m "…"` | send it back; your note is written to `FEEDBACK.md` |
| `helm unblock -m "…"` | answer a `BLOCKED.md` |
| `helm finish [--clean]` / `helm abort` | end the task; `finish` lists the `[human]` decisions made and lets you promote chosen ones into `docs/decisions.md` (numbered `DEC-nnn`, human-only file) |
| `helm violations [--ack -m …]` | see / acknowledge guardrail breaches |
| `helm baseline refresh` · `helm integrity refresh` | accept your own Git / framework-file changes |
| `helm bootstrap start\|accept\|abort` | build the repo layer |
| `helm skills add <dir> --name … --source … --sha … --license … --reviewer …` | vendor + lock a reviewed skill |
| `helm doctor --live` | prove hooks fire through the real CLI |

**Anyone (agents may run these)**: `helm status [--json|--brief]` · `helm check [artifact]` · `helm verify [--only a,b]` · `helm metrics` · `helm log` · `helm doctor` · `helm skills verify|list`.

**CI (no key, no state, no Cursor)**: `helm ci [--base origin/main] [--require-overlay]` — asserts hooks are `failClosed`, constitution present, skills approved and unmodified, MCP regex read-only, no task artifacts committed, guard self-test passes, and lists protected files changed in the PR. Recipes: `docs/ci/github-actions.yml`, `docs/ci/bitbucket-pipelines.yml`. CI is the one control that does not depend on Cursor's hooks firing.

**In Cursor**: `/bootstrap` · `/work <ID>` · `/continue` · `/review` · `/status`. (`/approve` and `/reject` exist only to tell the agent to point you at the terminal.)

## How "human control" is actually enforced

| Rule | Mechanism | Class |
|---|---|---|
| No push / PR / merge | no credentials in the agent's environment + remote branch protection *(your setup)*; guard denies `gh glab curl ssh` and state-changing git | **Enforced** outside the agent when you do the setup; speed bump otherwise |
| No commit / rebase / branch | guard (parsed read-only git allowlist) · **HEAD/branch/refs/stash/worktree snapshot checked at every gate** | Enforced + **Detected** |
| No source edits before plan approval | phase-scoped write hook · signed approvals bound to artifact hashes · tree hash checked at the gate | Enforced (if hooks fire) + Detected |
| Agent cannot approve | approval is a TTY-only human command; records HMAC-signed with a key outside the workspace; agent shell access to it denied | Enforced (same-OS-user caveat) |
| Agent cannot edit hooks/policy/skills/approvals | protected-path deny (tool + shell) · integrity manifest checked at every gate · CODEOWNERS · optional managed hooks | Enforced + Detected |
| Atlassian read-only | `beforeMCPExecution` allowlist (server + read-verb regex), Confluence call budget, **plus** give the token read-only scopes | Enforced |
| Completion is evidence, not confidence | the reviewer's **Traceability table** (every acceptance criterion → implementation → an *existing* test file or `manual:` reason → pass/fail/unproven); `APPROVE` is invalid unless every row is `pass`; checked by `helm check REVIEW` and again at the final gate, which prints the proven/manual/unproven counts | Enforced (structure + file existence) · Instructed (that the cited test really proves it — the human reads it) |
| Verification is real | `helm verify` runs human-approved commands; result signed and bound to the diff hash; any later edit invalidates it | Enforced |
| Stop on uncertainty / no invented requirements | prompts + reviewer + human gate; `BLOCKED.md` mechanically freezes all writes | **Instructed** (with a mechanical freeze once raised) |

Full analysis and residual risks: `docs/THREAT-MODEL.md`. **Read it before you trust this with anything that matters.**

## What was and was not verified in this bundle

**Tested (Linux, Python 3.12, `python3 -m unittest -v tests/test_hcaf.py`, 41 tests)** — the whole Python layer: guard policy table + adversarial shell shapes, full tier-1 and tier-2 lifecycles, stale-review invalidation, forged/unsigned approvals, tampered state, cascade invalidation, git and protected-file tamper detection, `BLOCKED` freeze, bootstrap accept + overlay sanitising, skills vendoring/locking/tamper detection, traceability rules, decision promotion + integrity refresh, `helm ci` without key/state, installer merge behaviour, fail-closed on broken policy.

**NOT testable outside Cursor — verify on your machine** (each has a tool):

| Assumption | How to verify |
|---|---|
| Hook payload field names (`command`, `tool_name`, `tool_input`, `mcp_server_name`, `file_path`, `subagent_type`) match your Cursor version | `HELM_PROBE=1` in Cursor's environment → do some edits/reads → `helm doctor --probe` prints observed payload *shapes* |
| Hooks fire in the **CLI on WSL**, and from **subagents** | `helm doctor --live` (set `HELM_CLI_CMD` if your CLI invocation differs) |
| `cli.json` `Shell()/Read()/Write()` patterns match as intended | try a denied action through the CLI; the hook layer is the primary control either way |
| Atlassian read tool names (`getJiraIssue`, `search…`) | `mcp.allow_tool_regex` in policy; adjust if your server names differ |

If hooks do not fire on some route, **do not rely on the phase gating for that route**; the *detective* controls (gate-time Git/tree/integrity checks and `afterFileEdit` violations) still catch most breaches after the fact.

## Docs
`docs/METHODOLOGY.md` normative spec v2 · `docs/THREAT-MODEL.md` controls and residual risk · `docs/SKILLS-POLICY.md` skill supply chain · `docs/OPERATIONS.md` runbook, rollout, pilot metrics · `docs/ci/` CI recipes.

## Uninstall
Delete `.cursor/{agents,commands}/` entries, `.cursor/hooks.json` guard entries, `.helm/`, the HELM block in `AGENTS.md`, and `~/.helm/state/<repo>`.

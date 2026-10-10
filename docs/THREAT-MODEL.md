# HELM Threat Model

Purpose: say precisely what the framework stops, what it only detects, what it merely asks for, and what you must still do yourself. If this page and the README disagree, believe this page.

## 1. What we protect
| Asset | Why |
|---|---|
| Git history and remotes | irreversible once pushed; developer-owned |
| Requirements and architecture decisions | must be human decisions, not agent inventions |
| Secrets (`.env`, keys, tokens, cloud creds) | exfiltration |
| The control plane (hooks, policy, skills, approvals, signing key) | if the agent can edit it, nothing else holds |
| Jira / Confluence content | integrity (no writes) and confidentiality (no exfil) |
| Corporate network and dependencies | supply chain |

## 2. Adversaries (in order of likelihood)
1. **A cooperative but over-eager model** that "helps" by committing, pushing, or approving its own work.
2. **Prompt injection** via Jira descriptions/comments, Confluence pages, READMEs, web pages, package READMEs, tool output — someone with comment rights can steer the agent.
3. **A supply-chain skill** (instructions or scripts) with hidden behaviour.
4. **A tired human** rubber-stamping gates (process failure, not attack).
5. *Out of scope:* a malicious developer with shell access to their own account, or a fully adversarial agent with unrestricted OS access. See §6.

The dangerous combination is the **lethal trifecta**: untrusted content (Jira/web) + private data (repo, secrets) + an exfiltration channel (MCP write tools, web fetch, `curl`, `git push`). HELM removes legs: Atlassian writes denied, web fetch allowlisted, web search off, network CLIs denied, no push credentials (your setup).

## 3. Controls and their class

**E** = Enforced (action blocked) · **D** = Detected (caught at a gate or after the fact) · **I** = Instructed (prompt only).

| # | Threat | Control | Class | Fails when |
|---|---|---|---|---|
| 1 | Agent commits / rebases / branches | guard: parsed git allowlist (read-only subcommands; denies `-c`, `--output`, `--exec-path`…); nested shells, `env`/`xargs`/`timeout` wrappers, backticks, `$()`, `bash -c`, interpreter strings are analysed | E | git is invoked by a *script the guard cannot read* (`make`, `npm run x`, a checked-in `.sh`) |
| 2 | …same, any route | **Git snapshot** (HEAD, branch, refs, stash, worktrees, hooksPath) compared at every approve/finish | D | the agent restores state before the gate (unlikely; would need to undo its own commit) |
| 3 | Agent pushes / opens PR / merges | guard denies `gh glab hub curl wget ssh scp…`; **plus** you remove push credentials from the agent's environment and enable branch protection | E (if you do the setup) | credentials are present *and* the push goes via a script the guard cannot read |
| 4 | Agent approves its own work | approval = TTY-only human command; HMAC-signed records in `~/.helm` (outside workspace); guard denies every human-only `helm` subcommand and any mention of the state/key path | E | the agent can read `~/.helm/key` by a route the guard misses (same OS user) |
| 5 | Agent forges approvals / verification / active pointer | signatures; invalid records ignored; invalid active pointer → `STATE_TAMPERED` (all writes denied) | E | key compromised |
| 6 | Source edited before plan approval | phase-scoped write scope in `preToolUse`, and for *explicit* shell write targets; tree-hash vs baseline checked at discovery/plan approval | E + D | edit made by a tool/script with no visible path (`npm run codegen` rewriting files) → caught by D |
| 7 | Reviewer modifies code | REVIEW phase scope = `REVIEW*.md` only | E | as #6 |
| 8 | Agent edits hooks/policy/skills/AGENTS.md/CI | protected-path deny (tools + shell mentions), CLI `Write()` deny, **integrity manifest checked at every gate**, CODEOWNERS | E + D | hooks are not firing *and* the edit precedes the gate → D still catches it at the next gate |
| 9 | Hooks silently not firing | `helm doctor --live` canary through the real CLI (main agent and subagent); `afterFileEdit` violation ledger; gate-time detectives | D | you never run `doctor --live` |
| 10 | Hook crash/timeout fails open | all permission hooks `failClosed: true`; doctor fails if not | E | Cursor ignores `failClosed` on a given hook type (verify) |
| 11 | Secret read/exfil | secret globs denied for Read tools, `beforeReadFile`, and any shell token resolving to a secret path; network CLIs denied; web allowlist | E | secret is in a non-matching file name; pasted in chat by a human |
| 12 | Jira/Confluence write or injection-driven action | MCP: server allowlist + read-verb tool regex; unknown/missing server → deny; Confluence budget; untrusted-content rule; reviewer checks instruction-following | E (writes) + I (injection) | injection that merely *persuades* the agent to write bad code — needs the human gates and review |
| 13 | New dependency / arbitrary package execution | guard denies `npm|pnpm|yarn|bun add/install <pkg>`, `npx/dlx`, `pip install`, publish/login | E | dependency added by hand-editing `package.json` → shows in the diff; reviewer's scope check + `unplanned files` at final gate |
| 14 | Malicious/modified skill | vendored copy, content hash in lock, markdown-only default, risky-pattern scan, CI/doctor verify, discovery of unapproved skills flagged | D | skill discovered from a path Cursor loads but `doctor` does not scan |
| 15 | Stale / forged review or verification | both bound to the **diff hash**; edit after → phase regresses | E | — |
| 16 | Agent ignores `BLOCKED` | once raised, writes are frozen except `BLOCKED.md`; deleting the file does not unblock | E for writes, I for "stop talking" | agent keeps *discussing*; harmless without write access |
| 17 | Agent invents requirements / guesses | prompts + provenance tags + Assumptions/Open Questions + reviewer + human gates | I (+ human review) | nothing mechanical can prove absence of a guess |
| 18 | Approval fatigue | tiers; compact artifacts with size caps; `helm approve` prints open questions, `[inferred]` count, unplanned files, verdict | process | people stop reading |
| 19 | Hooks bypassed entirely / framework weakened in a PR | `helm ci` in CI (key-free): `failClosed` asserted, skills hash-verified, MCP regex read-only, no committed artifacts, protected-path changes flagged for CODEOWNERS | D (and E if the job is a required check) | CI job not required in branch protection |
| 20 | "Done" claimed without evidence | Traceability table: every criterion needs an existing test file or an explicit `manual:` reason; `APPROVE` impossible with unproven rows; final gate prints counts | E (structure, file existence) + I (that the test proves it) | the cited test exists but is weak — the human and independent review judge that |
| 21 | Agent rewrites durable decisions | `docs/decisions.md` is a protected path; promotion is a human TTY act | E | — |

## 4. Platform facts that shape the design (as reported by Cursor docs/forums, Oct 2026 — verify on your build)
- Hook `failClosed` **defaults to false**; crashes, timeouts and unexpected exit codes let the action through unless set. → every guard sets it.
- Permission `ask` is not enforced for `preToolUse`/shell hooks → HELM uses allow/deny only.
- Project hooks live in the repo and reload automatically. → protected-path rules + integrity manifest + (best) managed hooks.
- Managed/enterprise hooks outrank project hooks (Linux/WSL path `/etc/cursor/hooks.json`); any deny wins.
- Reports exist of Cursor **CLI hook coverage gaps** (hooks not invoked on Linux for a specific build; `beforeSubmitPrompt`, `afterAgentResponse`, `stop` not sent by the CLI). HELM therefore relies only on `beforeShellExecution`, `beforeMCPExecution`, `preToolUse`, `beforeReadFile`, `subagentStart`, `afterFileEdit` — and **proves** coverage with `doctor --live` instead of assuming it.
- CLI `Shell()` permissions match the **first token** only → `Shell(git)` would be all-or-nothing, so git is controlled by the hook, not by `cli.json`.
- Skills load from project, nested and user directories; there is no CLI switch to skip them → unapproved skills are *detected*, not prevented.
- Reports of `Mcp(...)` allow entries not matching in the CLI → HELM does not rely on them.
- Subagent hook coverage and the identity of the calling subagent in hook payloads are **not documented** → writes are scoped by phase, and `subagents.mode` can be `deny_all` to force inline execution.

## 5. Same-OS-user boundary (the honest part)
The agent runs as *you*. The signing key, state directory and `helm` binary are reachable by any process of yours. HELM makes crossing that line (a) blocked by the guard for every visible route, (b) **detectable** by signatures, hashes and snapshots, and (c) impossible to do *accidentally*. It is **not** a sandbox. A determined, fully shell-capable adversarial agent can defeat a same-user guard.

If that matters for your risk profile, move the boundary:
1. Run the Cursor CLI as a **separate OS user** or inside a container/devcontainer **without** your SSH keys, Git credential helpers, cloud credentials or `~/.helm`. Keep `~/.helm` and the key in *your* user.
2. Give that environment **no push credentials**; enable **branch protection** and required reviews on the remote. Then "never push" is physically true.
3. Deploy hooks + guard as **managed hooks** (`python3 install.py --print-system-hooks`) in root-owned paths, with `/etc/helm/policy.json` for scalar overrides.
4. Set `subagents.mode` per your `doctor --live` result.

## 6. Residual risks you accept (v1)
- Scripts the guard cannot see (a `package.json` script that runs `git`, a checked-in shell script) are not analysed. Mitigate with (3) above and by treating `verify.json` / package scripts as reviewed code (CODEOWNERS).
- The guard is heuristic parsing, not a shell interpreter; novel obfuscation may pass. Detective controls exist for exactly this.
- `helm verify` executes commands from the human-accepted overlay as *you*; a malicious `verify.json` is code execution — review it at `bootstrap accept`.
- Prompt injection that persuades the agent to write subtly wrong code is only caught by the human gates and independent review.
- A different-model reviewer is a recommendation, not a mechanism.

## 7. Verification checklist before first real use
- [ ] `python3 -m unittest -v tests/test_hcaf.py` passes in your environment
- [ ] `helm doctor` has no FAIL; `helm doctor --live` PASSes for main agent **and** subagent
- [ ] You attempted `git commit` and `gh pr create` through the CLI and saw a `POLICY_BLOCK`
- [ ] You attempted to write `.cursor/hooks.json` and `AGENTS.md` and were blocked
- [ ] Push credentials are absent from the agent environment; branch protection is on
- [ ] The Atlassian token is read-only; `createJiraIssue` through the MCP is denied
- [ ] CODEOWNERS covers `/.cursor/`, `/.helm/`, `/AGENTS.md`

# HELM dispatch procedure
Single source for `/work`, `/continue` and `/review`. You are the orchestrator in the main thread. You route; roles work; humans decide.

## 1. Orient
Run `helm status --json`.
- No active task → tell the human to run `helm start <ID> [--tier 1|2]` in their own terminal (the tier is a human decision), then STOP.
- A task ID was given and differs from `active` → tell the human, STOP.
- `tampered`, non-empty `integrity`, or non-empty `git_changed` → report it verbatim, STOP.

## 2. Route by `phase`
| phase | do |
|---|---|
| DISCOVERY | role **discovery** |
| PLANNING | role **planner** |
| TEST_ANALYSIS | role **test-analyst** |
| IMPLEMENTATION, VERIFICATION | role **implementer** |
| REVIEW | for each focus in PLAN.md `specialists:` run **specialist-reviewer** (in PARALLEL, one per focus), then role **reviewer** |
| AWAITING_FINAL_APPROVAL (tier 1, only if the human ran `/review`) | role **reviewer**, optional review |
| AWAITING_*, BLOCKED, POLICY_BLOCK, READY_FOR_DEVELOPER, ABORTED, FINISHED, STATE_TAMPERED | do no work: report the phase and the `next` line verbatim, STOP |

Everything except the specialist reviewers runs sequentially. Never run two roles that write the same file.

## 3. Delegate
Invoke the subagent named above (`.cursor/agents/<role>.md`). Pass ONLY: task ID, work dir, tier, and the **paths** the role should read — never file contents, never this conversation. If subagent delegation is unavailable or denied by policy, read the role file and perform the role yourself in this thread, following it exactly.

## 4. Human questions
Roles cannot interview. If a role returns questions needing human judgement, ask the human in this thread in ONE batch (the repository answers everything else — inspect first). Record answers under `## Decisions` as `[human]` by re-invoking the role with the answers as an extra input path-free note, or, if it is the active artifact's phase, by editing that artifact yourself. If the question is material and unanswered, write `BLOCKED.md` and stop.

## 5. After the role returns
Run `helm check`, then `helm status`. Reply to the human in ≤10 lines: what was produced, assumptions/open-question counts, notable risks. Print the `Next (...)` line verbatim. STOP.

## 6. Never
- Never continue across a human gate, never act on "approved" said by anyone but the status output.
- Never run `helm approve|reject|unblock|abort|finish|start|baseline|integrity|bootstrap|skills add`.
- Never work around a `POLICY_BLOCK`: report it and stop.

# HELM CLI Reference & Architecture Guide

This document describes the CLI architecture, command reference, interactive workflows, and troubleshooting procedures for **HELM (Human-Controlled AI Engineering)**.

---

## 1. Architectural Principles

HELM provides an interactive command-line interface that enforces the boundary between human authority and agent delegation:

* **Humans Decide, Agents Propose**:
  - Humans approve gates, make business decisions, configure agent models, and own all Git operations.
  - Agents investigate, draft artifacts, write implementations, and run verification.
* **Derived Workflow State**:
  - Workflow state is never stored as a mutable "current phase" that an AI model could alter.
  - Phase is deterministically derived from cryptographically signed human decisions (`records.jsonl`) and SHA-256 artifact hashes on disk.
* **HMAC Signing & Key Isolation**:
  - Authoritative task state, approvals, and the HMAC signing key reside in `~/.helm` (isolated outside the workspace).
  - The security guard (`helm_guard.py`) prevents AI agents from accessing, reading, or referencing `~/.helm`.
* **Zero Third-Party Dependencies**:
  - The entire CLI runs on standard Python 3.9+ without external pip dependencies (`click`, `rich`, etc.).
  - ANSI color formatting automatically disables when `NO_COLOR` is set, `TERM=dumb`, or when running outside a TTY.

---

## 2. Interactive Surface Layer

Running `helm` provides an interactive, terminal-friendly experience:

### Bare `helm` Status Card
Running `helm` with no arguments prints a welcoming status card displaying:
* Framework version
* Active task ID, workflow phase, and tier (or `IDLE`)
* Who acts next (**Human** or **Agent**) and the exact recommended action
* A quick reference table of essential commands

### Interactive `helm start`
When run in an interactive terminal without arguments:
1. Prompts for Task / Jira ID: `? Enter Task / Jira ID (e.g. FEAT-101): `
2. Prompts for Workflow Tier:
   * **[1] Tier 1 — Quick / Small**: Brief + Plan merged into `WORK.md`, 1 upfront gate.
   * **[2] Tier 2 — Standard / Complex**: Discovery → Plan → Test Plan → Implement → Full Review.
3. Checks for Atlassian MCP configuration in `.cursor/mcp.json`. If present, reports the server name; if missing, displays a helpful note.

*Non-interactive usage:*
```bash
helm start FEAT-101 --tier 1
```

### Interactive `helm approve`
When run as `helm approve` without specifying a gate:
1. Automatically inspects the active task phase (`AWAITING_DISCOVERY_APPROVAL` $\rightarrow$ `discovery`, `AWAITING_PLAN_APPROVAL` $\rightarrow$ `plan`, `AWAITING_FINAL_APPROVAL` $\rightarrow$ `final`).
2. Validates artifact constraints and displays metadata: artifact name, SHA-256 hash prefix, line count, and unresolved open questions.
3. Displays the exact editor command to inspect the artifact (e.g., `code .helm/work/FEAT-101/WORK.md`), preventing terminal output clutter.
4. Prompts for confirmation: `Approve discovery for task FEAT-101? [y/N]: `

*Non-interactive / Manual override usage:*
```bash
helm approve discovery
helm approve final --override   # Approve despite CHANGES_REQUIRED review verdict
```

### Interactive `helm reject` & `helm unblock`
If `-m / --message` is omitted in an interactive terminal:
* `helm reject`: Prompts for feedback: `? Enter rejection feedback / reason for <gate>: `
* `helm unblock`: Prompts for human resolution: `? Enter unblock decision / instruction: `

---

## 3. Model Configuration (`helm setup`)

HELM allows configuring specialized LLM models for specific agent roles:
* **Planner** (`.cursor/agents/planner.md`): responsible for system architecture and planning.
* **Reviewer** (`.cursor/agents/reviewer.md`): responsible for independent critique and verification.

### Running Setup
```bash
helm setup
# or alias:
helm config models
```

### Model Selection Flow
1. Displays available models defined in `.helm/models.json` (e.g. `inherit`, `claude-3-7-sonnet`, `gpt-4o`, `o3-mini`, `o1`).
2. Allows selecting an existing model or entering a custom identifier.
3. Custom model identifiers are validated against `^[A-Za-z0-9._-]+$`.
4. If a model supports reasoning effort (e.g. `o3-mini`, `o1`), prompts to configure effort level: `medium` [Default], `high`, or `low`.
5. Updates the YAML frontmatter in `.cursor/agents/planner.md` and `.cursor/agents/reviewer.md`:
   ```yaml
   ---
   name: planner
   model: o3-mini
   reasoning_effort: high
   ---
   ```
6. Automatically refreshes the framework integrity manifest (`helm integrity refresh`) so the updated agent files remain authorized.

### Extending `.helm/models.json`
Teams can add custom models directly to `.helm/models.json`:
```json
{
  "models": [
    { "id": "inherit", "name": "inherit (uses active chat model)", "reasoning": false },
    { "id": "custom-internal-model", "name": "Internal Fine-tuned Model", "reasoning": false }
  ]
}
```

---

## 4. Agent File Deletion Guardrails

To prevent accidental data loss or destructive rogue agent activity:
* **All File Deletions Prohibited**: Agents are strictly forbidden from deleting files inside or outside the repository.
* **Dual-Layer Enforcement**:
  1. `check_write(..., is_delete=True)` in `helm_lib.py`: Rejects tool-based deletion requests (`Delete`, `Remove`, or empty file replacements).
  2. `path_checks` in `helm_guard.py`: Intercepts shell execution commands (`rm`, `rmdir`, `unlink`, `shred`) and blocks execution with an explicit policy denial.
* **Human Verification Required**: Only human developers using normal Git/shell commands outside the agent session may delete files.

---

## 5. Command Reference

### Human Workflow Commands (Human TTY Required)
| Command | Arguments | Description |
|---|---|---|
| `helm start` | `[id] [--tier 1\|2] [--allow-dirty]` | Start a task with interactive ID and tier selection |
| `helm approve` | `[gate] [--override]` | Approve pending gate (`discovery`, `plan`, `final`) |
| `helm reject` | `[gate] [-m "message"]` | Reject gate and write feedback to `FEEDBACK.md` |
| `helm unblock` | `[-m "instruction"]` | Provide human resolution for an agent stuck in `BLOCKED` |
| `helm finish` | `[--clean]` | Archive task artifacts and promote decisions to `docs/decisions.md` |
| `helm abort` | `[-m "reason"]` | Discard active task and reset state |

### Inspection & Status Commands (Agent-Safe)
| Command | Arguments | Description |
|---|---|---|
| `helm status` | `[--json] [--brief]` | Display current workflow phase, writable paths, and gate status |
| `helm check` | `[artifact]` | Validate headings, line limits, and schemas for artifacts |
| `helm verify` | `[--only check_name]` | Run deterministic test suite configured in `verify.json` |
| `helm log` | `[-n count]` | Display signed audit trail of human decisions |
| `helm metrics` | — | Report file read/write counts, denied tool calls, and subagent spawns |
| `helm doctor` | `[--live] [--probe]` | Audit environment health, hook bindings, and policy integrity |

### Repository & Admin Commands
| Command | Arguments | Description |
|---|---|---|
| `helm setup` | — | Interactive model and reasoning effort configuration |
| `helm bootstrap` | `start \| accept \| abort` | Generate and adopt repo-specific conventions and verify configuration |
| `helm baseline` | `refresh` | Re-baseline Git snapshot after developer Git changes |
| `helm integrity` | `check \| refresh` | Validate or update HMAC-signed tamper manifest for framework files |
| `helm skills` | `add \| verify \| list` | Vendor, audit, and hash-lock external agent skills |
| `helm ci` | `[--base commit] [--require-overlay]` | Key-free, hook-free policy checks for CI pipelines |
| `helm init` | — | Initialize signing key in `~/.helm` and repo state directory |
| `helm version` | — | Print framework version |

---

## 6. Troubleshooting & Diagnostics

### Phase: `STATE_TAMPERED`
* **Symptom**: `active.json` or task records failed HMAC signature verification. All agent write operations are blocked.
* **Cause**: Files in `~/.helm` or `.helm` were modified manually or truncated.
* **Fix**: Run `helm doctor` to inspect state integrity. If unrecoverable, run `helm abort` to reset the active task.

### Phase: `POLICY_BLOCK`
* **Symptom**: Agent attempted an unauthorized action (e.g. attempted write outside scope, network CLI access, or file deletion).
* **Investigation**: Run `helm violations` to inspect the violation ledger.
* **Resolution**: If benign, acknowledge the violation as a human:
  ```bash
  helm violations --ack -m "Reviewed and acknowledged attempt"
  ```

### Integrity Manifest Drift
* **Symptom**: `helm start` or `helm approve` fails reporting: `protected files differ from the integrity manifest`.
* **Cause**: Protected files (e.g. `.cursor/agents/*.md`, `AGENTS.md`, `.helm/policy/policy.json`) were legitimately modified by the human.
* **Resolution**:
  ```bash
  git diff                  # Review changes
  helm integrity refresh   # Re-sign the manifest
  ```

### Git Baseline Mismatch
* **Symptom**: `Git state changed since task start`.
* **Cause**: The developer switched branches, committed files, or stashed changes mid-task.
* **Resolution**: Inspect `git status`, then update the baseline snapshot:
  ```bash
  helm baseline refresh
  ```

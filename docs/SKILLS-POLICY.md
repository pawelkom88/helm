# Skills Policy — supply chain for agent instructions

A skill is **trusted instructions** (and sometimes scripts). It outranks Jira and Confluence text in the agent's authority, so a poisoned skill is worse than a poisoned ticket. Treat skills as code dependencies.

## Rules
1. **Vendor, never install at runtime.** No `npx skills add …` into a working repo. Review a pinned commit, then vendor it with `helm skills add`.
2. **Markdown-only by default.** `SKILL.md`, references, text/JSON/YAML. Any script, binary or executable asset needs `--allow-scripts` *after* a line-by-line review, and a second reviewer.
3. **Pin and hash.** `.helm/skills.lock.json` stores source URL, commit SHA, licence, reviewer, approval date, scope, file list and a SHA-256 over the whole folder. `helm skills verify` (also run by `helm doctor` and your CI) fails on any change.
4. **One location.** Vendored skills live in `.cursor/skills/<name>/`. (A reported Cursor bug ignores `disable-model-invocation: true` under `.agents/skills/`; keep user-invoked workflow skills in `.cursor/skills/` and test.)
5. **Small set.** Every discovered skill's name + description sits in the agent's context from the first token. Cap at ~10–12. Remove what the plan never lists.
6. **Skills are not roles.** Roles (agents) say *who owns a stage*; skills say *how to do a kind of work*. A planner lists the skills the implementer needs in `PLAN.md → Required Skills`; the implementer reads exactly those files. Skills are matched by description and cannot be "handed" to a subagent reliably — naming the path is the contract.
7. **Updates are PRs.** Re-vendor from a new reviewed commit; the diff of the skill folder is what the reviewer reads. No tracking of moving branches.
8. **Unknown skills are flagged.** Cursor loads skills from project, nested and *user-level* directories and there is no CLI switch to disable that. `helm doctor` reports any discovered skill that is not in the lock (including `~/.cursor/skills`, `~/.claude/skills`, `~/.agents/skills`, `~/.codex/skills`). Ask platform/IT whether your plan can restrict plugins/marketplaces centrally.
9. **Marketplace plugins bundle skills.** The Atlassian MCP plugin for Cursor ships skills; prefer configuring the MCP server by hand (`docs/atlassian-mcp.example.json`) so you control exactly what loads.

## Intake checklist (per skill)
- [ ] Source repo, **commit SHA**, licence recorded (MIT/Apache/other — check redistribution)
- [ ] Read *every* file, including references and examples, not just `SKILL.md`
- [ ] No instructions to fetch/execute remote content, change git config, read credentials, or "ignore previous instructions"
- [ ] No scripts (or reviewed + justified), no network access, no package installs
- [ ] Description is narrow (won't auto-trigger on unrelated work)
- [ ] Scope noted (which roles/stages use it); added to `Required Skills` guidance in `.helm/repo/conventions.md` if relevant
- [ ] Second person signs off if it contains scripts or touches security/testing policy

```bash
helm skills add ./vendor-candidate/react-best-practices \
  --name react-best-practices --source https://github.com/ORG/REPO \
  --sha <40-char-commit> --license MIT --reviewer "Your Name" --scope "implementer, reviewer"
# prints risky-pattern hits for you to read, asks you to type the skill name, vendors + locks
git add .cursor/skills .helm/skills.lock.json && git commit
```

## Candidate sources (NOT vetted by this bundle — you must review them)
| Candidate | Fit | Notes |
|---|---|---|
| Matt Pocock's engineering skills | planning / alignment (`grill-with-docs`-style interviewing, TDD, diagnosing) | Workflow skills are intentionally *user-invoked* (`disable-model-invocation`). `grill-with-docs` **writes** glossary/ADR docs — run it only in the main thread, human-invoked, and review its diffs; do not run it inside a subagent. |
| Vercel React best-practices | implementer / reviewer (React, performance) | Large rule sets: vendor only the rules relevant to your stack to protect the context budget. |
| TanStack Query best practices | implementer / reviewer (server state) | Check it matches your installed major version. |
| Your company skills (frontend, component library, testing, architecture) | the highest value | Author these *from* the bootstrap output; they should point at the component library's real paths, not duplicate component source. |

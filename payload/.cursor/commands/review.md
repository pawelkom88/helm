Run the independent review stage of the active HELM task.

Read `.helm/templates/DISPATCH.md` and follow it, but only act if `phase` is `REVIEW` (or `AWAITING_FINAL_APPROVAL` on a tier-1 task, where review is optional). In any other phase report the phase and the `next` line and stop. Use the role files `.cursor/agents/specialist-reviewer.md` and `.cursor/agents/reviewer.md`.

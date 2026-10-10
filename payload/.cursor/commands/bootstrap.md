Build the repo-specific HELM layer (run once per repository, re-run when `helm status` says the overlay is stale).

1. Run `helm status --json`. If `phase` is not `BOOTSTRAP`, tell me to run `helm bootstrap start` in a terminal and stop.
2. Invoke the `bootstrapper` subagent (`.cursor/agents/bootstrapper.md`). Pass no content. If subagents are unavailable or denied, read that file and perform the role yourself.
3. Relay its summary and its **Unknowns / questions** to me. Ask me the questions that need human judgement in one batch and fold my answers into the proposal files.
4. Tell me to read `.helm/bootstrap/proposal/` and run `helm bootstrap accept`. Stop. You cannot accept it.

@AGENTS.md

# Claude Code enforcement

The rules above are enforced in this repository, not only described:

- `.claude/hooks/authority_guard.py` (PreToolUse) reads
  `policies/agent-authority.yaml`. The main conversation is the maker and may
  write only its `writable_paths`. The `checker` subagent writes nothing and
  runs only the verifier and read-only Git commands.
- `.claude/settings.json` denies `git add`, `git commit`, push, merge,
  network tools, bootstrap, Evidence collection, and loop reset. The human
  owner stages and commits.
- The Bash sandbox (bubblewrap, WSL2/Linux) blocks writes to Spec, task,
  policy, script, and config paths and has no network access. Unsandboxed
  retries are disabled.

When a guard blocks you, do not look for a way around it. Report what you
needed and why; the human owner decides.

# Workflow skills

- `/task-new "<goal>"`: draft a task contract for the human to approve.
- `/task-run TB-LAB-NNN [checker-base]`: maker flow with
  `scripts/bounded-loop.sh step TB-LAB-NNN`.
- `/check TB-LAB-NNN [base]`: read-only checker validation.

---
description: Run one approved task end to end as the maker, using the bounded loop as the gate and the checker subagent for acceptance.
argument-hint: TB-LAB-NNN [checker-base]
disable-model-invocation: true
---

Run task $0 as the maker. Follow `AGENTS.md`; this skill only fixes the order.
A second argument, if given, is the checker base: the human owner passes it
when the contract was amended after approval. Existing uncommitted changes in
the allowed scope are earlier work on this same task; build on them.

1. Confirm `tasks/$0.md` exists and `tasks/queue.yaml` lists $0 as `ready`.
   If not, stop: only the human owner approves tasks.
2. Read the task, the linked Spec section, `context/context-manifest.md`, and
   `policies/agent-authority.yaml`.
3. Run `scripts/bounded-loop.sh status`. If it shows `retrying`, `escalated`,
   `blocked`, or `aborted` for a different task, stop: the human owner must
   resolve that task first, and you may not reset the loop.
4. Run `scripts/verify.sh fast`. Exit 2 means fix the environment, not the code;
   stop and report. Exit 1 is acceptable only when every failing test is the
   target of this task; otherwise stop and report.
5. Implement inside the task's Allowed scope only. Write tests first for each TAC.
6. Run `scripts/bounded-loop.sh step $0`. The loop binds to this task and
   starts fresh automatically when the previous task is `done`:
   - exit 0: confirm a new `evidence/loop-runs/attempt-*` directory was
     created by this step, then continue to step 7. No new directory means
     the gate did not run; stop and report.
   - exit 1: read the newest `evidence/loop-runs/*/verifier.out`, change the
     code, and step again.
   - exit 2: stop. Report the state from `scripts/bounded-loop.sh status` and
     hand back to the human owner. Do not reset the loop yourself.
7. Run `scripts/verify.sh full`.
8. Delegate to the `checker` subagent with the task id and a base: `$1` if
   it was given, otherwise the approval commit from
   `git log --diff-filter=A --format=%h -- tasks/$0.md`.
9. Report: status, changed files, TAC/SAC mapping, commands with exit codes,
   loop evidence paths, the checker decision, and known gaps. Propose a commit
   message, but let the human decide whether to commit. If the test count or
   coverage changed, say so: the human owner updates the README baseline after
   the checker passes; it is not part of the maker's diff.

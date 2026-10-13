---
description: Run one approved task end to end as the maker, using the bounded loop as the gate and the checker subagent for acceptance.
argument-hint: TB-LAB-NNN
disable-model-invocation: true
---

Run task $0 as the maker. Follow `AGENTS.md`; this skill only fixes the order.

1. Confirm `tasks/$0.md` exists and `tasks/queue.yaml` lists $0 as `ready`.
   If not, stop: only the human owner approves tasks.
2. Read the task, the linked Spec section, `context/context-manifest.md`, and
   `policies/agent-authority.yaml`.
3. Run `scripts/verify.sh fast`. Exit 2 means fix the environment, not the code;
   stop and report.
4. Implement inside the task's Allowed scope only. Write tests first for each TAC.
5. Run `scripts/bounded-loop.sh step`:
   - exit 0: continue to step 6.
   - exit 1: read the newest `evidence/loop-runs/*/verifier.out`, change the
     code, and step again.
   - exit 2: stop. Report the state from `scripts/bounded-loop.sh status` and
     hand back to the human owner. Do not reset the loop yourself.
6. Run `scripts/verify.sh full`.
7. Delegate to the `checker` subagent with the task id and base `main`.
8. Report: status, changed files, TAC/SAC mapping, commands with exit codes,
   loop evidence paths, the checker decision, and known gaps. Propose a commit
   message, but let the human decide whether to commit.

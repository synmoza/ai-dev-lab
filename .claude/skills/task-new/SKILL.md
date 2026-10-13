---
description: Draft a new task contract from tasks/TEMPLATE.md for the human owner to review and approve.
argument-hint: "<one-line goal>"
disable-model-invocation: true
---

Draft a new task for this goal: $ARGUMENTS

The authority guard blocks you from writing `tasks/`, `specs/`, and policies,
on purpose: approving work is the human owner's decision. So draft, do not file.

1. Find the next unused `TB-LAB-NNN` from `tasks/queue.yaml` and `tasks/`.
2. Read `tasks/TEMPLATE.md` and `specs/task-board.md`.
3. Decide whether the goal needs a new or changed SAC. If it does, draft the
   SAC text separately and say so plainly: the Spec change comes first.
4. Print, in the chat, three blocks the human can paste:
   - the full `tasks/TB-LAB-NNN.md`, with TAC items that are each checkable
     by a test, and the TAC to SAC table;
   - the SAC lines to add to `specs/task-board.md`, if any;
   - the queue entry for `tasks/queue.yaml`.
5. List open questions that need a human decision before approval.

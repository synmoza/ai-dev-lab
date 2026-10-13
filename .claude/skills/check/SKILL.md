---
description: Ask the read-only checker subagent to validate a task against its contract and the Spec.
argument-hint: TB-LAB-NNN [base-ref]
disable-model-invocation: true
---

Delegate to the `checker` subagent. Pass it task `$0` and base `$1`. If no
base was given, pass the task's approval commit: the commit that added
`tasks/$0.md`, found with
`git log --diff-filter=A --format=%h -- tasks/$0.md`. That keeps the human
owner's approval commit (Spec, task, queue) out of the maker's scope check.
Do not run the checks yourself and do not edit anything. Relay the checker's structured result verbatim, then add one
line on what the human owner should decide next.

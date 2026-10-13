---
description: Ask the read-only checker subagent to validate a task against its contract and the Spec.
argument-hint: TB-LAB-NNN [base-ref]
disable-model-invocation: true
---

Delegate to the `checker` subagent. Pass it task `$0` and base `$1`; if no
base was given, use `main`. Do not run the checks yourself and do not
edit anything. Relay the checker's structured result verbatim, then add one
line on what the human owner should decide next.

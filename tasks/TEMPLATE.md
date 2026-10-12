# Task TB-LAB-NNN｜<一句話說明要交付的行為>

<!--
使用方式：
1. 複製成 `tasks/TB-LAB-NNN.md`，NNN 取下一個未使用的編號。
2. 若需要新的產品行為，先在 `specs/task-board.md` 新增或修改 SAC，
   Spec 變更屬於人工決策，不交給 Agent。
3. 在 `tasks/queue.yaml` 加一筆 `{"task_id", "contract", "status": "ready",
   "depends_on"}`。
4. 由 human owner commit 上述檔案；commit 即代表核准這張 task。
刪掉本註解後再 commit。
-->

## Goal

<完成後，使用者可以觀察到什麼行為？用可驗證的句子描述。>

## Context pointers

- `AGENTS.md`
- `specs/task-board.md`
- `context/context-manifest.md`
- `policies/agent-authority.yaml`

## Scope

- Allowed: <例如 `src/task_board/`、`tests/`、本 task 的 Evidence。>
- Forbidden: <明確列出不可碰的路徑與功能，例如 Spec、policy、網路、資料庫。>

## Constraints

- Python 3.12+；exact tool profile 由
  `constraints/runtime-profile.txt` 定義。
- Runtime 只用標準庫。
- <本 task 特有的技術限制。>

## Acceptance and Evidence

- TAC-01：<可由測試或命令驗證的驗收條件。>
- TAC-02：<…>
- TAC-NN：`scripts/verify.sh full` 通過並達 80% coverage。

| Task acceptance | Spec／gate 對應 |
|---|---|
| TAC-01 | SAC-<編號> |
| TAC-NN | Task-only verification gate |

Evidence：pytest output、coverage、diff、commit、exit code 與 known gaps。

## Authority

- Agent read/write scope：依 `policies/agent-authority.yaml` 的 maker／checker 角色。
- Execute：`scripts/verify.sh`、`scripts/guard-command.sh` allowlist、
  `scripts/bounded-loop.sh step`。
- Merge、push、deploy、外部訊息：不在授權 scope，由 human owner 執行。

## Stop and escalate

- Acceptance 需要改動 `specs/task-board.md` 或 policy。
- 需要 runtime dependency、network、credential 或 production data。
- Baseline 先失敗，或 verifier 回 exit 2。
- `bounded-loop.sh step` 進入 `escalated` 或 `blocked`。

## Return

回報 status、changed files、TAC／SAC 對應、commands／exit codes、Evidence path、risks／gaps。

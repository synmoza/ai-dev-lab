# Task TB-LAB-004｜讓 bounded loop 綁定任務，換任務自動重新開始

## Goal

`scripts/bounded-loop.sh step TB-LAB-NNN` 會記住目前是哪張任務；換了任務就自動
從 `ready` 開始，不再需要 human owner 在核准時手動 reset。

## Context pointers

- `AGENTS.md`
- `specs/task-board.md`（Evidence plan：loop 成功與失敗路徑）
- `.ai-loop/loop-contract.yaml`
- 既有實作：`src/task_board/loop.py`、`tests/test_loop.py`

## Scope

- Allowed: `src/task_board/loop.py`、`tests/test_loop.py`、本 task 的 Evidence。
- Forbidden: `scripts/`、`.claude/`、`specs/`、`tasks/`、`policies/`、
  `.ai-loop/loop-contract.yaml`、其他測試檔；不得改變 `run`、`reset`、`status`
  的現有行為，不得刪改既有 loop 測試。

## Constraints

- Runtime 只用標準庫；狀態檔、事件、`result.json` 仍為 JSON，狀態檔仍以
  atomic replace 寫入。
- 任務 ID 格式為 `TB-LAB-` 加三位數字；只檢查 `tasks/<ID>.md` 是否存在，
  不讀 `tasks/queue.yaml`。
- 證據目錄名稱維持 `attempt-NNN-<timestamp>`；任務 ID 只寫在檔案內容。
- `step` 的任務 ID 為選填參數；不帶 ID 時行為完全不變。

## Acceptance and Evidence

- TAC-01：狀態記錄的任務與 `step <ID>` 指定的不同，或狀態檔不存在時，從
  attempt 0 重新開始，追加一筆 reason 為 `new-task-started` 的事件，再跑一輪；
  既有事件與證據全部保留，事件序號連續。
- TAC-02：同一張任務已是 `done` 時，`step <ID>` 回 0，不新增一輪、不新增證據。
- TAC-03：同一張任務是 `escalated` 或 `blocked` 時，`step <ID>` 仍回 2，
  不自動重新開始。
- TAC-04：狀態檔、`events.jsonl` 的新事件、每輪 `result.json` 都記錄 `task_id`。
- TAC-05：沒有 `task_id` 欄位的舊格式狀態檔仍可讀取，視為未綁定任務；
  `step <ID>` 會依 TAC-01 重新開始。
- TAC-06：ID 格式不符或 `tasks/<ID>.md` 不存在時，回 exit 2，狀態檔與
  `events.jsonl` 都不變。
- TAC-07：不帶 ID 的 `step`、`run`、`reset`、`status` 行為不變；既有
  `tests/test_loop.py` 測試不修改也全部通過。
- TAC-08：`scripts/verify.sh full` 通過並達 80% coverage；checker 在 sandbox
  內執行也 exit 0。

| Task acceptance | Spec／gate 對應 |
|---|---|
| TAC-01 | Spec Evidence plan（loop 成功與失敗路徑） |
| TAC-02 | Spec Evidence plan |
| TAC-03 | Spec Evidence plan；`same_failure_limit` 的 escalate 不得被繞過 |
| TAC-04 | Spec Evidence plan |
| TAC-05 | Spec Evidence plan；本機狀態相容 |
| TAC-06 | Spec Evidence plan；exit 2 慣例 |
| TAC-07 | 既有行為不得退化 |
| TAC-08 | Task-only verification gate |

本 task 不新增或修改產品行為 SAC。

Evidence：pytest output、coverage、diff、commit、exit code、checker decision 與 known gaps。

Known gap（human owner 已接受）：`.ai-loop/loop-contract.yaml` 的
`allowed_tasks` 仍為 `["TB-LAB-001"]`，loop 不讀這個欄位；之後另行決定刪除或啟用。

## Authority

- Agent read/write scope：依 `policies/agent-authority.yaml` 的 maker／checker 角色。
- Execute：`scripts/verify.sh`、`scripts/guard-command.sh` allowlist、
  `scripts/bounded-loop.sh step`（本 task 實作期間使用不帶 ID 的 step）。
- 核准 commit 已由 human owner 讓 `scripts/bounded-loop.sh` 轉送全部參數，
  並在 `.claude/settings.json` 允許 `step TB-LAB-*`。
- 流程文件（`/task-run`、`AGENTS.md`、`tasks/TEMPLATE.md`）改用
  `step TB-LAB-NNN` 由 human owner 在 checker pass 後處理，不在本 task 範圍。
- Merge、push、deploy、外部訊息：不在授權 scope，由 human owner 執行。

## Stop and escalate

- 修正需要改動 `scripts/`、`.claude/`、loop contract 或其他測試檔。
- 需要修改或刪除既有 loop 測試才能通過。
- Baseline verifier 回 exit 2；或回 exit 1，但失敗的不是本 task 要修的目標。
- 任一後續 verifier 回 exit 2。
- `bounded-loop.sh step` 進入 `escalated` 或 `blocked`。

## Return

回報 status、changed files、TAC 對應、commands／exit codes、Evidence path、risks／gaps。

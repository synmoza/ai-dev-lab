# Task TB-LAB-003｜讓 evidence collector 測試在 Claude Code sandbox 內也能通過

## Goal

`tests/test_scripts.py::test_evidence_collector_rejects_tracked_dirty_source`
只複製 Git 追蹤的檔案建立隔離副本，因此不論 repo 根目錄有沒有未追蹤或無法讀取
的檔案（例如 Bash sandbox 的 mount 佔位檔），`scripts/verify.sh full` 在 sandbox
內外都得到相同結果。

## Context pointers

- `AGENTS.md`
- `specs/task-board.md`（Evidence plan：隔離 copy 的 evidence 成功與失敗路徑）
- `scripts/collect-evidence.sh`（被測對象，本 task 不修改）
- `.claude/agents/checker.md`（sandbox 佔位檔說明）

## Scope

- Allowed: `tests/test_scripts.py`、本 task 的 Evidence。
- Forbidden: `scripts/`、`src/`、`specs/`、`policies/`、`.claude/`、
  `.gitignore`、其他測試檔；不得刪除、skip 或 xfail 既有測試，不得放寬既有斷言。

## Constraints

- 只用標準庫與 `git` 指令；複製來源以 `git ls-files` 列出的檔案為準。
- 複製邏輯抽成 test helper，並可對任意來源 repo 使用（方便單獨測試）。
- 測試不得在 repo 工作目錄內建立檔案；所有暫存資料放在 `tmp_path`。

## Acceptance and Evidence

- TAC-01：collector 測試的隔離副本只含來源 repo `git ls-files` 列出的檔案；
  未追蹤檔案不會被讀取或複製。
- TAC-02：新增 helper 測試：在 `tmp_path` 建立含一個已追蹤檔案、一個未追蹤
  且權限為 000 的檔案的 Git repo，helper 複製成功、副本只含已追蹤檔案、不拋例外。
- TAC-03：collector 測試原有的四項斷言（exit 2、status.txt 非空、change.diff
  非空、verifier.out 含 `verification not run`）保持不變且通過。
- TAC-04：`scripts/verify.sh full` 在 sandbox 外與 Claude Code sandbox session
  內（checker 執行）都 exit 0，並達 80% coverage。
- TAC-05：diff 只包含 `tests/test_scripts.py`。

| Task acceptance | Spec／gate 對應 |
|---|---|
| TAC-01 | Spec Evidence plan（隔離 copy 的 evidence 失敗路徑） |
| TAC-02 | Spec Evidence plan |
| TAC-03 | Spec Evidence plan；既有行為不得退化 |
| TAC-04 | Task-only verification gate |
| TAC-05 | Task-only scope gate |

本 task 不新增或修改產品行為 SAC。

Evidence：pytest output、coverage、diff、commit、exit code、checker decision 與 known gaps。

Known gap（human owner 已接受）：TAC-02 以權限 000 模擬無法讀取的檔案；
以 root 執行測試時 000 仍可讀，該測試只能證明「不複製」，不能證明「不讀取」。
CI 與 lab 以一般使用者執行。

## Authority

- Agent read/write scope：依 `policies/agent-authority.yaml` 的 maker／checker 角色。
- Execute：`scripts/verify.sh`、`scripts/guard-command.sh` allowlist、
  `scripts/bounded-loop.sh step`。
- Merge、push、deploy、外部訊息：不在授權 scope，由 human owner 執行。

## Stop and escalate

- 修正需要改動 `scripts/`、`.gitignore`、sandbox 設定或其他測試檔。
- 需要 skip、xfail 或放寬既有斷言才能通過。
- Baseline 先失敗，或 verifier 回 exit 2。
- `bounded-loop.sh step` 進入 `escalated` 或 `blocked`。

## Return

回報 status、changed files、TAC 對應、commands／exit codes、Evidence path、risks／gaps。

# Task TB-LAB-002｜新增 delete 指令，刪除指定 task

## Goal

使用者執行 `task-board delete TB-NNN` 後，該 task 從本機 JSON store 移除，
其餘 task 不變；未知 ID 回 exit 2 且 store 不被改寫。

## Context pointers

- `AGENTS.md`
- `specs/task-board.md`（SAC-10、SAC-11，以及既有 SAC-04、SAC-06、SAC-07）
- `context/context-manifest.md`
- `policies/agent-authority.yaml`
- 既有實作：`src/task_board/cli.py`、`src/task_board/service.py`

## Scope

- Allowed: `src/task_board/cli.py`、`src/task_board/service.py`、
  `src/task_board/domain.py`（僅限需要時）、`tests/`、本 task 的 Evidence。
- Forbidden: `specs/`、`policies/`、`scripts/`、`tasks/`、store 格式變更
  （root 仍為 JSON array）、確認提示／互動輸入、批次刪除、undo／trash、
  網路、資料庫。

## Constraints

- Python 3.12+；exact tool profile 由
  `constraints/runtime-profile.txt` 定義。
- Runtime 只用標準庫。
- 刪除沿用 `TaskRepository.save` 的 atomic replace，不另寫檔案路徑。
- 預期錯誤以 `TaskBoardError` 子類回報，CLI 回 exit 2；不吞錯誤。
- 一次只刪一個 ID；不接受 glob、範圍或多個參數。

## Acceptance and Evidence

- TAC-01：`delete TB-002` 在含 TB-001..TB-003 的 store 上回 exit 0，
  stdout 為 `deleted TB-002 [<status>] <priority> | <title>`，
  之後 `list` 只剩 TB-001、TB-003，且其欄位與刪除前完全相同。
- TAC-02：todo 與 done 狀態的 task 都可刪除。
- TAC-03：`delete TB-999`（不存在）回 exit 2，stderr 含
  `task not found: TB-999`，store 檔案 bytes 與刪除前相同。
- TAC-04：store 不存在時 `delete TB-001` 回 exit 2，且不建立 store 檔案。
- TAC-05：corrupt store（壞 JSON 或非 array root）時 `delete` 回 exit 2，
  原檔內容不被覆寫。
- TAC-06：刪除後再 `add`，新 ID 為「剩餘 task 最大編號 + 1」；
  刪除中間的 ID 不會被重新分配（例：刪 TB-002 後 add 得到 TB-004）。
- TAC-07：ID 參數 `'$(touch pwned)'` 經
  `scripts/guard-command.sh task-board delete ...` 只被當作文字，
  回 exit 2 task not found，且測試的工作目錄中不存在 `pwned` 檔案。
- TAC-08：`scripts/verify.sh full` 通過並達 80% coverage。

`TAC-*` 是這張 task 的驗收編號；`SAC-*` 是
`specs/task-board.md` 的產品行為編號。兩者不能只靠尾碼推定對應：

| Task acceptance | Spec／gate 對應 |
|---|---|
| TAC-01 | SAC-10 |
| TAC-02 | SAC-10 |
| TAC-03 | SAC-10、SAC-04（未知 ID exit 2 的既有慣例） |
| TAC-04 | SAC-10 |
| TAC-05 | SAC-05 |
| TAC-06 | SAC-11、SAC-02 |
| TAC-07 | SAC-07 |
| TAC-08 | Task-only verification gate；對應 Spec 的 Evidence plan，不是產品行為 SAC |

Evidence：pytest output、coverage、diff、commit、exit code 與 known gaps。

Known gap（human owner 已接受）：刪除最大編號後，下一次 add 可能重用該 ID
（SAC-11）。永不重用 ID 需另立 task 變更 store 格式。

## Authority

- Agent read/write scope：依 `policies/agent-authority.yaml` 的 maker／checker 角色。
- Execute：`scripts/verify.sh`、`scripts/guard-command.sh` allowlist、
  `scripts/bounded-loop.sh step`。
- 這裡的 delete 指產品功能；Agent 本身仍不得刪除 repo 檔案或 Runtime
  store 以外的資料。測試只能在 `tmp_path` 的 store 上執行 delete。
- Merge、push、deploy、外部訊息：不在授權 scope，由 human owner 執行。

## Stop and escalate

- Acceptance 需要改動 `specs/task-board.md`、store 格式或 policy。
- 需要 runtime dependency、network、credential 或 production data。
- Baseline 先失敗，或 verifier 回 exit 2。
- `bounded-loop.sh step` 進入 `escalated` 或 `blocked`。

## Return

回報 status、changed files、TAC／SAC 對應、commands／exit codes、Evidence path、risks／gaps。

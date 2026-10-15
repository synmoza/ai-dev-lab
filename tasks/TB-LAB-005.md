# Task TB-LAB-005｜README 不再寫死測試數；CI 檢查腳本執行權限

## Goal

`tests/test_artifacts.py` 不再要求 README 寫出特定測試數與 coverage，讓每張
task 不必為了更新數字多一個 commit；同時新增測試，在 `scripts/*.sh` 失去執行
權限時讓 verifier 與 CI 失敗。

## Context pointers

- `AGENTS.md`
- `specs/task-board.md`（Evidence plan）
- `tests/test_artifacts.py`（被修改的測試）
- `scripts/`（被檢查的對象，本 task 不修改）

## Scope

- Allowed: `tests/test_artifacts.py`、本 task 的 Evidence。
- Forbidden: 其他所有路徑；不得刪除或放寬 TAC-01 指定以外的任何既有斷言，
  不得 skip 或 xfail 測試。

## Constraints

- 只用標準庫與 `git` 指令。
- 權限檢查以 Git index 記錄的 mode 為準（`git ls-files -s`），不看工作目錄的
  檔案系統權限，因此在 Windows 端編輯後 CI 一樣能抓到。
- 檢查邏輯抽成可對任意 repo 使用的 helper，測試資料放在 `tmp_path`。

## Acceptance and Evidence

- TAC-01：`test_readme_discloses_pedagogical_boundary` 不再斷言測試數與
  coverage 數字；其他斷言（`不是`、`production`、`GitHub Actions`、
  `Windows PowerShell`、`releases/tag/v1.0.0`、版本 `1.0.0`）全部保留。
- TAC-02：新增測試：本 repo `git ls-files -s` 列出的每個 `scripts/*.sh`
  mode 都是 `100755`。
- TAC-03：新增測試：在 `tmp_path` 建立含 mode `100644` 的 `scripts/*.sh` 的
  Git repo，helper 回報該檔案；全部為 `100755` 時回報為空。
- TAC-04：除 TAC-01 指定的兩行外，`git diff` 中沒有任何既有斷言被刪除或放寬。
- TAC-05：`scripts/verify.sh full` 通過並達 80% coverage；checker 在 sandbox
  內執行也 exit 0。
- TAC-06：diff 只包含 `tests/test_artifacts.py`。

| Task acceptance | Spec／gate 對應 |
|---|---|
| TAC-01 | Spec Evidence plan；README 數字改以 CI 與 evidence manifest 為準 |
| TAC-02 | Spec Evidence plan（scripts 可執行） |
| TAC-03 | Spec Evidence plan；證明 TAC-02 會失敗 |
| TAC-04 | 既有斷言不得退化 |
| TAC-05 | Task-only verification gate |
| TAC-06 | Task-only scope gate |

本 task 不新增或修改產品行為 SAC。

## Abuse cases

- 藉「拿掉測試數斷言」順便刪掉或放寬其他斷言 → TAC-04，checker 逐行比對
  被刪除的行。
- 權限測試寫成永遠通過（例如只檢查存在、或讀工作目錄權限）→ TAC-03 要求證明
  它會對 `100644` 失敗。

Evidence：pytest output、coverage、diff、commit、exit code、checker decision 與 known gaps。

Known gap（human owner 已接受）：合約審查員 subagent（框架規劃 C1）尚未建立，
本合約由 human owner 與 Windows 端 Claude 手動審查。

## Human owner changes in the approval commit

- `.ai-loop/loop-contract.yaml`：刪除未使用的 `allowed_tasks`。
- `.claude/settings.json`：`git add`、`git commit` 由 ask 改為 deny；
  `tests/test_claude_config.py` 對應斷言同步修改，`CLAUDE.md` 與 README
  的強制層說明同步修改。
- `.gitignore`：忽略 sandbox 在 repo 根目錄掛載的佔位檔。
- README 的「已驗證基線」段落在 checker pass 後由 human owner 改寫，
  不在本 task 範圍。

## Authority

- Agent read/write scope：依 `policies/agent-authority.yaml` 的 maker／checker 角色。
- Execute：`scripts/verify.sh`、`scripts/guard-command.sh` allowlist、
  `scripts/bounded-loop.sh step TB-LAB-005`。
- `git add`、`git commit`、merge、push、deploy、外部訊息：不在授權 scope，
  由 human owner 執行。

## Stop and escalate

- 修正需要改動 `tests/test_artifacts.py` 以外的檔案。
- 需要刪除或放寬 TAC-01 以外的斷言才能通過。
- Baseline verifier 回 exit 2；或回 exit 1，但失敗的不是本 task 要修的目標。
- 任一後續 verifier 回 exit 2。
- `bounded-loop.sh step` 進入 `escalated` 或 `blocked`，或拒絕切換任務。

## Return

回報 status、changed files、TAC 對應、commands／exit codes、Evidence path、risks／gaps。

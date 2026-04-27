# Sprint-18 計画書

**期間**: 2026-04-26
**ブランチ**: feat/sprint-18
**ゴール**: Sprint-17 後処理（Issue 重複整理・lesson status 更新・hook スモークテスト・pm-learned-rules.md コミット）

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-17 全5タスク DONE・PR #98 マージ済み）
- [x] 計画重複タスク: なし
- [x] DECISIONS.md 反映: Sprint-17 の成功パターン（_queue.json 状態記録によるレート制限耐性）を確認。次スプリントへの推奨（Issue #99/#100 重複整理）を sprint-18 に反映。
- [x] pm-learned-rules.md 反映: sprint-17-tooling-001（フック実装権限事前登録）・sprint-17-reliability-001（_queue.json 状態記録）を確認。sprint-17-tooling-001 は今スプリントでアクション完了（settings.json に権限追加済み・Issue #100 オープン中）。
- [x] Riku 担当 L タスク: 0件（Riku 担当タスクなし）

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | qa_mode |
|---|------|----------|------|------|------------|---------|
| 1 | lesson-dedup-close | Issue #99/#100 重複クローズ + lesson status 更新 | Yuki | なし | S | — |
| 2 | hook-smoke-test | TaskCompleted hook 実動作確認 | Sora | なし | S | — |
| 3 | pm-rules-update | pm-learned-rules.md 未コミット変更確定 | Yuki | なし | S | — |
| 4 | sprint18-qa | Sprint-18 最終QA | Sora | #1 #2 #3 | S | — |

**合計ポイント: 4 pt**（S×4=4）
**Riku 担当 L タスク**: 0件（制限 1件/sprint に適合）

### 並列化

- lesson-dedup-close・hook-smoke-test・pm-rules-update は同時実行可能（phase-1）
- sprint18-qa は phase-1 全完了後（phase-2）

---

## 変更ファイル予定

| ファイル | 変更種別 |
|---------|---------|
| `.claude/agents/pm-learned-rules.md` | 未コミット変更のコミット + 最終更新日更新 |
| `.claude/_queue.json` | sprint-18 タスク状態記録 |
| `~/.claude/_lessons.json` | sprint-17-tooling-001 status を implemented に更新 |
| `docs/sprints/sprint-18.md` | 本ファイル（新規作成） |

---

## 完了条件

- [ ] Issue #99 が CLOSED
- [ ] `~/.claude/_lessons.json` の `agent-crew-sprint-17-tooling-001` の status が `implemented`
- [ ] `.claude/_signals.jsonl` に sprint-17 の `task_completed` イベントが存在する
- [ ] `pm-learned-rules.md` の最終更新日が sprint-18 に更新されている
- [ ] Sora QA: APPROVED

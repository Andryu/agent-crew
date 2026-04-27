# Sprint-19 計画書

**期間**: 2026-04-27
**ブランチ**: claude/plan-next-sprint-exr9F
**ゴール**: Sprint-18 の積み残し対処（retro.md 重複防止・_lessons.json 未初期化修正・Sprint-18 レトロ記録）

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-18 全4タスク DONE・QA APPROVED・PR #101 マージ済み・elapsed 正常）
- [x] 計画重複タスク: なし（Sprint-18 タスクは全て DONE 確認）
- [x] DECISIONS.md 反映: Sprint-18 エントリ追記済み（sprint18-retro-docs タスクで対処）。Sprint-16 推奨（propose-lesson-rules.sh 本番運用）は Sprint-16 で完了済み。Sprint-18 推奨（Issue重複防止・lessons初期化）を Sprint-19 に反映。
- [x] pm-learned-rules.md 反映:
  - priority >= 9: engineer-go 委譲指示2000トークン制限（agent-crew-sprint-09-process-001）→ タスク設計に反映（lessons-init-fix は S で1ファイル、retro-dedup-fix は S で1ファイル）
  - priority >= 6: 各 Issue 着手条件確認ルール（agent-crew-sprint-13-process-001）→ 全タスクの notes に着手条件を明記済み
  - priority >= 6: みゆきち自動起動ルール（agent-crew-sprint-07-process-001）→ Sora sprint19-qa の notes に @retro 起動依頼を記載
- [x] Riku 担当 L タスク: 0件（全タスク complexity S、制限 1件/sprint に適合）

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | qa_mode |
|---|------|----------|------|------|------------|---------|
| 1 | retro-dedup-fix | retro.md ステップ4に issue_url 重複チェック追加 | Riku | なし | S | inline |
| 2 | lessons-init-fix | install.sh に lessons_init.sh 呼び出しを追加 | Riku | なし | S | inline |
| 3 | sprint18-retro-docs | Sprint-18 レトロ記録作成 | Yuki | なし | S | — |
| 4 | sprint19-qa | Sprint-19 最終QA | Sora | #1 #2 #3 | S | — |

> **合計ポイント: 4 pt**（S×4=4）

**Riku 担当 L タスク**: 0件（制限 1件/sprint に適合）

---

## 並列化

- retro-dedup-fix・lessons-init-fix・sprint18-retro-docs は phase-1 で同時実行可能（互いに独立）
- sprint19-qa は phase-1 全完了後（phase-2）

---

## 変更ファイル予定

| ファイル | 変更種別 | 担当 |
|---------|---------|------|
|  | ステップ4直前に issue_url null チェック追加 | Riku |
|  | lessons_init.sh 呼び出しを完了メッセージ前に追加 | Riku |
|  | 新規作成（遡及レトロ記録） | Yuki |
|  | sprint-18 エントリ追記 | Yuki |
|  | sprint-19 タスク状態記録 | Yuki |

---

## 完了条件

- [ ] retro.md のステップ4直前に issue_url null チェックが追加されている
- [ ] install.sh に lessons_init.sh 呼び出しが追加されている（bash -n 構文確認 PASS）
- [ ] docs/retro/sprint-18.md が存在しレトロ形式になっている
- [ ] DECISIONS.md に sprint-18 エントリが追記されている
- [ ] Sora QA: APPROVED

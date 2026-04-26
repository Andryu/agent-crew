# Sprint-16 計画書

**期間**: 2026-04-26  
**ブランチ**: feat/sprint-16  

---

## ゴール

Sprint-15 で積み残した3件の後処理を完遂する。
`scripts/lessons.sh` の permissions 登録、蓄積済み 18件 lesson の agent .md への反映 Draft PR 作成、pm-learned-rules.md の Sprint-15 lesson 追記。

---

## スプリント前チェック結果

- [x] 前スプリントの設計完了タスクとの突合: 実施済み（Sprint-15 全6タスク DONE、設計→実装の対応確認済み）
- [x] 計画重複タスク: なし（elapsed 短すぎるタスクなし）
- [x] DECISIONS.md 反映: lessons.sh 未登録 / Bash絶対パス問題 / propose-lesson-rules.sh 本番実行推奨 → Sprint-16 タスクに反映

---

## タスク一覧

| # | slug | タイトル | 担当 | 依存 | complexity | risk | qa_mode |
|---|------|----------|------|------|------------|------|---------|
| 1 | lessons-permission-fix | settings.json に Bash(scripts/lessons.sh *) 追加 | Yuki | なし | S | low | — |
| 2 | pm-learned-rules-sprint15 | pm-learned-rules.md に Sprint-15 lesson 2件追記 | Riku | なし | S | low | inline |
| 3 | propose-lesson-rules-exec | propose-lesson-rules.sh 本番実行・Draft PR 作成 | Riku | なし | M | medium | inline |
| 4 | sprint16-qa | Sprint-16 最終QA | Sora | #2 #3 | S | low | — |

> **合計ポイント: 7 pt**（S×3=3 + M×1=4）

**Riku担当 L タスク**: 0件（制限 1件/sprint に適合）

---

## 並列化

- タスク1・2・3 は相互依存なし、同時進行可（タスク1はYuki実施済み）
- タスク4 はタスク2・3 完了後に着手

---

## 実装方針

### propose-lesson-rules-exec の注意点

`propose-lesson-rules.sh` はスクリプト内部で `git checkout -b fix/lesson-rules-YYYYMMDD` を実行する。
feat/sprint-16 ブランチから実行すると別ブランチに切り替わるため、実行後に `git checkout feat/sprint-16` で戻ること。

### pm-learned-rules-sprint15 の追記内容

Sprint-15 で記録された2件の lesson（priority_score=4）:

1. **[全エージェント] Bash 許可パターンは相対パスのみ一致する**
   - settings.json の permissions.allow は相対パス形式（scripts/xxx.sh *）で記述すること
   - 絶対パス（/Users/...）では一致しない

2. **[みゆきち / Yuki] retro フェーズで使用するスクリプトは permissions.allow に事前登録する**
   - スプリント開始前に scripts/lessons.sh など retro フェーズで使うコマンドが permissions.allow に含まれているか確認する

追記前に priority フィルタ確認（`priority_score >= 3`）を実施すること（Issue #89 対策）。

---

## 完了条件

- [ ] settings.json に `Bash(scripts/lessons.sh *)` が追加されている（実施済み）
- [ ] pm-learned-rules.md に Sprint-15 の2件の lesson が追記されている
- [ ] fix/lesson-rules-YYYYMMDD ブランチの Draft PR が作成されている
- [ ] Sora QA: APPROVED

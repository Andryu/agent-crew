# Sprint-18 レトロスペクティブ

**期間**: 2026-04-26
**ブランチ**: feat/sprint-18
**PR**: #101

---

## 観察サマリー

### 成功パターン
- 全4タスク retry_count=0、BLOCKED=0 で完了（lesson-dedup-close・hook-smoke-test・pm-rules-update・sprint18-qa）
- Sprint-17 で導入した TaskCompleted hook が正常動作（_signals.jsonl に task_completed イベント記録済み確認）
- Issue #99/#100 の重複整理を計画的に後処理スプリントとして完了

### 失敗パターン
- **Sprint-18 レトロが未実施**: Sora QA の完了報告末尾に @retro が記述されていたが、実際にはみゆきちが起動されず、本ドキュメントが Sprint-19 計画時に後付けで作成された
- **_lessons.json が環境に未初期化**: ~/.claude/_lessons.json が存在しない状態が継続。lessons.sh による lesson 記録フローが機能していない。install.sh に lessons_init.sh 呼び出しが欠落していることが根因

### 新規 lesson

| lesson_id | 内容 | priority |
|-----------|------|---------|
| agent-crew-sprint-18-process-001 | retro.md ステップ4の gh issue create 前に issue_url null チェックを追加 | 4 |

---

## 次スプリント（Sprint-19）への引き継ぎ

- retro.md ステップ4に issue_url 重複チェックを明示追加（retro-dedup-fix）
- install.sh に lessons_init.sh 呼び出しを追加して _lessons.json 未初期化を解消（lessons-init-fix）
- Sprint-18 レトロ記録（本ドキュメント）を Sprint-19 計画時に遡及作成

---

*このファイルは Sprint-19 計画時（2026-04-27）に遡及作成されました。みゆきちによるレトロが実施されなかったため Yuki が代替記録しました。*

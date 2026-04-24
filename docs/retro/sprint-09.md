# Sprint-09 レトロスペクティブ

実施日: 2026-04-24
担当: みゆきち（retro エージェント）

---

## スプリントサマリー

| 指標 | 値 |
|------|-----|
| タスク数 | 5（設計1 / 実装2 / QA2） |
| 完了数 | 5（全DONE） |
| QA APPROVED | 2 / 2 |
| リトライ | 0回 |
| BLOCKED | 0件 |
| 内部エラー | 1回（engineer-go 無応答停止、Issue #64 再発） |
| Sora指摘 | APPROVED（指摘なし） |

---

## うまくいったこと (Keep)

### 1. pytest 16/16 全PASSED・queue.sh完全互換達成

queue.py の実装において、16ケース全パスおよび queue.sh との出力完全一致を Sora が確認した。typer + pydantic + fcntl.flock の組み合わせが Python による CLI 実装の標準パターンとして機能した。

### 2. uv による Python 環境管理の導入

pip3 の代わりに uv を採用し、依存解決速度と再現性が向上した。

### 3. ADR による移行決定の記録

docs/adr/queue-py-adr.md（ADR-008）として、queue.sh から queue.py への移行決定と根拠が文書化された。今後の移行判断の参照点になる。

### 4. リトライ0・全タスククリーン完了

Sprint-08 と同様にリトライなしで全タスクが DONE になった。依存関係チェーン（設計→実装→QA→自動起動修正→QA）が整然と流れた。

### 5. レトロ自動起動（Issue #65）の具体化

subagent_stop.sh にスプリント完了時の NEXT STEP としてみゆきち起動を追記し、Sprint-09 では実際にこの仕組みに沿ってレトロが実施された。

---

## 改善が必要なこと (Problem)

### 1. engineer-go エージェントが複雑タスクで再び無応答停止（Issue #64 再発）

Sprint-08 で初めて記録された engineer-go の無応答停止（agent-crew-sprint-08-reliability-001）が Sprint-09 でも発生した。複雑な実装タスクで Agent tool が `[Tool result missing due to internal error]` で停止し、親 Claude が直接実装することで回避した。2スプリント連続で同一パターンが発生しており、改善アクション（実装指示の分割・2,000トークン以下）が実行されていない。

### 2. _signals.jsonl への記録が今スプリントも欠落

Sprint-08 で修正された emit バグについて、Sprint-09 の queue.py では Python で正しく実装されたとの報告があるが、`.claude/_signals.jsonl` ファイルが存在しない。signals の書き込み先・有効化がまだ不完全な可能性がある。

### 3. engineer-go サブエージェントへの対策アクションが次スプリントに持ち越しになり続けている

Sprint-08 retro で「サブエージェントへの実装指示は 2,000 トークン以下・complexity L は M×2 に分割」というアクションを記録したが、Sprint-09 の計画策定時にこのアクションが採用されなかった。lesson が計画フェーズにフィードバックされる仕組みが欠如している。

---

## 試してみること (Try)

### 1. スプリント計画時に priority_score >= 6 の未解決 lesson を必ずレビューする

Yuki（pm エージェント）がスプリント計画を立てる前に `lessons.sh list` または `_lessons.json` を確認し、未解決の高優先度 lesson を計画に反映するステップを pm.md に追加する。

### 2. engineer-go へのタスク投入前に complexity チェックを行う

complexity L タスクは自動的に M×2 に分割するか、または直接実装（親 Claude）を選択するガードをサブエージェント起動ロジックに追加する。

### 3. _signals.jsonl の書き込み動作を各スプリント開始時に smoke test する

スプリント開始後の最初のタスクで emit が正常に記録されているかを Sora が確認するステップを追加する。

---

## 持ち越しバックログ（未採用 Issue）

| Issue | 内容 | Sprint-10 候補 |
|-------|------|---------------|
| #64 | engineer-go 無応答停止 | 対策を計画に反映必須 |
| #56 | _signals.jsonl 完全稼働 | queue.py 完成後の次ステップ |
| #48 | Soraスリープ切断問題 | 継続保留 |
| #62 | worktree並列化 | 採用検討 |

---

## 記録した lesson

| lesson-id | 概要 | priority_score | Issue |
|-----------|------|---------------|-------|
| agent-crew-sprint-09-process-001 | engineer-go 無応答停止の再発（2スプリント連続） | 9 | #64（既存） |
| agent-crew-sprint-09-process-002 | lesson アクションがスプリント計画に反映されない | 6 | #69（新規） |
| agent-crew-sprint-09-tooling-001 | _signals.jsonl が依然として記録されていない | 4 | #70（新規） |

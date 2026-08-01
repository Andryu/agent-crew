# Sprint-24 レトロスペクティブ

- 実施日: 2026-08-01
- 担当: みゆきち（retro エージェント）
- スプリント: sprint-24（組織OS Phase 1、ブランチ feature/my-company、PR #126）

---

## ルーブリックスコア

| 評価軸 | スコア | 合格基準 | 判定 |
|--------|--------|---------|------|
| 仕様明確度 | 0.89 | >= 0.8 | PASS |
| QA合格率 | 1.00 | >= 0.9 | PASS |
| ブロック率 | 0.00 | <= 0.1 | PASS |
| 負荷分散 | 2.22 | <= 2.0 | FAIL |

> FAIL 軸: 負荷分散（次スプリントの改善優先事項）
>
> 計画書は Fable が先行完了した4タスクを除いた「残タスクのみ」で負荷分散スコアを 1.6（PASS）と算出していたが、スプリント全体（9タスク・5エージェント）で再計算すると Fable への4タスク集中により 2.22（FAIL）だった。計画外の先行完了タスクを除外して計算すると実質的な偏りが不可視化される、という計算方法自体の盲点がある（詳細は Problem 節参照）。

---

## スプリント概要

- タスク数: 9（全 DONE）
- retry_count 合計: 1（sprint24-qa のみ。初回 CHANGES_REQUESTED → 2回目 APPROVED_WITH_NOTE）
- BLOCKED タスク: 0
- QA 対象: 1タスク（sprint24-qa、APPROVED_WITH_NOTE）
- CRITICAL: ゼロ / MAJOR: 2件（初回のみ、いずれも修正確認済み） / MINOR: 4件（3件修正確認・1件は次スプリント対応の NOTE）

### 担当者内訳

| エージェント | タスク数 | タスク一覧 |
|-------------|---------|-----------|
| Fable | 4 | org-constitution / project-charter-template / coo-persona / weekly-council-protocol（計画立案と並行して先行完了） |
| Alex | 2 | org-departments / adr-014-separation |
| Ren | 1 | token-report-script |
| Sora | 1 | sprint24-qa |
| みゆきち | 1 | sprint24-retro |
| Riku | 0 | 当初計画では担当予定だったが、Fable の先行完了により稼働なし |

### 特殊な進行

Fable（メインセッション）が計画立案と並行して4タスクを先行完了させ、Yuki が計画を後追いで修正する進行になった。計画書の「更新」注記に修正履歴が残っている。

---

## 成功パターン（Keep）

### 実データ検証によるトークン水増しの未然回避

Ren が token-report-script の実データ調査で、JSONL のストリーミング途中経過行を単純合算するとトークン消費が2〜5倍水増しされる落とし穴を発見し、message.id の重複排除で回避した。想像でスキーマを設計せず実データを先に確認したことが、集計結果の重大な誤りを防いだ。

### 表記不一致の自己解決による作業ブロック回避

Alex は指示メッセージのファイル名（ADR-014-org-os-separation.md）と計画書のファイル名（ADR-014-headquarters-department-separation.md）の不一致を検出し、より権威度の高い計画書側を正として自己解決した。判断に迷って作業を止めることなく後続タスクへ進めた。

### QA による文書横断の整合性検証

sprint24-qa は単一文書のセルフレビューでは気づけない「文書間の整合性」欠陥を初回で MAJOR 2件検出し（後述）、token-report.py の実データ実行確認（agent-crew-sprint-11-reliability-002 準拠）も徹底した。修正後 APPROVED_WITH_NOTE まで正しく機能した。

---

## 失敗パターン（Problem）

### 並行作業による担当割衝突

Fable が計画立案と並行して4タスクを先行完了させたことで、Yuki は #6 coo-persona を Riku に割り当てていたが既に完了済みだった。実害は後追い修正で解消したが、計画とのズレを修正するコストが発生した。

### 負荷分散スコアの計算範囲の盲点（新規発見）

計画書は Fable の先行完了分を除いた残タスクのみでスコアを計算し 1.6（PASS）としていたが、全体で再計算すると Fable への集中により 2.22（FAIL）だった。Sprint-23 の Riku 集中（FAIL）に続き、対象を変えて2スプリント連続で負荷分散の問題が発生している。「計画外の先行完了タスクを除外すれば PASS になる」という判定方法自体に盲点があった。

### 文書間の整合性欠陥（QA MAJOR 2件）

sprint24-qa 初回で以下の2件が検出された。

1. constitution.md 第3条の Enforcement に実在しない仕組み（Kai 定常スキャン）を現行稼働中であるかのように記載しており、憲章前文と自己矛盾していた。
2. weekly-council.md が pm.md への伝達を規定していたが、pm.md 側に受け口の記述がなく片方向のみの連携になっていた。

いずれも文書を書いた本人の視点では気づきにくく、複数文書を横断する QA で初めて発見されるタイプの欠陥だった。

### QA 修正時の二次欠陥（見出し番号重複）

上記の修正時に追加した見出しが、pm.md の既存「ステップ0.7」と番号重複する二次欠陥が新たに発生した（2回目 QA の NOTE として発見）。修正作業自体が既存文書の構造との整合を確認せずに行われたことが原因。機能はブロックしないが、修正が新たな不整合を生むリスクを示している。

### レトロ実施時の運用制約（新規発見）

- **macOS に flock コマンドが存在しない**: `_lessons.json` への書き込み手順は `flock` による排他ロックを前提としていたが、darwin 標準環境には同梱されておらず（brew 未インストール）、`flock: command not found` で失敗した。`mkdir` による排他ロックで代替して対処した。
- **`gh issue create` が auto mode 分類器によりブロックされた**: GitHub 上への公開 Issue 作成という外向きの操作のため、確認なしでは実行できなかった。Sprint-23（Bash 権限なしで保留）とは別の理由だが、結果として同じ「Issue 化保留」の扱いになった。

---

## 記録した Lesson

| lesson_id | 概要 | priority |
|-----------|------|---------|
| agent-crew-sprint-24-planning-001 | 並行作業時の担当割衝突（Fable 先行完了と Yuki 計画の後追い修正） | 4 |
| agent-crew-sprint-24-planning-002 | 負荷分散スコアは先行完了タスクを含む全体で計算する | 4 |
| agent-crew-sprint-24-design-001 | 文書間の整合性欠陥は QA が横断的に確認する必要がある | 6 |
| agent-crew-sprint-24-qa-process-001 | QA 修正時の見出し番号重複という二次欠陥 | 2 |
| agent-crew-sprint-24-tooling-001 | 実データ検証によるストリーミングデータ水増しの回避（成功パターン） | 4 |
| agent-crew-sprint-24-tooling-002 | macOS では flock の代わりに mkdir ロックを使う | 6 |
| agent-crew-sprint-24-process-001 | 表記不一致の自己解決（成功パターン） | 1 |

合計: 7件

---

## Issue 化結果

エビデンスゲート（priority_score >= 4 かつ evidence 1件以上かつ issue_url == null）を通過した5件について `gh issue create` を試みたが、auto mode 分類器によりブロックされ実行できなかった（外向きの公開操作のため確認が必要と判定された）。以下は Issue 起票推奨として保留する。

| lesson_id | 判定 | 理由 |
|-----------|------|------|
| agent-crew-sprint-24-planning-001 | 保留 | priority=4・evidence あり — gh issue create が auto mode 分類器にブロックされた |
| agent-crew-sprint-24-planning-002 | 保留 | 同上 |
| agent-crew-sprint-24-design-001 | 保留 | 同上 |
| agent-crew-sprint-24-tooling-001 | 保留 | 同上 |
| agent-crew-sprint-24-tooling-002 | 保留 | 同上 |
| agent-crew-sprint-24-qa-process-001 | 対象外 | priority=2（基準 priority >= 4 未満） |
| agent-crew-sprint-24-process-001 | 対象外 | priority=1（基準 priority >= 4 未満） |

> 注: オーナー確認後、上記5件について手動で `gh issue create` を実行するか、Bash 権限設定の見直しを検討してください。

---

## pm-learned-rules.md 更新結果

- 追加: 5件（`.claude/agents/pm-learned-rules.md`）
  - `agent-crew-sprint-24-planning-001`: [Yuki] メインセッションの先行完了タスクは即座に _queue.json へ反映する
  - `agent-crew-sprint-24-planning-002`: [Yuki] 負荷分散スコアは計画外の先行完了タスクを含めた全体で計算する
  - `agent-crew-sprint-24-design-001`: [全エージェント / Sora] 複数文書にまたがる整合性は QA が横断的に確認する
  - `agent-crew-sprint-24-tooling-001`: [全エージェント] ストリーミング形式データの集計は実データで重複パターンを先に確認する
  - `agent-crew-sprint-24-tooling-002`: [みゆきち] macOS 環境では flock の代わりに mkdir ロックを使う
- スキップ（重複）: 0件
- スキップ（priority < 3）: 2件（agent-crew-sprint-24-qa-process-001, agent-crew-sprint-24-process-001）

---

## Issue 起票推奨（オーナー確認後に起票）

1. **レトロ強制の Stop フック化**（sprint-24 計画書に記載済み、team-lead 合意済み）: 「レトロスペクティブのスキップが再発する」失敗パターン（agent-crew-sprint-22-process-001）の恒久対策。`_queue.json` へのキュー登録と完了条件への明記だけでは構造的強制にならないため、Stop フックまたは同等の機構による強制実行を次スプリント候補として起票する。
2. **`agent-crew-sprint-24-planning-001`**（priority 4）: 並行作業時の担当割衝突対策。
3. **`agent-crew-sprint-24-planning-002`**（priority 4）: 負荷分散スコアの計算範囲を全体に統一する対策。
4. **`agent-crew-sprint-24-design-001`**（priority 6）: 文書間整合性の QA チェック項目追加。
5. **`agent-crew-sprint-24-tooling-001`**（priority 4）: ストリーミングデータ集計の実データ検証ルール化。
6. **`agent-crew-sprint-24-tooling-002`**（priority 6）: retro.md のロック手順を macOS 対応（mkdir ベース）に修正する。
7. **`docs/org/` 相互参照の横断チェック**（sprint-24 計画書「次スプリント候補」に記載済み）: coo.md・departments.md・constitution.md 間の参照リンク切れがないかを次スプリント冒頭のチェックリストに追加する。
8. **計画書のポイント集計の機械化**（sprint-24 計画書「次スプリント候補」に記載済み）: `jq` でタスク一覧の complexity を機械集計してから計画書に転記する運用に変更する。

---

## 次スプリントへの改善優先事項

1. **負荷分散改善（FAIL 軸）**: Yuki は担当者ドラフト後、計画外の先行完了タスクを含む全体で負荷分散スコアを計算する（pm-learned-rules.md 反映済み）。
2. **並行作業時の担当割衝突防止**: メインセッションが計画立案と並行してタスクを実装する場合は、着手・完了のたびに `_queue.json` を即時更新する（pm-learned-rules.md 反映済み）。
3. **文書間整合性の QA チェック強化**: Enforcement 等の稼働記述の実在性と、文書間連携の受け口有無を QA チェックリストに明示する（pm-learned-rules.md 反映済み）。
4. **retro.md のロック手順の macOS 対応**: `flock` 依存を解消し、`mkdir` ロックへの統一を検討する。
5. **Issue 起票フローの見直し**: `gh issue create` が auto mode 分類器にブロックされるケースがあることを踏まえ、レトロ完了時の Issue 化はオーナー確認後の手動実行を前提とした運用に整理する。

# 学習ループへの効果検証の導入 — 段階的導入提案（v3）

作成日: 2026-08-08（v2）/ 最終更新: 2026-08-08（v3 追補）
ステータス: v2 実装済み（PR #177/#178）・v3 追補はレビュー中
起案: team-lead（Fable）
レビュー: Sora（QA） — 条件付き承認（2026-08-08、指摘10件を本版に反映済み）
関連: docs/spec/lessons-json-schema.md / docs/spec/evidence-gate-design.md / docs/spec/self-improvement-mode-design.md

---

## 背景

学習ループ監査（2026-08-08）の結論: 記録・構造化・ゲーティングは業界水準超だが、
「書き出したルールが行動を変えたか」を測る仕組み（効果検証）と、効かないルールを
捨てる仕組み（剪定）が存在しない。

- **F-1 検証不在**: `verified` ステータスが未運用。sprint-27 レトロには「ルール化した
  当人が同一セッション内で同じ落とし穴を踏んだ」記録があり、プロンプト追記が
  行動を変えない実証がループ内に存在する。
- **F-2 優先度式の欠陥**: severity×frequency は構造的再発問題を過小評価。
  全4軸PASSのスプリントで priority 9 の教訓が2件発生してもルーブリック改訂の
  メタ手続きがない。
- **F-3 剪定不在**: ルールは末尾追記のみ。`pm-learned-rules.md` は既に **983行** あり、
  指示ファイルの遵守率が低下するとされる 100〜150 行を大幅に超過している。

効果検証の定義（本提案のスコープ）:

1. **再発の測定** — 書いたルールで同じ失敗が起きなくなったかを数える
2. **効かないルールの処分** — 再発したルールは「無効」と判定し、プロンプトより
   強い手段（コード化）へ格上げするか、削除する

---

## Sora レビューで v1 から変更した点

| 指摘 | 重大度 | v2 での反映 |
|------|--------|------------|
| 2. 「再発なし2スプリント」を数える状態保持機構がない | 高 | `_lessons.json` に `verification_streak` / `last_recurrence_sprint` フィールドを追加（タスク L0-1） |
| 3. 再発検知条件の必須化がプロンプト任せ（F-1と同型の罠） | 高 | `lessons.sh add` に `--recurrence-condition` 必須オプションを追加しコードでゲート（タスク L0-2） |
| 4. `pm-learned-rules.md` は983行で目標の6〜10倍 | 高 | 初回大掃除を Level 2 の運用から切り離し、独立した M〜L タスクとして計上（タスク L2-1） |
| 5. スキーマ文書が実装から乖離（status/scope/stack/source_repo 未定義） | 中 | `enforcement` 追加時に既存4フィールドも含めてスキーマ文書を実装に追いつかせる（タスク L0-1 に統合） |
| 6. `audit-scan.sh` 自身が `readlink -f` に依存（検出器自身のバグ） | 中 | 検出追加の前提タスクとして自身の修正を明記（タスク L1-1） |
| 7. `queue.py done` への git status 警告は repo ルート解決が必要 | 中 | `git rev-parse --show-toplevel` による明示的なルート解決を実装要件に明記（タスク L1-2） |
| 8. `enforcement: code` だけでは二重管理を防げない（書き出しフロー2箇所が enforcement を見ない） | 中 | retro.md Step 5 / `propose-lesson-rules.sh` に skip 分岐を追加。振り分け判断者は「みゆきちが即時判断し、Yuki が自己改善モードで再点検」と定義（タスク L1-4） |
| 9. ルーブリック改訂自動起票の閾値が1スプリント分のデータしかない | 低 | 2スプリントの試験運用（発火頻度の観察）を経て正式化する条件を明記 |
| 10. F-1 引用の「再発」は同一セッション内の即時反復 | 低 | 背景の記述を修正済み（上記 F-1） |

---

## Level 0 — 再発チェックの基盤（次スプリント、S規模×3）

「コードほぼ不要」ではなく **小規模な実装を含む** ことを明確化する（Sora 指摘2・3）。

1. **スキーマ拡張＋文書の実装追いつき**（L0-1, Alex 設計 → Riku 実装）
   - `Lesson` に追加: `recurrence_condition`（string, ルール書き出し対象では必須）、
     `verification_streak`（int, 再発なし連続スプリント数）、
     `last_recurrence_sprint`（string|null）、`enforcement`（`code|prompt|process`）
   - 既存の実装済みフィールド `status` / `scope` / `stack` / `source_repo` を
     スキーマ文書に追記し、`additionalProperties: false` と実装の整合を回復する
2. **lessons.sh のゲート化**（L0-2, Riku）
   - `add` に `--recurrence-condition` オプション追加。`--type failure` かつ
     priority>=3（ルール書き出し対象）では未指定をエラーにする（最小文字数チェック付き）
   - `verify-check <sprint>` サブコマンド追加: 対象 lesson の streak を機械更新
     （再発報告があれば 0 リセット＋`last_recurrence_sprint` 更新、なければ +1、
     streak>=2 で `verified` へ自動遷移）
3. **retro.md への再発チェックステップ追加**（L0-3, Alex）
   - 「前スプリントまでに書き出したルールを列挙し、今スプリントの failure lesson と
     突合 → `lessons.sh verify-check` を実行」を正式ステップ化
   - メタ評価ルールを追記: 「全軸PASSかつ priority>=6 の教訓が2件以上 →
     ルーブリック改訂タスクの起票を提案する」。**2スプリントは試験運用**とし、
     発火頻度を観察してから正式化する（Sora 指摘9）

## Level 1 — 機械化ゲート（次スプリント〜次々スプリント、S規模×4）

原則: **script/lint/hook で強制可能な教訓はプロンプトに書かずコードにする。**
コード化された教訓は再発検証が不要になる（テストが通れば効いている）。

1. **audit-scan.sh の readlink 修正＋検出追加**（L1-1, Riku）
   - 前提: 自身の symlink チェック（3.2節）の `readlink -f` 依存を python3 realpath 等で
     置換（BSD readlink での偽陽性 FAIL を解消）— Sora 指摘6
   - その上で、リポジトリ内スクリプトの `readlink -f` 使用を検出する項目を追加
   - reliability-002 を `enforcement: code` へ更新
2. **queue.py done の未コミット警告**（L1-2, Riku）
   - `git rev-parse --show-toplevel` で repo ルートを明示解決した上で
     `git status --porcelain` を確認し、差分があれば警告表示（ブロックはしない）
   - 全体差分しか見られない制約（タスク関連差分との区別不可）は既知の制約として
     notes に明記 — Sora 指摘7
   - reliability-003 を `enforcement: code` へ更新
3. **source_repo 正規化**（L1-3, Riku）
   - `lessons.sh` 内で SSH/HTTPS 形式を正規化（比較・保存の両方）
   - tooling-001 を `enforcement: code` へ更新（priority 2 だが構造的再発が確定して
     いるため機械化対象とする — F-2 の運用補正）
4. **enforcement 分岐の統合**（L1-4, Alex 設計 → Riku 実装）
   - retro.md Step 5 と `propose-lesson-rules.sh` の抽出条件に
     「`enforcement == "code"` は書き出しスキップ（コード化タスクへ誘導）」を追加
   - 振り分け判断者: みゆきちがレトロ時に即時判断、Yuki が自己改善モードで再点検

## Level 2 — 剪定と実測データ（Level 1 完了後）

1. **pm-learned-rules.md 初回大掃除**（L2-1, **独立 M〜L タスク**、Alex 主担当＋Yuki レビュー）
   - 983行 → 目標100〜150行。verified 済み・機械化済みは削除、類似ルールは抽象化して統合
   - 削除したルールの根拠は `_lessons.json`（台帳）に残るため情報は失われない
   - Sora 指摘4により Level 2 の定常運用とは別タスクとして計上
   - **✅ 実施済み（2026-08-08）**: 983行 → 83行。機械化済み7件を表形式で分離、
     統合15グループ、陳腐化6件削除。全 lesson_id の traceability を括弧内に保持
2. **定常棚卸し**（L2-2, みゆきち）
   - 3スプリントに1回、レトロの一部として実施。ファイル行数上限を retro.md に明記
   - **✅ 実施済み（2026-08-08）**: retro.md ステップ5に棚卸し手順（150行上限・
     verified/機械化済み削除・統合・報告）を追加
3. **/insights 月次実行**（L2-3, Yuki 運用ルール — オーナー操作が必要）
   - facets 由来の実測データ（繰り返し指示・中断・ツール失敗）を自己改善モードの
     入力に追加し、エージェント自己報告との差分を分析する
   - `/insights` はオーナーのローカルセッション履歴を解析するコマンドのため、
     リモートセッションからは自動化できない。**月初にオーナーが `/insights` を実行し、
     レポートの「CLAUDE.md additions」相当の指摘を Yuki の自己改善モードへ渡す**運用とする

## Level 3 — 本格 eval 基盤: 導入しない

ルールあり/なしのA/B並列実行・エージェント別 component-level eval・trajectory 分析の
自動化は、個人開発の規模ではコストが効果に見合わないため導入しない。
（例外の「ルーブリック改訂の自動起票」は L0-3 に試験運用として統合済み）

---

## タスク一覧（スプリント計画への取り込み用）

| # | slug | 担当 | 依存 | complexity | 内容 |
|---|------|------|------|------------|------|
| 1 | verify-schema-design | Alex | なし | S | L0-1 設計: スキーマ拡張＋文書の実装追いつき |
| 2 | lessons-verify-impl | Riku | #1 | M | L0-1/L0-2 実装: フィールド追加・--recurrence-condition ゲート・verify-check |
| 3 | retro-verify-step | Alex | #1 | S | L0-3: retro.md 再発チェックステップ＋メタ評価ルール（試験運用） |
| 4 | audit-scan-readlink-fix | Riku | なし | S | L1-1: 自身の readlink 修正＋検出追加 |
| 5 | queue-done-git-guard | Riku | なし | S | L1-2: done 時の未コミット警告（ルート解決付き） |
| 6 | lessons-source-repo-normalize | Riku | なし | S | L1-3: source_repo SSH/HTTPS 正規化 |
| 7 | enforcement-gate-design | Alex | #1 | S | L1-4 設計: 書き出しスキップ分岐＋判断フロー |
| 8 | enforcement-gate-impl | Riku | #7 | S | L1-4 実装: retro.md Step5 / propose-lesson-rules.sh 改修 |
| 9 | verify-loop-qa | Sora | #2,#3,#4,#5,#6,#8 | M | 横断QA: 全実装の検証（pytest 追加必須） |
| 10 | verify-loop-retro | みゆきち | #9 | S | レトロ（初回の再発チェックステップ実運用を兼ねる） |

合計ポイント目安: 13 pt（S×8=8pt + M×2=4pt +α）。
L2-1（pm-learned-rules 大掃除, M〜L）は負荷分散の観点から**次々スプリント**に送る。

## 成功条件（このプロジェクト自体の効果検証）

- 2スプリント後: `verified` へ遷移した lesson が1件以上存在する
- 3スプリント後: `enforcement: code` の教訓について同型再発ゼロ
- 4スプリント後: `pm-learned-rules.md` が150行以下で維持されている

---

## v3 追補 — 海外最先端調査（2026-08-08）の反映

3系統の調査（実務家: Karpathy/Willison/HumanLayer/Manus 等、研究: Library Drift/ACE/
memory poisoning 等、公式: Anthropic/OpenAI/Google）の結論は「予算制約つきの蓄積＋
機械検証＋定期剪定」への収束であり、v2 実装と方向一致。ただし v2 に欠けている
4視点が特定されたため、以下を追補する。いずれも小規模（プロンプト・文書の編集）。

### V3-1. 反証条件 — 記憶の作話（confabulation）対策

根拠: Reflexion 型エージェントは「自信はあるが誤った失敗診断」を記憶に固定し、
以後それに従い続ける（Honest Lying, arXiv 2605.29463）。v2 の verify-check は
「再発したか」を測るが「診断自体が正しかったか」は測らない。

- retro.md ステップ2.7 に追加: 再発チェック時、**同型事象が別の根因で再発した場合は
  「ルールが破れた」ではなく「診断が誤っていた」を疑い、supersedes で診断を改訂した
  新 lesson を起こす**（旧 lesson は dismissed へ）。
- retro.md ステップ2 の記録ガイドに追加: priority >= 6 の lesson は description に
  「この診断が誤りなら何が観測されるはずか」（反証のヒント）を1文含めることを推奨。

**診断改訂の実行手順（Sora レビュー必須指摘1への対応 — 誤昇格経路を塞ぐ）:**

1. `lessons.sh verify-check <sprint> --recurred <旧lesson-id>` —
   **診断改訂対象の旧 lesson は必ず `--recurred` に含める**。防げなかった事実は
   根因の異同にかかわらず同じであり、streak を確実にリセットするため。
   verify-check より前に dismiss してはならない（順序固定）。
2. `lessons.sh add --supersedes <旧lesson-id> ...` で改訂診断の新 lesson を起こす
3. `lessons.sh set-status <旧lesson-id> dismissed` — dismissed は verify-check の
   streak 対象ステータスに含まれないため、以後誤って verified へ昇格する経路はない
4. 旧 lesson に `issue_url` がある場合: 該当 Issue に「診断改訂（supersedes: 新ID）」の
   コメントを追記してクローズし、新 lesson 側の evidence に旧 Issue URL を残す

後続実装タスク: `lessons.sh add --supersedes` に指定 ID の存在チェックを追加する
（`--recurred` には存在チェックがあるが supersedes には無い非対称の解消）。

### V3-2. 信頼境界 — 記憶汚染（memory poisoning）対策

根拠: 通常クエリのみで長期記憶を汚染する攻撃（MINJA: 95%超の成功率）が実証されており、
「記憶を効かせる設計ほど攻撃面が広がる」（arXiv 2606.04329）。

- retro.md ステップ4.5（外部リポジトリ由来 lesson のクロスポスト）に注記を追加しつつ、
  **強制は構造化フィルタで行う（Sora レビュー必須指摘2への対応）**。プロンプト上の
  約束だけでは、本提案が対策しようとしている「規範だけでは徹底されない」問題を
  再生産するため:
  - `_lessons.json` スキーマに `owner_approved`（boolean, default false）を追加
  - retro.md ステップ5 と `propose-lesson-rules.sh` の**両方の抽出クエリ**に
    `and ((.source_repo // "") == $own_repo or (.owner_approved // false))` 相当の
    条件を追加（`$own_repo` は `git remote get-url origin` の正規化値）
  - 台帳への記録と Issue 起票までは外部由来でも可。行動変更（ルール書き出し・
    エージェント定義変更）への昇格は本社リポジトリ由来またはオーナー承認済みに限る

### V3-3. 差分棚卸し — context collapse 対策

根拠: 蓄積した文脈の全面書き換え（monolithic rewrite）は反復のたびに詳細を侵食する
（ACE, arXiv 2510.04618）。2026-08-08 の初回棚卸し（983→83行）は全面書き換えで実施
したが、恒常運用で繰り返すべきではない。

- retro.md ステップ5 の棚卸し手順を修正: **棚卸しは差分操作（個別ルールの削除・
  2件の統合・1件の語調修正）のみとし、ファイル全体の書き直しは行わない**。
  担保（Sora 指摘への対応）: 棚卸しコミット前に `git diff --stat` を確認し、
  pm-learned-rules.md の変更行数が現行行数の30%を超える場合は差分操作に分割し直す、
  を手順に明記する。
- 月次ヘルスチェックに lint 項目を追加: pm-learned-rules.md 内の
  「相互に矛盾するルール」「台帳に対応 lesson が見つからない孤児ルール」を検出して
  報告する（Karpathy の LLM Wiki lint 相当）。
  **更新対象の実体（Sora 指摘への対応）**: リポジトリ内スクリプトではなく、
  claude.ai の Routine「学習ループ月次ヘルスチェック」（2026-08-08 作成、毎月1日
  9:00 JST に読み取り専用のクラウドセッションを起動）の prompt である。
  lint は Read/Grep のみで実施可能なため、既存の読み取り専用制約と整合する。

### V3-4. 助言化 — 規範的言語の段階的緩和

根拠: Anthropic 公式「旧世代向けの規範的スキルは新世代モデルの品質を劣化させる。
CRITICAL/YOU MUST は普通の書き方に戻せ」。OpenAI 公式「矛盾ルールの調停に推論トークン
を浪費する」。Forage V2 の知識ベースは「助言文書であって拘束的命令ではない」設計。

- 次回棚卸し時（差分操作で）: pm-learned-rules.md の「〜してはいけない」列挙を、
  **「推奨行動＋理由」の形式へ順次書き換える**。禁止形を残すのは、破ると即時に
  実害が出る**ガードレールL0（人間専権: docs/org/guardrails.md 第1条）**関連のみ
  （本文書の Level 0 タスク群とは別概念。用語衝突を避けるため「ガードレールL0」と表記）。
  判定を構造化するため、該当 lesson には `tags: ["guardrail"]` を付与する運用とする。
- propose-lesson-rules.sh の「禁止行動」語彙の変更は**4箇所を一括改修**する
  （Sora 指摘への対応 — 見出し1箇所だけ変えると既存セクション判定の grep が
  外れて重複セクションが量産されるバグになる）:
  entry フィールド見出し・セクション見出し・既存セクション検出用 grep パターン・
  コミット/PRメッセージ。

### 実施順序

V3-1〜V3-3 は次スプリントの S タスク×3（retro.md 編集×2・ルーチンプロンプト更新×1）。
V3-4 は次回棚卸し（3スプリント後）に統合する。

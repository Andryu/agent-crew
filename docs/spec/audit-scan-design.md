# audit-scan.sh 設計書 — 憲章第3条 Enforcement 実運用化

> 対象slug: `audit-scan-design`（Sprint-26 #4）。実装は `audit-scan-impl`（#5, Riku）、QAは `audit-scan-qa`（#6, Sora）で行う。

## 1. 目的

`docs/org/constitution.md` 第3条「最小権限」の Enforcement は現状「Kai による定常スキャンは将来整備」という注記のまま止まっている。本設計は、その注記を解除し、実際に動く `scripts/audit-scan.sh` の仕様を定義する。

対象は以下3種の逸脱・破損検知:

1. `permissions.allow` がスプリント計画書に記載された変更と整合しているか（無断追加の検知）
2. symlink の健全性（リンク切れ・自己参照）
3. `.claude/settings.json` の `hooks` の構文と、参照している既存フックスクリプトの生存確認

## 2. 実行I/F

```
scripts/audit-scan.sh [--sprint <sprint-name>] [--out <report-path>]
```

- `--sprint`: 突合対象のスプリント計画書を明示指定（省略時は `.claude/_queue.json` の `.sprint` フィールドから自動解決。キューが無い場合は permissions.allow チェックのみスキップし、symlink/hooksチェックは実行する）
- `--out`: Markdownレポートの保存先（省略時は標準出力のみ。`docs/org/audit/` への保存は呼び出し側 [Rin/Yuki] が `--out` を指定して行う）

## 3. チェック項目仕様

### 3.1 `permissions.allow` 整合性チェック（差分検知）

**目的**: 憲章第3条 Enforcement「`permissions.allow` への追加はスプリント計画書に記載されたもののみ」を機械検証する。

**手順**:

1. 対象スプリントの計画書（`docs/sprints/<sprint>.md`）を読み込む
2. `git merge-base origin/main HEAD`（スプリントブランチの分岐元コミット）を求め、そのコミット時点の `.claude/settings.json` の `permissions.allow` 配列を取得する（`git show <base-commit>:.claude/settings.json | jq -r '.permissions.allow[]'`）
3. 現在の `.claude/settings.json` の `permissions.allow` と比較し、**新規追加分**（3の集合差分）を洗い出す
4. 新規追加分の各エントリについて、スプリント計画書の全文中に当該文字列（またはそのコマンド名部分、例 `scripts/audit-scan.sh`）が言及されているかを `grep -F` で確認する
5. 言及がないエントリは **FAIL** として報告する（「無断追加」の疑い）

**誤検知バイパス**:
- ブランチが `origin/main` から分岐していない（`git merge-base` が取得できない）場合はこのチェック自体をスキップし、レポートに「SKIP: merge-base不明」と明記する
- スプリント計画書ファイルが見つからない場合も同様にSKIPしレポートに明記する（存在しないことを FAIL にはしない — 計画書のパス変更等の運用揺れを誤検知しないため）

### 3.2 symlink 健全性チェック

**目的**: `agent-crew-sprint-25-reliability-001`（symlink/配布系は自己参照ガード）を定常運用として機械化する。

**手順**:

1. リポジトリ全体から symlink を列挙する（`find . -type l -not -path './.git/*' -not -path '*/node_modules/*'`）
2. 各 symlink について:
   - **リンク切れ**: `[ -e "$f" ]` が偽（symlinkの参照先が存在しない）→ FAIL
   - **自己参照（ループ）**: `readlink -f "$f"` が失敗する、または `readlink "$f"` の解決結果が `$f` 自身のパスと一致する → FAIL
3. `.claude-worktrees/` 配下（worktree由来の一時ディレクトリ）は対象外とする

### 3.3 `.claude/settings.json` hooks 構文・生存確認

**目的**: hooks定義の破損（JSON構文エラー・参照先スクリプトの欠落）を早期検知する。

**手順**:

1. `jq -e . .claude/settings.json` でJSON全体の構文を確認（失敗したら即 FAIL、以降のチェックは中断してレポートに理由を記載）
2. `jq -r '.hooks[][] .hooks[]?.command'` 相当のクエリで全 `command` 文字列を抽出する
3. 各 `command` について:
   - `.claude/hooks/*.sh` へのパス参照であれば、ファイル存在確認 (`test -f`) と実行権限確認 (`test -x`) を行う。欠落していれば FAIL
   - `bash -c '...'` 形式のインラインコマンドであれば、内部スクリプト文字列を抽出し `bash -n` で構文検証する（`agent-crew-sprint-08-tooling-001` 準拠）。構文エラーがあれば FAIL
4. 上記いずれのパターンにも一致しないコマンド（今後追加される未知形式）は「UNKNOWN: 手動確認推奨」としてWARNING扱いにする（FAILにはしない。誤検知でスキャン自体の信頼性を落とさないため）

## 4. 出力仕様

### 4.1 Markdownレポート形式

```markdown
# audit-scan レポート — YYYY-MM-DD HH:MM

対象スプリント: sprint-26
対象コミット: <short-sha>

## サマリー

| チェック項目 | 結果 |
|------------|------|
| permissions.allow 整合性 | PASS / FAIL / SKIP |
| symlink 健全性 | PASS / FAIL (n件) |
| hooks 構文・生存確認 | PASS / FAIL (n件) / WARNING (n件) |

## 詳細

### permissions.allow
- [FAIL] "Bash(scripts/xxx.sh *)" — スプリント計画書に言及なし
（PASSの場合は「新規追加なし、または全件計画書に記載あり」の1行のみ）

### symlink
- [FAIL] path/to/symlink — リンク切れ（参照先: ../missing/target）
（該当なしの場合は「該当なし」の1行のみ）

### hooks
- [FAIL] .claude/hooks/xxx.sh — ファイルが存在しない
- [WARNING] bash -c '...' — 未知の形式のため手動確認推奨

## 総合判定
PASS / FAIL
```

### 4.2 終了コード

| コード | 意味 |
|-------|------|
| 0 | 全チェック PASS（SKIP・WARNINGのみは0で問題ない） |
| 1 | 1件以上 FAIL あり |
| 2 | スクリプト自体の実行前提エラー（`jq` 不在・`.claude/settings.json` 自体が読めない等） |

**本スクリプトは "enforce" ではなく "スキャン・報告" が役割であるため、他のフック（`enforce-retro-stop.sh` 等）と異なり Bash 実行を能動的にブロックする用途では使わない。** 終了コードは呼び出し側（Rin/Yuki/Kai）が次アクション判断に使う入力に留める。

## 5. 実行タイミング設計

### 5.1 経営会議準備時（Rin）

`docs/org/weekly-council.md` の「事前準備」（Rinが意思決定キューを生成する工程）に以下を追加する。

```diff
 | 事前準備 | Rin が意思決定キュー（`docs/org/council/YYYY-MM-DD-queue.md`）を生成しておく |
+| 監査スキャン | Rin が `scripts/audit-scan.sh --out docs/org/audit/YYYY-MM-DD-audit.md` を実行し、FAILがあれば意思決定キューの「要判断」に追加する |
```

`.claude/agents/coo.md`「主な責務」に以下を追加する。

```diff
 4. **横展開トリガーの監視** — （...）
+5. **定常監査スキャン** — 経営会議準備時に `scripts/audit-scan.sh` を実行し、`permissions.allow` 逸脱・symlink破損・hooks異常を確認する。FAILがあれば意思決定キューの「要判断」に追加し、PASSならトークン会計セクションの隣に1行「監査スキャン: PASS」とだけ記載する。
```
（既存の項目番号5・6はそれぞれ6・7へ繰り下げ）

### 5.2 スプリント開始時（Yuki経由でKaiが実行、またはYukiが代行）

`.claude/agents/pm.md`「スプリント開始前チェック」の「ステップ2.5: フック権限の事前確認」の直後に新ステップとして追加する。

```diff
 ### ステップ2.5: フック権限の事前確認
 （...既存の記述...）

+### ステップ2.6: 定常監査スキャン（Kai, 憲章第3条 Enforcement）
+
+`scripts/audit-scan.sh --sprint <sprint-name>` を実行する（Kaiに委譲、またはKai不在の場合はYukiが代行実行）。
+FAILがあれば計画書提出前に是正するか、是正できない場合はブロッカーとして計画書の「確認事項」に明記した上で提出する。
+実行結果（PASS/FAILの別）をスプリント計画書の「事前チェック結果」セクションに1行追記する。
```

### 5.3 Kai（`security.md`）への職務追記

「主な責務」に以下を追加する。

```diff
 ## 主な責務

 1. **セキュリティコードレビュー** — （...）
 5. **セキュリティ勧告の作成** — （...）
+6. **定常監査スキャン（憲章第3条 Enforcement）** — `scripts/audit-scan.sh` を①経営会議準備時（Rin依頼分の代行）②スプリント開始時（Yuki依頼分）に実行し、`permissions.allow` 逸脱・symlink破損・hooks構文/生存異常を検出する。FAILがあれば重大度を判定し（下記「監査スキャン重大度」参照）、CRITICAL/HIGH相当は即座にYuki/Rinへ報告する。
```

「完了報告フォーマット」に以下のセクションを追加する。

```diff
 ### 依存関係スキャン結果
 - go list / npm audit: 問題なし / [CVE番号と深刻度]
+
+### 監査スキャン結果（audit-scan.sh）
+- 総合判定: PASS / FAIL
+- FAILの内訳（あれば）: [permissions.allow / symlink / hooks のどれか、詳細]
```

**監査スキャン重大度（Kai用の補助基準）**:

| 検知内容 | 重大度 |
|---------|--------|
| `permissions.allow` の無断追加（計画書に記載なし） | HIGH（最小権限の逸脱そのもの） |
| symlink リンク切れ | MEDIUM（配布事故の兆候） |
| symlink 自己参照 | HIGH（無限ループ・ツール停止リスク） |
| hooks JSON構文エラー | HIGH（全フック機構が機能停止するリスク） |
| hooks 参照スクリプト欠落 | MEDIUM |
| hooks UNKNOWN（未知形式） | LOW（手動確認推奨のみ） |

## 6. `docs/org/constitution.md` 第3条 更新指示（Riku適用）

現行の以下の一文を:

```
Kai（監査）による定常スキャンは**将来整備**（次スプリント以降で Kai に定常スキャン機能を追加後に運用開始。ADR-014 の推奨事項と同期）。
```

以下に置換する:

```
Kai（監査）は `scripts/audit-scan.sh` による定常スキャンを、①週次経営会議の準備時（Rin依頼、`docs/org/weekly-council.md`）②スプリント開始時（Yuki依頼、`pm.md` ステップ2.6）の2タイミングで実行する。
スキャン結果（Markdownレポート）は意思決定キュー／スプリント計画書に転記され、`permissions.allow` 逸脱・symlink破損・hooks構文/生存異常を機械的に検知する（Sprint-26 `audit-scan-design`/`audit-scan-impl` で実装、ADR-014 の推奨事項に対応）。
```

## 7. `audit-scan-impl`（Riku, #5）への引き継ぎ

- 実装対象: `scripts/audit-scan.sh`（本設計書 §2〜4 準拠）。既存スクリプト（`enforce-retro-stop.sh` 等）の bash 記法・`jq` の使い方を踏襲する
- `--sprint` 省略時のスプリント自動解決は `.claude/_queue.json` の `.sprint` フィールドを使う（`enforce-retro-stop.sh` と同じ取得方法）
- `.claude/agents/security.md`・`docs/org/coo.md`(実体は`.claude/agents/coo.md`)・`docs/org/weekly-council.md`・`.claude/agents/pm.md`・`docs/org/constitution.md` への追記は、本設計書 §5・§6 の diff をそのまま適用する（既存文言の削除は最小限、番号の繰り下げのみ）
- `permissions.allow` は既に本スプリントで `Bash(scripts/audit-scan.sh *)` が計画書記載の上で追加済み（sprint-26.md ステップ2.5参照）のため、実装時点で追加の権限申請は不要
- `agent-crew-sprint-25-reliability-001`（symlink/配布系は自己参照ガード＋実機QA）に基づき、`audit-scan-qa`（#6, Sora）では**実際にリポジトリ上で `scripts/audit-scan.sh` を実行**し、意図的にダミーのリンク切れsymlinkを1件作成→検知確認→削除、という実機検証を必須とする

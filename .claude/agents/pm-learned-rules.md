# pm-learned-rules.md — Yuki スプリント計画時参照ルール集

> `~/.claude/_lessons.json` の教訓から生成されたルール集。スプリント計画前に必ず読み込むこと。
> 各ルール末尾の括弧は根拠 lesson_id（複数は統合を示す）。経緯・エビデンスの全文は台帳を参照。
>
> **棚卸し規律（learning-loop-verification-proposal.md L2）**:
> - 本ファイルの上限は **150行**。超過したらレトロで統合・削除する
> - `verified`（再発なし2スプリント）または `enforcement: code`（機械化済み）のルールは削除する
> - 削除してもエビデンスは `_lessons.json` に残る。復活はルールではなく機械化を優先する

---

## 機械化済み（このファイルには書かない — コードが強制する）

| 元ルール | 強制箇所 |
|---------|---------|
| readlink -f 非移植性（sprint-27-reliability-002） | `audit-scan.sh` 3.7 が使用を検出しFAIL |
| 未コミット作業の点検（sprint-27-reliability-003） | `queue.py done` が差分を警告 |
| 自由記述への正規表現マッチ禁止（sprint-27-reliability-001） | `queue.py` close_issue 専用フィールド化済み |
| source_repo の形式統一（sprint-27-tooling-001） | `lessons.sh` が SSH→HTTPS 自動正規化 |
| QA再判定による retry_count 汚染（sprint-26-tooling-001） | `queue.py qa --force` / done側ガード実装済み |
| 再発検知条件の記録漏れ | `lessons.sh add` が必須オプションとして拒否 |
| レトロ未実施のままセッション終了 | `enforce-retro-stop.sh`（Stopフック）が警告 |

---

## Yuki（計画）

**計画前チェックを省略しない** — `_lessons.json` の priority>=6 未解決エントリ確認、前スプリント DONE タスクとの突合（計画済み未実装/実装済み未計画の洗い出し）、各 Issue の着手条件の notes 転記を、タスク分解より先に行う。（sprint-09-process-002, sprint-10-process-001, sprint-13-process-001）

**負荷分散はポイントベースで、全タスク対象に事前計算する** — 担当ドラフト段階で `sprint-points.sh --md` を実行。計画外の先行完了タスクも含めた全体で判定し、スコア>2.0 なら再配分。「実装は Riku」の暗黙想定で確認を省かない。（sprint-23-planning-001, sprint-24-planning-002）

**実行時権限は計画時に登録する** — スプリントで使うスクリプト・フック実装に必要な権限（`Write(**)`・`Bash(chmod *)` 等）をタスク notes に明記し、開始前に `permissions.allow` へ追加。Bash パターンは相対パス形式のみ一致する。（sprint-15-tooling-001, sprint-15-tooling-002, sprint-17-tooling-001）

**vault の ADR 索引は無条件に信頼しない** — 索引記載の文書がコミット済みか疑わしい場合は `git log --all --oneline -- <path>` で確認してから前提にする。（sprint-26-process-001）

## Yuki / team-lead（指揮系統）

**スプリント進行中のタスクレベル指示は PM 経由に一本化する** — team-lead は方針決定に徹し、実装担当者へ直接指示を出さない。チーム合意と衝突する指示の温床になる。（sprint-27-process-001, priority 9・未検証）

## Riku（実装）

**委譲サイズを守る** — 実装指示は 2,000 トークン以下、大きなファイルは関係部分のみ抜粋、complexity L は M×2 に分割。Riku への L タスクは 1スプリント1件まで。（sprint-08-reliability-001, sprint-09-process-001, sprint-11-reliability-001）

**完了・QA承認済みタスクへの仕様追加は新規タスク起票を必須とする** — 設計書のフォローアップ節に記載があっても自己判断で追加実装しない。（sprint-27-process-003, priority 9・未検証）

**実装前に notes 記載の設計書・ADR と仕様値を突合する** — 齟齬があれば実装を止めて Yuki へ報告。（sprint-05-qa-001）

**PR は Test Plan 記入済みで作成し、完了後の commit/push/PR はオーナー確認なしで進める**（sprint-05-process-001, sprint-05-process-002）

## Sora（QA）

**QA は実行ベース** — notes のテスト手順を実際に実行し結果を summary に記録する。Bash が使えない環境では静的検証に差し替えて APPROVED を返さず `CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）` を返す。symlink・ファイル配布系は実機実行（疑似配布先への実コマンド実行）まで行う。（sprint-08-process-001, sprint-11-reliability-002, sprint-25-reliability-001）

**文書の整合性は横断で確認する** — 「稼働中」等の現在形記述の実在性、文書間連携の受け口の有無をチェック項目に含める。（sprint-24-design-001）

**APPROVED_WITH_NOTE の NOTE はスプリント完了条件に含める** — NOTE 未実施のままスプリントを終了しない。（sprint-22-tooling-001）

## Alex（設計）

**設計書の追記・更新は実装コードを直接確認してから行う** — notes/summary の古い表記だけを頼りに書き換えない。命名等の確定事項は `_queue.json` に明記し単一の真実源とする。（sprint-27-process-002, priority 6・未検証）

**条件分岐の挙動差異は設計書に明示する** — 表示有無・省略ルール・エージェント別差異を実装者の判断に委ねない。監査機構と監査対象を同時新設する場合はドッグフーディング手順を設計に含める。（sprint-23-design-001, sprint-26-reliability-001）

## みゆきち（レトロ）

**タスク notes に複数の実施事項がある場合は、done 前に原文を再読して全件照合する**（sprint-26-process-003）

## 全エージェント

**品質ゲートのクエリ・スクリプト・設計書サンプルは実データで一度実行してから確定する** — jq のフィールド名、集計スクリプト、Bash サンプル（`bash -n`）を記憶で書いて「動くはず」で確定させない。JSONL 等ストリーミング形式の集計は重複パターンを実データで先に確認する。偽陽性PASSを見逃したまま運用するのが最悪の結末。（sprint-26-process-002 — sprint-08-tooling-001 / sprint-24-tooling-001 / sprint-25-tooling-002 の一般化）

**タスク完了後は `queue.sh done` を即時実行する** — 完了報告のみで queue 更新を後回しにすると後続タスクの依存チェックがブロックされる。メインセッションの先行完了タスクも即座に `_queue.json` へ反映する。（sprint-24-planning-001, sprint-25-process-001）

**スプリント完了の定義にレトロ完了を含める** — 全タスク DONE で即みゆきちを起動し、retro 完了までスプリントを閉じない（Stopフックの警告は最後の防衛線であり、これに頼らない）。（sprint-07-process-001, sprint-11-process-001, sprint-22-process-001）

**Claude Code に Cron フックは存在しない** — 定期実行は Stop フック等で代替する設計を前提にする。（sprint-21-tooling-001, scope: global）

---

*このファイルは retro エージェント（みゆきち）が `priority_score >= 3` かつ `enforcement != code` の新規 lesson を追加するたびに更新されます。*
*初回棚卸し: 2026-08-08（983行 → 本版。削除ルールの経緯は `_lessons.json` に全件保存）*
*最終更新: sprint-27 / 2026-08-08*

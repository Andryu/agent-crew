# pm-learned-rules.md — Yuki スプリント計画時参照ルール集

> このファイルは `~/.claude/_lessons.json` に記録された教訓から自動変換されたルール集です。
> スプリント計画前に必ず読み込み、該当ルールをタスク設計に反映してください。
> 対象: `status: open` かつ `priority_score >= 3` のエントリ

---

## フォーマット定義

各ルールは以下の形式で記述します。

```
## [エージェント名] ルールタイトル
- lesson_id: <id>
- priority: <score> / sprint: <sprint>

**やること**
<具体的な行動指針>

**やってはいけないこと**  ← 禁止行動が明確な場合は必須。禁止行動が特定できない場合は省略可。
<禁止行動>

**エビデンス**
<再発防止の根拠となった出来事>
```

---

## ルール一覧

---

## [Yuki] スプリント計画時に _lessons.json の高優先度教訓を確認する

- lesson_id: agent-crew-sprint-09-process-002
- priority: 6 / sprint: sprint-09

**やること**

スプリント計画を立てる前に、`~/.claude/_lessons.json` を読み込み、`priority_score >= 6` かつ未解決（`status` なし or `open`）のエントリを確認する。確認した改善アクションを今スプリントのタスク設計に反映する。

反映が不要と判断した場合でも、その理由をスプリント計画案の「確認事項」セクションに記載すること。

**やってはいけないこと**

`_lessons.json` を参照せずにタスク分解を始める。

**エビデンス**

Sprint-08 retro で記録した `engineer-go 停止対策` が Sprint-09 計画に未反映で、2スプリント連続で同一障害が再発した（agent-crew-sprint-09-process-002）。

---

## [Yuki] Riku への L タスクは 1スプリント 1件まで

- lesson_id: agent-crew-sprint-11-reliability-001
- priority: 4 / sprint: sprint-11

**やること**

Riku 担当の complexity `L` タスクは 1スプリントにつき 1件を上限とする。2件以上になる場合は M×2 に分割するか、スコープを次スプリントへ持ち越す。

**やってはいけないこと**

Riku に complexity `L` タスクを2件以上同一スプリントで割り当てる。

**エビデンス**

Sprint-11 で L タスク連続処理後に Riku がレート制限に到達し、後続引き継ぎがメインセッション代行になった（agent-crew-sprint-11-reliability-001）。

---

## [Yuki] engineer-go への委譲前にトークン数を推定する

- lesson_id: agent-crew-sprint-09-process-001
- priority: 9 / sprint: sprint-09

**やること**

engineer-go サブエージェントへの実装指示は **2,000 トークン以下** を目安に作成する。実装指示が長くなる場合は、関係する関数部分のみ抜粋して渡す。complexity `L` のタスクは complexity `M` × 2 に分割してから委譲する。

**やってはいけないこと**

queue.sh 全体など大きなファイルをそのまま実装指示に含める。

**エビデンス**

Sprint-08・Sprint-09 と2スプリント連続で engineer-go が無応答停止し、親 Claude が直接実装した。コンテキストウィンドウ超過が根本原因と推定（agent-crew-sprint-09-process-001, agent-crew-sprint-08-reliability-001）。

---

## [Yuki] engineer-go 無応答停止パターン（根本原因分析済み）

- lesson_id: agent-crew-sprint-08-reliability-001
- priority: 6 / sprint: sprint-08

**やること**

engineer-go へ委譲するタスクは、実装指示を 2,000 トークン以下に分割する。queue.sh 全体を渡さず関係する関数部分のみ抜粋する。complexity `L` タスクは `M` × 2 に分割してから委譲する。

**やってはいけないこと**

長大な実装指示（queue.sh 全体 + 詳細指示）を一括で engineer-go に渡す。

**エビデンス**

Sprint-08 の `signals-impl` タスクで engineer-go を Agent tool 起動したが `[Tool result missing due to internal error]` で無応答停止し、親 Claude が直接実装した（Issue #64）。コンテキストウィンドウ超過またはタイムアウトが根本原因と推定（agent-crew-sprint-08-reliability-001）。

---

## [Yuki] 前スプリントの実装完了状態を計画前に突合する

- lesson_id: agent-crew-sprint-10-process-001
- priority: 4 / sprint: sprint-10

**やること**

計画前チェックリストに「前スプリントの DONE タスクの実装状態を確認し、計画済みだが未実装・実装済みだが未計画の両方を洗い出す」ステップを実行する。

start → done が 60秒未満のタスクがある場合は計画重複を疑って調査する。

**エビデンス**

Sprint-10 の `delegate-impl` は Sprint-09 で実装済みだったが計画に再び含まれ、実装着手後に発覚した。`_signals.jsonl` で start→done が 5秒（23:13:39→23:13:44）と記録されていた（agent-crew-sprint-10-process-001）。

---

## [Yuki] 各 Issue の着手条件を計画時に確認する

- lesson_id: agent-crew-sprint-13-process-001
- priority: 6 / sprint: sprint-13

**やること**

各 Issue の着手条件（前提条件・制約）を実装開始前に確認する。条件未成立の場合はスキップして Yuki へ報告する。`_queue.json` の `notes` フィールドに着手条件を転記する。

**やってはいけないこと**

Issue 本文の「着手条件」「前提条件」セクションを読まずにタスクを READY_FOR_RIKU に設定する。

**エビデンス**

Sprint-13 で Issue #82（マルチプロダクト対応）が「単体プロジェクト安定後に着手」と明記されていたにもかかわらず実装され、パイプラインが停止した。PR #84 クローズ・PR #85 再作成の手戻りが発生（agent-crew-sprint-13-process-001）。

---

## [Yuki / みゆきち] engineer-go 調査結果の対処方針を実装に反映する

- lesson_id: agent-crew-sprint-12-reliability-001
- priority: 6 / sprint: sprint-12

**やること**

`docs/spec/engineer-go-investigation.md` に記載された対処方針（即時対応: engineer-go.md への参照ファイル制限ルール追記・委譲チェックリスト追記）を実装し、Issue #64 をクローズする。

**やってはいけないこと**

調査結果（設計書）が完成した後も対処方針の実装を先送りし続ける。

**エビデンス**

Sprint-08/09/10/11/12 と5スプリント連続で engineer-go 停止対策が未実装のまま。設計書（engineer-go-investigation.md）は Sprint-12 で完成済みだが実装が着手されていない（agent-crew-sprint-12-reliability-001、Issue #64）。

---

## [Riku] 実装前に計画文書と ADR/設計書の仕様値を突合する

- lesson_id: agent-crew-sprint-05-qa-001
- priority: 3 / sprint: sprint-05

> 注: このエントリは priority:2 から priority:3 相当として扱う（初版混入を Sprint-14 で修正）

**やること**

実装着手前に、タスクの `notes` に記載された設計書・ADR を読み込み、計画文書との仕様値の齟齬がないか確認する。不一致がある場合は実装を止めて Yuki へ報告する。

**エビデンス**

Sprint-05 の `token-opt-qa` で、計画文書（Bash 上限 5回）と ADR-004（3回）の数値齟齬が QA で検出されて差し戻しが発生した（agent-crew-sprint-05-qa-001）。

---

## [Riku] PR Test Plan チェックリストを記入してから PR を作成する

- lesson_id: agent-crew-sprint-05-process-001
- priority: 6 / sprint: sprint-05

**やること**

PR 作成前に Test Plan チェックリストが記入されているか確認する。QA 確認済みの項目はチェック済みで提出する。

**やってはいけないこと**

Test Plan を空欄または未チェックのまま PR を作成する。

**エビデンス**

Sprint-04・Sprint-05 と2スプリント連続で Test Plan チェック漏れをオーナーに指摘された（agent-crew-sprint-05-process-001）。

---

## [Riku] スプリント完了後はオーナー確認なしにコミット・PR 作成してよい

- lesson_id: agent-crew-sprint-05-process-002
- priority: 4 / sprint: sprint-05

**やること**

スプリント完了後は自動フローに従い、オーナー確認なしで `git commit` → `git push` → `gh pr create --draft` を実行する。

**やってはいけないこと**

コミットや PR 作成の可否をオーナーに確認する（介入最小化違反）。

**エビデンス**

Sprint-05 完了後にコミット可否をオーナーに確認し、介入最小化違反と指摘された（agent-crew-sprint-05-process-002）。

---

## [Sora] Bash が利用できない場合は CHANGES_REQUESTED を返す

- lesson_id: agent-crew-sprint-11-reliability-002
- priority: 6 / sprint: sprint-11

**やること**

Bash が実行できない環境では、テスト実行なしで APPROVED を返してはいけない。`CHANGES_REQUESTED（REASON: BASH_UNAVAILABLE）` を返し、Bash 実行可能な環境での再確認を求める。

**やってはいけないこと**

Bash 不可の場合にスモークテストを静的検証に差し替えて黙って APPROVED を返す。

**エビデンス**

Sprint-11 で Sora が Bash 実行上限でスモークテストを静的検証に差し替えて APPROVED を返し、Sprint-08 issue の QA 形骸化が再発した（agent-crew-sprint-11-reliability-002）。

---

## [Sora] スプリント完了時はレトロ（みゆきち）を起動する

- lesson_id: agent-crew-sprint-11-process-001
- priority: 8 / sprint: sprint-11

**やること**

全タスク DONE の完了報告末尾に `@retro` を含め、みゆきち（retro エージェント）を起動する。

**やってはいけないこと**

レトロ起動なしでスプリント完了を報告する。

**エビデンス**

5スプリント連続でレトロ起動がスキップされた。pm.md への記載では効果がなく、Sora 自身のエージェント定義への直接埋め込みが必要と確定した（agent-crew-sprint-11-process-001）。

---

## [Sora] QA タスクでは実際にテストを実行し、結果を summary に記録する

- lesson_id: agent-crew-sprint-08-process-001
- priority: 4 / sprint: sprint-08

**やること**

QA タスクの notes に記載されたテスト手順を実際に実行し、その結果を summary に記録する。テスト実行なしの DONE は CHANGES_REQUESTED 扱いとする。

**エビデンス**

Sprint-08 の `signals-qa` の summary が `test` のみで、QA の実施内容が不明なまま DONE になり、シグナルのバグが残存した（agent-crew-sprint-08-process-001）。

---

## [Alex] Bash コードサンプルを設計書に含める場合は bash -n でバリデーションする

- lesson_id: agent-crew-sprint-08-tooling-001
- priority: 9 / sprint: sprint-08

**やること**

設計書に含まれる Bash コードサンプルは `bash -n <file>` または実行でバリデーションを行う。`${...}` 展開を含むコードは特に要注意。サブシェル内で `set +e` を先行させ `jq -cn --argjson` を使ってデフォルト値を渡すパターンを標準とする。

**やってはいけないこと**

`${4:-{}}` など、シェルが `}` を誤解釈する構文を設計書のサンプルコードに含める。

**エビデンス**

Sprint-08 で `${4:-{}}` 構文のバグが含まれた設計書サンプルを Riku がそのままコピーし、JSON が破損した。`set -e + || true` の組み合わせでサイレントに失敗し、Sprint-08 の大半のシグナルが記録されなかった（agent-crew-sprint-08-tooling-001）。

---

## [全エージェント] セッション中断リスクへの対策

- lesson_id: agent-crew-sprint-05-reliability-001
- priority: 4 / sprint: sprint-05

**やること**

長時間タスク（L タスク・夜間処理）は作業ブレイクポイントを設計し、中断後に再開できるよう状態を `_queue.json` に記録する。

**エビデンス**

深夜セッション完了後の約8時間ブレイク中にスマホ RemoteControl のスリープで接続が切断され、Sora が内部エラーで落ちた（agent-crew-sprint-05-reliability-001）。

---

## [全エージェント] みゆきちはスプリント完了ごとに必ず起動する

- lesson_id: agent-crew-sprint-07-process-001
- priority: 6 / sprint: sprint-07

**やること**

スプリント完了時は Yuki がみゆきち（retro エージェント）を起動してレトロスペクティブを実施する。完了メッセージのテンプレートに `@retro` 呼び出しを含める。

**エビデンス**

Sprint-06 で「みゆきち自動起動を pm.md に明文化した」にもかかわらず Sprint-07 完了時に実行されず、振り返りが欠落した。sprint-07 のレトロファイルが存在しない（agent-crew-sprint-07-process-001）。

---

## [全エージェント] _signals.jsonl の書き込みを最初のタスク完了後にスモークテストする

- lesson_id: agent-crew-sprint-09-tooling-001
- priority: 4 / sprint: sprint-09

**やること**

各スプリント開始後の最初のタスク完了時に Sora が `_signals.jsonl` の存在と内容を確認するスモークテストを実施する。

**エビデンス**

Sprint-08 の emit バグ修正後も `_signals.jsonl` が Sprint-09 終了時点で存在せず、retro 分析の観察精度が低下した（agent-crew-sprint-09-tooling-001）。

---

## [Alex] サブエージェントコンテキストでの Bash 利用可否を委譲前に確認する

- lesson_id: agent-crew-sprint-05-tooling-001
- priority: 4 / sprint: sprint-05

**やること**

Alex がサブエージェントとして実行される場合の Bash 利用可否を委譲前に確認する。Bash が使えない場合は Yuki へ報告する。

**エビデンス**

Sprint-05 で Alex への Bash 付与後、トップレベルコンテキストでは機能したが、サブエージェントコンテキストでは Bash が利用できなかった（agent-crew-sprint-05-tooling-001）。

---

## [全エージェント] みゆきちはスプリント完了後に毎回呼ぶ（繰り返し注意）

- lesson_id: agent-crew-sprint-05-process-003
- priority: 3 / sprint: sprint-05

**やること**

Yuki のスプリント完了手順の末尾に必ず「みゆきちを呼んでレトロスペクティブを実施」を含める。

**エビデンス**

Sprint-03 以降3スプリント連続でオーナーが手動でみゆきちを依頼した（agent-crew-sprint-05-process-003）。

---

## [みゆきち] pm-learned-rules.md 更新時は priority フィルタを必ず確認する

- lesson_id: agent-crew-sprint-14-process-001
- priority: 4 / sprint: sprint-14

**やること**

`pm-learned-rules.md` に lesson を追記する前に、`jq '.lessons[] | select(.priority_score >= 3)'` で対象を絞り込む。追記後は全エントリの priority 値を確認し、`priority < 3` のエントリが混入していないかチェックする。

**やってはいけないこと**

フィルタ確認なしで lesson を変換し pm-learned-rules.md に追記する。

**エビデンス**

Sprint-14 の pm-learned-rules.md 初版に `agent-crew-sprint-05-qa-001`（priority:2）が混入し、Sora QA MINOR 指摘として検出された（agent-crew-sprint-14-process-001、Issue #89）。

---

## [みゆきち] pm-learned-rules.md の「やってはいけないこと」セクション統一ルール

- lesson_id: agent-crew-sprint-14-process-002
- priority: 3 / sprint: sprint-14

**やること**

ルールに禁止行動が明確に特定できる場合は「やってはいけないこと」セクションを必須とする。禁止行動が特定できない場合は省略可とし、省略した場合はフォーマット定義のコメントに従っていることを認識した上で省略する。

**エビデンス**

pm-learned-rules.md 初版で「やってはいけないこと」セクションが一部ルール（Lタスク上限・engineer-go委譲等）で省略されており、統一ルールが未定義だった。Sora QA MINOR 指摘として検出された（agent-crew-sprint-14-process-002）。

---

## [全エージェント] Bash 許可パターンは相対パスのみ一致する

- lesson_id: agent-crew-sprint-15-tooling-001
- priority: 4 / sprint: sprint-15

**やること**

settings.json の `permissions.allow` に登録する Bash パターンは相対パス形式（`scripts/xxx.sh *`）で記述すること。スプリント開始前にパターン形式が相対パスになっているか確認する。

**やってはいけないこと**

絶対パス（`/Users/...`）で Bash 権限パターンを設定する。相対パスで機能していても絶対パスは一致しないため、サブエージェントから実行されるコマンドが権限拒否になる。

**エビデンス**

Sprint-15 開始直後に Bash コマンドが絶対パスで拒否された。設定を相対パスに変更することで即時解消した（agent-crew-sprint-15-tooling-001）。

---

## [Yuki] retro フェーズで使用するスクリプトを permissions.allow に事前登録する

- lesson_id: agent-crew-sprint-15-tooling-002
- priority: 4 / sprint: sprint-15

**やること**

スプリント開始前に `scripts/lessons.sh` など retro フェーズで使うコマンドが `permissions.allow` に含まれているか確認する。未登録の場合はスプリント開始時に追加する。

**やってはいけないこと**

retro フェーズで使用するスクリプトを `permissions.allow` に未登録のままスプリントを開始する。

**エビデンス**

Sprint-15 の retro フェーズで `scripts/lessons.sh` が `permissions.allow` に未登録であり、`lessons.sh add` が実行できなかった。DECISIONS.md での代替記録で対応した（agent-crew-sprint-15-tooling-002）。

---

*このファイルは retro エージェント（みゆきち）が `priority_score >= 3` の新規 lesson を追加するたびに更新されます。*
*最終更新: sprint-16（Yuki/Riku追記） / 2026-04-26*

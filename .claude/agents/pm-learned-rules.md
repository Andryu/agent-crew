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

## [Yuki] フック実装タスクに必要な権限を計画時に settings.json へ事前登録する

- lesson_id: agent-crew-sprint-17-tooling-001
- priority: 6 / sprint: sprint-17

**やること**

フック実装タスクをキューに積む際、`notes` に必要権限（`Write(**)`・`Bash(chmod *)`・`Bash(bash *)`）を明記し、スプリント開始前に `settings.json` の `permissions.allow` に追加しておく。

**やってはいけないこと**

フック実装タスクを計画する際に権限要件を洗い出さず、実行時に権限拒否で手動追記対処する。

**エビデンス**

Sprint-17 で `Write(**)`・`Bash(chmod *)`・`Bash(bash *)` が `settings.json` に未登録だったため、Yuki が hook-impl タスク中に2回権限拒否ブロックに遭遇した。settings.json への手動追記で対処した（agent-crew-sprint-17-tooling-001、Issue #100）。

---

## [全エージェント] _queue.json への状態記録はレート制限中断後の再開耐性を高める

- lesson_id: agent-crew-sprint-17-reliability-001
- priority: 3 / sprint: sprint-17

**やること**

各タスク完了時に `_queue.json` の status・summary・events を確実に記録する。レート制限中断後の再開時に、完了済みタスクを重複実行しないために状態記録が必要。

**エビデンス**

Sprint-17 でレート制限による一時中断が発生したが、`_queue.json` の状態記録により重複作業なく再開できた。全タスク retry_count=0（agent-crew-sprint-17-reliability-001）。

---

## [みゆきち] Issue 作成前に issue_url の重複チェックを実施する

- lesson_id: agent-crew-sprint-18-process-001
- priority: 4 / sprint: sprint-18

**やること**

retro の Issue 作成手順（ステップ4）で `gh issue create` を実行する前に、`_lessons.json` の `issue_url` が null であることを確認する。null でない場合は Issue 作成をスキップする。

**やってはいけないこと**

同一 lesson_id に対して `issue_url` の確認なしに `gh issue create` を複数回実行する。

**エビデンス**

Sprint-18 で agent-crew-sprint-17-tooling-001 から Issue #99 と #100 が二重生成された。retro.md に重複チェックステップが欠如していたことが根因（Sprint-18 で #99 をクローズして対処）。

---


## [全エージェント] Claude Code に Cron フックは存在しない — Stop フックを定期実行代替として使う

- lesson_id: agent-crew-sprint-21-tooling-001
- priority: 4 / sprint: sprint-21

**やること**

定期実行を必要とする機能を設計する際は、Claude Code の利用可能なフックタイプ（Stop/PreToolCall/PostToolCall 等）を事前にリサーチし、Cron 相当機能がないことを前提に設計する。Stop フックはセッション終了時に実行されるトリガーとして利用可能。

**やってはいけないこと**

Cron フックの存在を前提に定期実行処理を設計する（Cron フックは Claude Code に存在しない）。

**エビデンス**

Sprint-21 でリサーチエージェント（Alex/Yuki/Guide）の並列調査により発見。Cron フックが存在しないことを事前確認し、Issue #108 の privacy-check 実装で Stop フックを代替採用した（agent-crew-sprint-21-tooling-001）。

---

## [Yuki / Sora] スプリント完了の定義にレトロ完了を含める

- lesson_id: agent-crew-sprint-22-process-001
- priority: 6 / sprint: sprint-22

**やること**

スプリント完了の定義に「みゆきちによる retro 完了」を明示的に含める。全タスク DONE になったら即座にみゆきちを起動し、retro 完了を確認してからスプリントを DONE とする。エージェント定義（Sora の @retro ルール）が実際に機能しているか定期的に確認する。

**やってはいけないこと**

全タスク DONE になった後、retro を実施せずにスプリントを終了する。「pm-learned-rules.md に記載されているから大丈夫」と判断し、エージェント定義の直接確認を省略する。

**エビデンス**

Sprint-22 で QA_APPROVED_WITH_NOTE で全タスク完了したにもかかわらず、みゆきちが起動されなかった。Sprint-23 で sprint22-retro タスクが補完タスクとして登録された（agent-crew-sprint-22-process-001）。Sprint-07 でも同一パターンが発生しており、複数スプリントを経て再発（agent-crew-sprint-07-process-001）。

---

## [Yuki] APPROVED_WITH_NOTE の NOTE 内容をスプリント完了条件に含める

- lesson_id: agent-crew-sprint-22-tooling-001
- priority: 4 / sprint: sprint-22

**やること**

QA が APPROVED_WITH_NOTE で完了した場合、NOTE の内容（手動セットアップ手順など）をスプリント完了条件に明示する。NOTE 内容が未実施のままスプリントを終了しない。フック実装で install.sh オプションを追加した場合は、QA タスクの notes に「install.sh --only=global-hooks を実際に実行して ~/.claude/settings.json を確認する」テスト手順を記載する。

**やってはいけないこと**

APPROVED_WITH_NOTE を APPROVED と同等に扱い、NOTE 内容の実施確認なしにスプリントを終了する。

**エビデンス**

Sprint-22 で capture-learning.sh / aggregate-learnings.sh を実装したが、~/.claude/settings.json への SubagentStop/Stop フック登録が手動セットアップ必須のまま残り、Sprint-23 の積み残しタスクとなった（agent-crew-sprint-22-tooling-001）。

---

## [Yuki] スプリント計画時に担当者の負荷分散スコアを事前計算する

- lesson_id: agent-crew-sprint-23-planning-001
- priority: 6 / sprint: sprint-23

**やること**

担当者ドラフトを作成した後、rubric 負荷分散スコア（最多担当数 / 平均担当数）を事前計算する。スコアが 2.0 を超える場合、Riku 担当の S/M タスクを Alex（設計系）・みゆきち（retro 系）・Sora（QA 系）へ再配分する。Riku の担当比率が全タスクの50%を超える場合は必ず再配分を検討する。

**やってはいけないこと**

「実装タスクは Riku が適任」という暗黙の想定のまま担当者を決定し、負荷分散スコアを確認しない。

**エビデンス**

Sprint-23 でタスク7件中4件が Riku に集中し、負荷分散スコア 2.29（基準 <=2.0）で FAIL となった。permissions-allow-fix(S)・rubric-pm(S) は他エージェントへの再配分が可能だった（agent-crew-sprint-23-planning-001）。

---

## [Alex / Riku] 設計書には条件分岐ごとの挙動差異を明示し、実装前にレビューする

- lesson_id: agent-crew-sprint-23-design-001
- priority: 4 / sprint: sprint-23

**やること**

設計書（docs/spec/*.md）を作成する際は、条件分岐を含む挙動の差異（表示有無・省略ルール・エージェント別の処理差など）を明示的に記述する。Riku が実装に着手する前に Alex が設計書をレビューし、dead code が生じうるケースや挙動の非一貫性を事前に検出する。

**やってはいけないこと**

条件分岐の挙動差異を設計書に記述せず、実装者の判断に委ねる。

**エビデンス**

Sprint-23 の build_retry_message 実装で、Yuki 系エージェントのみ retry_count 表示を省略し他は表示する非一貫な実装が混入した。設計書（slack-persona.md）に省略ルールが明記されていなかったことが根因で、Sora QA MINOR 指摘として検出された（agent-crew-sprint-23-design-001）。

---

## [Yuki] メインセッションの先行完了タスクは即座に_queue.jsonへ反映する

- lesson_id: agent-crew-sprint-24-planning-001
- priority: 4 / sprint: sprint-24

**やること**

メインセッション（Fable）が計画立案と並行してタスクを実装する場合は、着手・完了のタイミングで `_queue.json` の該当タスクへ `assigned_to`・`status` を即時反映する。Yukiは計画生成の最初のステップで `_queue.json` の既存状態（進行中/完了マーク）を必ず確認してから担当割当を行う。

**やってはいけないこと**

`_queue.json` の既存状態を確認せずに担当者ドラフトを作成し、既に完了済みのタスクを他エージェントへ再割当する。

**エビデンス**

Sprint-24 でFableが計画立案と並行して4タスクを先行完了させたが、Yukiはこれを把握せずcoo-personaをRikuに割り当てる担当割衝突が発生し、後追い修正のコストが生じた（agent-crew-sprint-24-planning-001）。

---

## [Yuki] 負荷分散スコアは計画外の先行完了タスクを含めた全体で計算する

- lesson_id: agent-crew-sprint-24-planning-002
- priority: 4 / sprint: sprint-24

**やること**

負荷分散スコア（最多担当数 / 平均担当数）は、計画外の先行完了タスクを含むスプリント内の全タスク・全エージェントを対象に計算する。特定タスクを除外して計算する場合は、除外理由とともに除外前後両方のスコアを併記する。

**やってはいけないこと**

計画外の先行完了タスクを除外した「残タスクのみ」のスコアだけでPASS判定を確定させる。

**エビデンス**

Sprint-24 で残タスクのみの負荷分散スコアは1.6（PASS）と算出されたが、Fableの先行完了分を含む全体（9タスク・5エージェント）で再計算すると2.22（FAIL）だった（agent-crew-sprint-24-planning-002）。

---

## [全エージェント / Sora] 複数文書にまたがる整合性はQAが横断的に確認する

- lesson_id: agent-crew-sprint-24-design-001
- priority: 6 / sprint: sprint-24

**やること**

文書に「〜している」「〜で稼働中」等の現在形で仕組みの稼働を示唆する記述を書く場合、著者は該当の仕組みが実際に実装・稼働しているかを確認する。QAは関連する全文書を横断して読み、Enforcement等の記述の実在性と、文書間の連携（一方が規定した伝達に対向文書に受け口があるか）を確認するチェック項目を持つ。

**やってはいけないこと**

単一文書のみをレビューして、複数文書にまたがる整合性（実在性・対向文書の受け口）の確認を省略する。

**エビデンス**

Sprint-24 の sprint24-qa で、constitution.md第3条のEnforcementに実在しない仕組みを稼働中として記載していた点と、weekly-council.mdの伝達規定にpm.md側の受け口がなく片方向連携になっていた点がMAJOR指摘として検出された。いずれも著者本人には気づきにくく、QAで初めて発見された（agent-crew-sprint-24-design-001）。

---

## [全エージェント] ストリーミング形式データの集計は実データで重複パターンを先に確認する

- lesson_id: agent-crew-sprint-24-tooling-001
- priority: 4 / sprint: sprint-24

**やること**

JSONLやログなど、ストリーミング形式で書き出されるデータを集計するスクリプトは、実装前に実データのフィールド構造・重複パターンを確認してからスキーマを設計する。実装後は必ず実データで実行し、レコードの重複（途中経過行の重複合算等）による水増しが発生していないかを検証する。

**エビデンス**

Sprint-24 でRenがtoken-report-scriptの実データ調査により、JSONLのストリーミング途中経過行を単純合算するとトークン消費が2〜5倍水増しされる落とし穴を発見し、message.id重複排除で回避した。想像でスキーマを設計せず実データを先に確認したことが功を奏した（agent-crew-sprint-24-tooling-001）。

---

## [みゆきち] macOS環境ではflockの代わりにmkdirロックを使う

- lesson_id: agent-crew-sprint-24-tooling-002
- priority: 6 / sprint: sprint-24

**やること**

`_lessons.json` への書き込み時、実行環境がmacOS（darwin）の場合は `flock` コマンドが存在しないため、`mkdir` による排他ロック（ロック取得: `mkdir ~/.claude/_lessons.json.lockdir`、解放: `rmdir`）にフォールバックする。事前に `which flock` で存在確認してから手順を選択する。

**やってはいけないこと**

`flock` コマンドの存在を確認せずにレトロ手順をそのまま実行し、ロック取得失敗を放置する。

**エビデンス**

Sprint-24 のレトロで `flock -x -w 10 200` 実行時に `flock: command not found` が発生した。darwin標準環境にはflockが同梱されておらず、brewにも未インストールだった（agent-crew-sprint-24-tooling-002）。

---

## [Riku] symlink/ファイル配布系の新関数は自己参照ガードと上書き防止を実装し、実機実行でQAする

- lesson_id: agent-crew-sprint-25-reliability-001
- priority: 6 / sprint: sprint-25

**やること**

install.sh 等でシンボリックリンクを生成する新規関数を書く場合、①配布先が自分自身（呼び出し元リポジトリ）のパスと一致しないかの自己参照ガード、②配布先に同名ファイル/ディレクトリが既に存在する場合の上書き前チェック、の2点を必ず実装する。実装後は必ず実機実行（scratchpad等への疑似配布先複製 + 実際のコマンド実行）でQAし、コードレビューのみで済ませない。

**やってはいけないこと**

symlink生成・ファイル配布系のコードをコードレビューのみでAPPROVEし、実際にコマンドを実行した検証を省略する。

**エビデンス**

Sora QAがscratchpadにtemplates/department/を複製しinstall.shを実際に実行したところ、自己参照ガード欠如とsymlink_file相当の関数の上書き無防備という2件のCRITICALバグが検出された。コードレビューだけでは気づかれていなかった（agent-crew-sprint-25-reliability-001）。

---

## [みゆきち] mkdir等のディレクトリロックは、trapをリソース取得成功後に設定し、解放時は所有権チェックを行う

- lesson_id: agent-crew-sprint-25-tooling-001
- priority: 6 / sprint: sprint-25

**やること**

mkdirベースの排他ロックを実装する際は、①`trap release_lock EXIT INT TERM` は `acquire_lock` が成功した後にのみ設定する、②`release_lock` 内で `$LOCKDIR/pid` 等の所有権情報が自分の `$$` と一致する場合のみ削除する二重防御を組み込む。

**やってはいけないこと**

ロック取得の成否が確定する前にtrapで解放処理を仕込む。これをやると、取得タイムアウト時にtrapが発火し、他プロセスが正当に保持しているロックを削除してしまう。

**エビデンス**

Sora QAが2プロセス競合（Aがロック保持中にBが取得を試みてtimeoutする）を実機再現し、Bのtimeout後にAのロックが削除されることを確認した。trapをacquire_lock成功後に移動し、release_lockに所有権チェックを追加した修正後は同シナリオで正しく動作することをみゆきちが再現テストで確認した（agent-crew-sprint-25-tooling-001。agent-crew-sprint-24-tooling-002のflock→mkdir移行を完了させる過程で発覚）。

---

## [全エージェント] タスク完了後は scripts/queue.sh done を即時実行する（再発防止の再徹底）

- lesson_id: agent-crew-sprint-25-process-001
- priority: 6 / sprint: sprint-25

**やること**

実装タスクが完了したら、次の作業や完了報告に進む前に必ず `scripts/queue.sh done <slug> <agent> "<summary>"` を実行し、`_queue.json` を実態に即時同期させる。完了報告には「queue.sh done 実行済み」であることを明記する。

**やってはいけないこと**

タスク実装完了後、queue更新を後回しにしたままteam-leadへの完了報告のみで済ませる。他タスクの `depends_on` チェックがブロックされ、後続のQAタスク着手が止まる。

**エビデンス**

Sprint-25でRiku（hq-install-distribution・hq-template-dir）とみゆきち（retro-mkdir-lock・retro-stop-hook）がqueue.sh done未実行のまま完了報告し、Soraのscripts/queue.sh startが依存タスク未完了エラーでブロックされた。agent-crew-sprint-24-planning-001で同様のルールが既に記載されていたにもかかわらず再発した（agent-crew-sprint-25-process-001。agent-crew-sprint-24-planning-001の再発）。

---

## [Yuki] 負荷分散スコアはポイントベース（complexity加重）を公式指標とする

- lesson_id: agent-crew-sprint-25-planning-001
- priority: 4 / sprint: sprint-25

**やること**

スプリント計画時・レトロ時の負荷分散スコアは `scripts/sprint-points.sh` が出力する `load_balance.by_points.score`（最多担当ポイント / 平均ポイント、complexity S=1/M=3/L=5換算）を公式指標として合否判定に用いる。タスク数ベース（`by_task_count.score`）は補助指標として併記するに留める。

**やってはいけないこと**

タスク数ベースのスコアのみを算出して合否判定を確定する。complexityの異なるタスクの負荷差を見落とす。

**エビデンス**

Ren（sprint-points-script実装時）が2つの定義の併存を発見した。Sprint-25計画書のタスク数ベーススコアは1.67（PASS）だったが、ポイントベースでは2.0（合格基準ちょうど）だった。Sora QAがポイントベースを公式指標とすることを推奨し、Sprint-25レトロで正式決定した（agent-crew-sprint-25-planning-001）。

---

## [みゆきち] retro.md内のjqスニペットは必ず実データに対して一度実行してから確定する

- lesson_id: agent-crew-sprint-25-tooling-002
- priority: 4 / sprint: sprint-25

**やること**

retro.md（やその他エージェント定義）にjqクエリ等の実行手順を記載・変更する際は、必ず実際の `_queue.json`（または対象データ）に対して一度実行し、出力が期待通りであることを確認してから確定させる。

**やってはいけないこと**

フィールド名などを記憶や想像で書いたjqクエリを、実行検証なしにドキュメントへ確定させる。

**エビデンス**

retro.mdステップ6の負荷分散スコアjqクエリが `.tasks[].agent` を参照していたが、_queue.jsonの実フィールド名は `.assigned_to` であり、常にLOAD_RATIO=1（偽陽性PASS）を返す不具合がSprint-25レトロで発覚した。過去のレトロでは字面通り実行せず手計算していたため実害は顕在化していなかったと推定される（agent-crew-sprint-25-tooling-002）。

---
*このファイルは retro エージェント（みゆきち）が `priority_score >= 3` の新規 lesson を追加するたびに更新されます。*
*最終更新: sprint-25 / 2026-08-01*

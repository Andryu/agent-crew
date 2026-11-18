# ADR-019: always-on 運用 — 「起きて1歩進めて眠る」run モデルと5プリミティブの割当

- **Status**: Proposed（critic〔Kagami〕の反証を反映後、オーナー承認で Accepted）
- **Date**: 2026-11-18
- **Issue**: なし（オーナー指示: Anthropic「Building always-on agents」を踏まえた開発環境の改善）
- **関連**: ADR-012（スキル配布の正本は一箇所）、ADR-016（フック追加の抑制）、ADR-017 / ADR-018（モデル運用・critic）、`issue-lifecycle-adr.md`（Issue #152 の誤クローズ事故）、`queue-py-adr.md`、`docs/plans/2026-08-24-dual-harness-foundation.md`
- **plan**: `docs/plans/2026-11-18-always-on.md`

> 用語: **run** ＝ イベントで起こされたセッションが行う1回分の作業。**owner** ＝ リポジトリのオーナー（人間）。**unattended run** ＝ owner が見ていない状態で始まる run（スケジュール実行など）。

---

## 背景

### 参照した外部設計

Anthropic の公式ガイド「Building always-on agents」（claude.com, 2026-11-13）は、常時稼働エージェントを「ずっと動くもの」ではなく **「イベントで起きて run を実行し、session に記録して眠る」の反復**として定義し、次の5つの部品を必須とする。

| 部品 | 要点（原文の趣旨） |
|---|---|
| Event inbox | イベントを永続化して受け付け、重複を除く。inbox が唯一の真実源。**inbox ごとにアクティブな worker は1つ** |
| Timers | エージェント自身の follow-up と、定期スケジュールの2種 |
| Memory | **再取得できないものだけを持つ**。他にあるものはポインタで持つ。常時読込は軽く |
| Permissions | 無人でユーザー権限を使うので**最もリスクが高い**。認証情報は環境の外で注入、重要操作は承認制 |
| Outbox | 途中経過は流さず結果だけ。**静かに始め、信頼を得てから注意を引く量を増やす** |

同系統の Claude Code「Projects」（2026-09-17）は coordinator ＋ thread（各 thread は独自ブランチ・独自コピーのクラウドセッション）で並列作業させる。

### agent-crew の現状（2026-11-18 時点、決定的コマンドで確認）

工程の強制（fable-class・critic・学習ループ）は厚いが、**owner 不在時に回る部品がほぼ無い**。

1. **Inbox**: `.claude/_queue.json` と `.claude/_signals.jsonl` は **git 追跡下**（`git ls-files` で確認）。Projects 型の並列ブランチ運用ではマージ衝突源になる。`flock` はマシン内排他でブランチ間には効かない。キューを進める契機は owner の「進めて」のみ。sprint-27（全10件 DONE、最終シグナル 2026-08-02）以降の作業はキューを経由していない。
2. **Timers**: 無い。`.github/workflows/slack-notify.yml` も `workflow_dispatch` のみ。
3. **Memory**: SessionStart が `~/Workspace/Obsidian/...` を必読と表示するが、クラウドコンテナには存在しない（`ls` で確認）。教訓ストア `~/.claude/_lessons.json` もローカル専用。`pm.md` は 506 行。
4. **Permissions**: `.claude/settings.json` の allow に `Bash(bash *)`・`Bash(python3 *)`・`Edit(**)`・`Bash(git push *)` があり、実質無制限。deny は無い。エージェントが自分の `settings.json` を書き換えて権限を広げることも妨げていない。
5. **Outbox**: `subagent_stop.sh` がエージェント完了ごとに Slack 通知する。さらに配布元 `hooks/subagent_stop.sh` と稼働中の `.claude/hooks/subagent_stop.sh` が**双方向にドリフト**している（配布元にだけ人格テンプレートと `jq -n` によるエスケープ、稼働側にだけレトロ NEXT STEP と vault 転記がある。`diff` で 145 行 / 31 行の差）。稼働側は JSON を文字列連結で組むため、メッセージに `"` が入ると壊れる。
6. **観測**: `task_completed.sh` が `type` ではなく `event` キーでシグナルを書いており、182 行中 9 行がスキーマ外（sprint-17/19/26）。`queue.py` のレポート集計は `e['type']` を前提にしているため、該当スプリントで **KeyError** になる（同じ式で再現確認済み）。

---

## テーゼ

> **常時稼働とは「ずっと動く」ことではなく、「状態と権限は run の外に置き、起こされた run は1歩だけ進め、owner の判断が要るものだけを返す」ことである。**

以下の決定はすべてこの一文から導出する。

- 状態が run（ブランチ・セッション）の中にあると、並列 run が衝突し、クラッシュで失われる。→ **Inbox を git の外へ**
- 権限が run の中（エージェントの自己判断・自分で書き換えられる設定）にあると、無人で広がる。→ **Permissions を二層化し、外側を GitHub と環境に置く**
- run が2歩以上進むと、owner が途中で止める機会がない。→ **unattended run は1 run につき1タスク、マージしない、risk high を決めない**
- 判断が要らないものまで返すと、判断が要るものが埋もれる。→ **Outbox は3分類、即時は needs-owner だけ**

---

## 決定

### D1. 5プリミティブの割当

| 部品 | 割当 | 導入フェーズ |
|---|---|---|
| Inbox | **GitHub Issues ＋ `crew:*` ラベル**が真実源。`_queue.json` は Issue から生成する**ローカルの読み取り専用射影**（git 追跡外）に格下げする | Phase 2 |
| Timers | **Claude Code のスケジュール実行**（発火ごとに新規クラウドセッション）。定義は repo 内の宣言ファイルに置き、作成は owner が行う。**エージェント自身が timer を作ることは禁止** | Phase 1 |
| Memory | 3層化（常時 / 必要時 / 外部ポインタ）。存在しない外部パスは表示しない | Phase 0（表示）、方針は本 ADR |
| Permissions | **外側**: main のブランチ保護、クラウド環境のネットワーク制限、秘密情報は環境側で注入。**内側**: allowlist の縮小と deny の新設 | Phase 0 |
| Outbox | 3分類（needs-owner / result / digest）。即時通知は needs-owner だけ | Phase 0（ローカル hook）、Phase 1（クラウド） |

### D2. フェーズ分割

- **Phase 0（土台・振る舞いは対話運用のまま）**: シグナルのスキーマ修正、フックのドリフト解消、Outbox の静音化、Permissions の縮小、Memory 表示の環境適応。新しいフックは追加しない（ADR-016）。
- **Phase 1（timer ＋ 読み取り専用 run）**: run 契約スキルと timer 定義を追加する。unattended run は **コードを書かない**（Issue コメントと digest 出力のみ）。最初の timer は `daily-brief` と `weekly-council` の2本。
- **Phase 2（Issue inbox ＋ 実行 run）**: `queue.py` にバックエンド抽象を入れ、Issue バックエンドを実装する。`inbox-sweep` timer が1 run につき READY を1件だけ処理し、PR を開く（マージはしない）。**Phase 2 は別 plan とし、着手前に改めて critic を通す**（エージェント間プロトコル変更＝強制 high）。

フェーズを分ける理由: Phase 1 は Inbox が `_queue.json` のままでも安全に価値を出せる（読むだけなので衝突しない）。一方、無人で**書く** run は Inbox が git の外に出るまで安全に回せない。

### D3. unattended run の契約（Phase 1 から適用）

1. **1 run 1 歩**: 1回の起動で処理するのは最大1タスク（Phase 1 では1レポート）。
2. **単一 worker**: 同時に動く実行 run は全体で1つまで（Phase 2 で claim ラベルによって強制する。Phase 1 の読み取り run はこの制約の対象外）。
3. **マージしない・main に触らない・timer を作らない**。
4. **risk high の設計判断をしない**: fable-class が critic 必須と判定する局面に来たら、`needs-owner` で停止する。unattended run に従量 API キーは渡さない（ADR-018 の `critic.sh` は対話運用専用のまま）。
5. **曖昧さ・BLOCKED・retry 上限・checkpoint では停止**して needs-owner を出す（README の auto モード停止条件と同じ）。
6. **出力は結果だけ**: 1 run の外部出力は「1件の Issue/PR コメント」または「1件の digest」に限る。

### D4. Outbox の3分類と経路

| 分類 | 例 | 即時性 | ローカル（hook） | クラウド（unattended run） |
|---|---|---|---|---|
| needs-owner | BLOCKED、critic CRITICAL のエスカレーション、checkpoint、承認待ち | 即時 | Slack webhook | スケジュール実行の push 通知 ＋ Issue に `crew:needs-owner` |
| result | スプリント完了、PR が ready | 即時（1日数件まで） | Slack webhook | push 通知 |
| digest | エージェント個別の完了、handoff、retry | 即時に送らない | 標準出力のみ（Slack に送らない） | daily-brief にまとめる |

- **GitHub の通知は owner に届かない**前提で設計する。エージェントは owner の資格情報で動くため、自分の操作は GitHub から自分に通知されない。GitHub 上のラベルは**記録（重複防止・後から一覧できる状態）**であって、プッシュ経路ではない。
- Slack webhook URL をクラウド環境の環境変数に入れない（環境変数は平文保存のため）。クラウドではスケジュール実行の push 通知を使う。

### D5. Permissions の二層化

**外側（エージェントが書き換えられない層。owner 作業）**

- GitHub の main ブランチ保護: PR 必須、force push 禁止、削除禁止。
- クラウド環境: ネットワークは limited のまま。`critic.sh` 用の API キーなど秘密情報をクラウド環境に置かない（unattended run には不要。D3-4）。

**内側（`.claude/settings.json`）**

- allow の縮小: `Bash(bash *)` → `Bash(bash scripts/*)` と `Bash(bash .claude/hooks/*)`、`Bash(python3 *)` → `Bash(python3 scripts/*)`、`Edit(**)` はプロジェクトルート配下に限定。
- deny の新設: force push、main への push、`gh pr merge`、`.env` の読み取り、**自分の権限設定の書き換え**（`.claude/settings.json`・`.codex/hooks.json` の Edit/Write）。
- 内側はパターン照合なので完全ではない（例: `git push origin HEAD:main` の表記揺れ）。**本当の防壁は外側**であり、内側は事故防止と意図の明示と位置づける。

### D6. Memory の3層

| 層 | 中身 | 読み込み |
|---|---|---|
| L0 常時 | `AGENTS.md`、run 契約（Phase 1 以降） | 毎セッション |
| L1 必要時 | `pm-learned-rules.md`、`docs/DECISIONS.md`、ADR | 該当工程で Read |
| L2 外部 | Obsidian、`~/.claude/_lessons.json` | **存在するときだけ**ポインタを表示。クラウドでは「無い」と1行だけ出す |

- unattended run は L2 を前提にしない（クラウドには無い）。unattended run は教訓を書かない（学習ループはローカルの対話運用のままにする。後で改めて検討する）。
- `pm.md`（506 行）の分割は本 ADR の範囲外（別タスク）。

### D7. Inbox（Phase 2 の方向性。詳細は Phase 2 plan で確定）

- 1タスク＝1 Issue（ラベル `crew:task`）。タスクと Issue の対応は、本文の機械可読マーカー `<!-- agent-crew:task {"slug": ...} -->` **だけ**で取る。タイトルや自由記述から推測しない（Issue #152 の再発防止）。
- 状態はラベル `crew:status/<state>`（`ready-<agent>` / `in-progress` / `blocked` / `done`）で表す。イベント履歴はマーカー付きコメント `<!-- agent-crew:event {...} -->` に残す。
- `scripts/queue.sh` の CLI（`start` / `done` / `handoff` / `qa` / `retry` / `block` / `show` / `next`）を**安定インターフェースとして維持**し、バックエンドだけを差し替える。CLI を呼んでいるだけの約 47 ファイルは変更不要にする。`_queue.json` を jq で直接読む約 13 本のスクリプトは、射影ファイルを読み続ければ動く。
- claim: `in-progress` ラベルと claim コメント（run ID と時刻）を付ける。一定時間を過ぎた claim は**自動で奪い返さず** needs-owner にする（二重実行より停止を選ぶ）。
- 未検証の前提: クラウドセッションから `gh` で Issue を書けるか。書けない場合は、同じプロトコルを GitHub MCP ツールで実行する手順を run 契約に書く。**Phase 2 着手の前提条件として検証する。**

---

## 却下した案

| 案 | 却下理由 |
|---|---|
| A. `_queue.json` を維持し、unattended run が main に直接 commit する | テーゼ不適合。状態が branch 上に残り、run が main に触る（D3-3 違反）。並列 thread で衝突する |
| B. 状態専用ブランチ（例: `agent-state`）に `_queue.json` を置き、rebase してリトライ | 衝突は減るが、状態は依然 git 上にあり、push 競合のリトライ制御が必要。owner がスマホから状態を見られず、Outbox の記録先にもならない。セッションに許可されたブランチ以外への push を常時許すことになる |
| C. 外部 DB（Supabase / SQLite サーバ） | ネットワーク許可、認証情報、運用するサーバが新たに要る。個人開発の規模に対して過大 |
| D. GitHub Actions の schedule ＋ claude-code-action で timer を作る | 認証トークンを Actions secrets に置くことになる。Claude Code のスケジュール実行なら push 通知・モデル指定・セッションの監視が最初から付いている。Actions は `deploy-pages.yml` などのコード以外の自動化に留める |
| E. 一気に Phase 2 まで実装する | 強制 high のプロトコル変更に、未検証の前提（クラウドからの `gh` 書き込み）が重なる。Phase 0/1 だけで価値が出るので、段階を分けて失敗の範囲を小さくする |
| F. Outbox に GitHub の通知（mention・assign）を使う | 自分の操作は自分に通知されないため、push 経路にならない（D4） |

---

## 影響とリスク

- **利用枠**: スケジュール実行は発火ごとにフルセッションを消費する。Phase 1 は1日1本＋週1本から始め、増やすときは daily-brief に出る実績で判断する（「静かに始める」）。
- **ダッシュボード（ADR-016）**: クラウドの run は `~/.claude/projects/` に transcript を残さないため、STONEFISH ダッシュボードには映らない。Phase 1 では digest を Issue に残すことで可視性を補う。ダッシュボード側の対応は範囲外。
- **`model-mode.sh`**: クラウドではフック入力にモデル名が来ず `src=none` になり、Pro 運用側へフェイルクローズする（今回のセッションで確認）。unattended run は D3-4 によって risk high で必ず止まるので、安全側に倒れる。ただし過剰に止まる可能性はあるので、Phase 1 の実績で評価する。
- **bench との関係**: `bench/tasks/03-task-completed-hook` は過去の仕様（`event` キー）を正解として固定している。Phase 0 の修正は `type` を**追加する**だけ（`event` は残す）なので、bench の採点を壊さない。

## 検証方法

- Phase 0: plan の DoD（テスト・`jq`・`diff` の生出力）。
- Phase 1: 2週間運用して、(a) daily-brief が owner の判断に使われた回数、(b) needs-owner の誤報数、(c) 利用枠の消費を `weekly-council` に記録する。(a) が2週連続で 0 なら timer を止める（撤退基準）。

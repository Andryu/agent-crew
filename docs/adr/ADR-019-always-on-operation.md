# ADR-019: always-on 運用 — 「起きて1歩進めて眠る」run モデルと5プリミティブの割当

- **Status**: Proposed（v2: critic〔Kagami, opus〕の反証レビュー〔CRITICAL 3・MAJOR 5・MINOR 2、条件付き差し戻し〕を反映済み。オーナー承認で Accepted）
- **Date**: 2026-11-18
- **Issue**: なし（オーナー指示: Anthropic「Building always-on agents」を踏まえた開発環境の改善）
- **関連**: ADR-012（正本は一箇所）、ADR-016（ダッシュボードの transcript 監視）、ADR-017 / ADR-018（モデル運用・critic）、`docs/DECISIONS.md:168`（Issue #152 の誤クローズ事故と `close_issue` フィールド）、`queue-py-adr.md`、`docs/plans/2026-08-24-dual-harness-foundation.md`
- **plan**: `docs/plans/2026-11-18-always-on.md`（critic の指摘と採否も同ファイル）

> 用語: **run** ＝ イベントで起こされたセッションが行う1回分の作業。**owner** ＝ リポジトリのオーナー（人間）。**unattended run** ＝ owner が見ていない状態で始まる run（スケジュール実行など）。

---

## 背景

### 参照した外部設計

Anthropic の公式ガイド「Building always-on agents」（claude.com, 2026-11-13）は、常時稼働エージェントを「ずっと動くもの」ではなく、**「イベントで起きて run を実行し、session に記録して眠る」の反復**と定義する。そのうえで、次の5部品を必須とする。

| 部品 | 要点（原文の趣旨） |
|---|---|
| Event inbox | イベントを永続化して受け付け、重複を除く。inbox が唯一の真実源。**inbox ごとにアクティブな worker は1つ** |
| Timers | エージェント自身が立てる follow-up と、定期スケジュールの2種 |
| Memory | **再取得できないものだけを持ち**、他にあるものはポインタで持つ。常時読み込む量は軽くする |
| Permissions | 無人でユーザー権限を使うので**最もリスクが高い**。認証情報は環境の外で注入し、重要な操作は承認制にする |
| Outbox | 途中経過は流さず結果だけを送る。送った記録を持ち、重複報告を防ぐ。**静かに始め、信頼を得てから注意を引く量を増やす** |

### agent-crew の現状（2026-11-18 時点、決定的コマンドで確認）

工程の強制（fable-class・critic・学習ループ）は厚いが、**owner 不在時に回る部品がほぼ無い**。

1. **Inbox**
   - `.claude/_queue.json` と `.claude/_signals.jsonl` は git 追跡下にある（`git ls-files`）。Projects 型の並列ブランチ運用では衝突の原因になる。`flock` はマシン内の排他で、ブランチ間には効かない。
   - キューを進めるきっかけは owner の「進めて」だけ。sprint-27（全10件 DONE、最終シグナル 2026-08-02）以降の作業はキューを通っていない。
   - なお `queue.py` の `close_linked_issue` はすでに `gh issue close` を実行しており、キューは部分的に GitHub へ書き込んでいる。
2. **Timers**: 無い。`.github/workflows/slack-notify.yml` は Sprint-06 で自動通知を廃止して以来、`workflow_dispatch` のみ。
3. **Memory**
   - settings.json の SessionStart フックが `~/Workspace/Obsidian/...` を「必読」と表示するが、クラウドのコンテナにこのパスは無い。
   - 教訓ストア `~/.claude/_lessons.json` もローカル専用。
   - `pm.md` は 506 行ある。
4. **Permissions**
   - allow に `Bash(bash *)`・`Bash(python3 *)`・`Edit(**)`・`Bash(git push *)` があり、実質無制限。deny は無い。
   - エージェントが `settings.json` や `settings.local.json` を書き換えて、自分の権限を広げることも防げない。
5. **Outbox**
   - **Stop（毎ターンの終了）にも `subagent_stop.sh` が登録されている。** そのうえこのフックは「状態」を見て通知するので、スプリント完了や BLOCKED の状態が続くかぎり、**毎ターン同じ通知を再送する**（stub の curl で3回実行したら3回送信。配布元と稼働側のどちらでも同じ）。
   - 配布元の `hooks/subagent_stop.sh` と稼働側の `.claude/hooks/subagent_stop.sh` が双方向にドリフトしている（`diff` で 145 行と 31 行）。
     - 配布元にだけあるもの: 人格テンプレート、`jq -n` によるエスケープ、差し戻し通知、スプリント完了時の `queue.sh retro --save --decisions` と `graph --save`。
     - 稼働側にだけあるもの: レトロの NEXT STEP、`lessons-to-vault.sh` の呼び出し、文字列連結で組む JSON。
   - 配布元の自動 retro は、稼働側の配置ではパスが解決できず動いていない。一方、配布元の位置から実行すると動き、`docs/retro/` に生成日付きのファイルを書く。
6. **観測**
   - `task_completed.sh` がシグナルを `type` ではなく `event` キーで書いており、182 行中 9 行がスキーマ外になっている（sprint-17/19/26）。
   - `queue.py retro` の集計は `e['type']` を前提にしている。そのため、該当スプリントで `queue.py retro` を直接実行すると KeyError になる（同じ式で再現した。`queue.sh retro` は bash 実装なので影響しない）。

---

## テーゼ

> **常時稼働とは「ずっと動く」ことではない。「状態と権限は run の外に置き、起こされた run は1歩だけ進め、owner の判断が要るものだけを返す」ことである。**

以下の決定はすべてこの一文から導出する。

- **状態を run の外へ**
  - 状態が run（ブランチ・セッション）の中にあると、並列 run が衝突し、クラッシュで失われる。→ Inbox を git の外へ出す。
  - 「送ったかどうか」も状態である。→ Outbox の送信記録も run の外に置く。
- **権限を run の外へ**: 権限が run の中（エージェントの自己判断、自分で書き換えられる設定）にあると、無人のまま広がっていく。→ 制約の主役は外側の層（GitHub・環境）に置き、内側（settings）は事故防止とする。unattended run を始める前に、外側の層が効いていることを確認する。
- **1歩だけ**: run が2歩以上進むと、owner が途中で止める機会がなくなる。→ unattended run は1 run につき1つの成果物とし、マージしない、risk high の判断をしない。
- **判断が要るものだけ**: 判断が要らないものまで返すと、判断が要るものが埋もれる。→ Outbox を3分類し、即時に送るのは needs-owner だけにする。同じものは2度送らない。

---

## 決定

### D1. 5プリミティブの割当

| 部品 | 割当 | フェーズ |
|---|---|---|
| Inbox | **GitHub Issues ＋ `crew:*` ラベル**を真実源とする。`_queue.json` は Issue から生成する読み取り専用の射影（git 追跡外）に格下げする | Phase 2 |
| Timers | **Claude Code のスケジュール実行**（発火ごとに新規クラウドセッション）。定義は repo 内の宣言ファイルに書く。**作成は owner が UI で行い、エージェントは timer を作れない**（D5 の deny で強制） | Phase 1 |
| Memory | 3層化（常時 / 必要時 / 外部ポインタ）。外部メモリは、それがある環境でだけ表示する | Phase 0 |
| Permissions | **外側**: main のブランチ保護、クラウド環境のネットワーク制限、秘密情報を repo の外に置く。**内側**: allowlist の縮小と deny の新設 | Phase 0（Phase 1 の前提条件） |
| Outbox | 3分類。**状態の変化だけを送り、送信記録を run の外に持つ**。needs-owner の主経路は「ラベル → GitHub Actions → Slack」 | Phase 0（ローカル）、Phase 1（クラウド） |

### D2. フェーズ分割

- **Phase 0（土台。振る舞いは対話運用のまま）**
  - シグナルのスキーマ修正
  - フックのドリフト解消（symlink 化）
  - Outbox の重複除去と静音化
  - Permissions の縮小
  - Memory 表示の環境適応
- **Phase 1（timer ＋ 読み取り専用 run）**
  - run 契約スキル、timer 定義、needs-owner と digest の Actions 経路を追加する。
  - unattended run は**コードを書かない**。出力は Issue へのコメントとラベル付与だけ。
  - 最初の timer は **`daily-brief` の1本だけ**。weekly-council は coo.md がファイル書き込みとローカル専用の集計を前提にしているため、Phase 1 では扱わない。
- **Phase 2（Issue inbox ＋ 実行 run）**
  - `queue.py` にバックエンド抽象を入れ、Issue バックエンドを実装する。
  - `inbox-sweep` timer が、1 run につき READY を1件だけ処理して PR を開く（マージはしない）。
  - **Phase 2 は別の plan とし、着手前に改めて critic を通す**（エージェント間プロトコルの変更は強制 high）。

フェーズを分ける理由: Phase 1 は Inbox が `_queue.json` のままでも安全に回せる（読むだけなので衝突しない）。一方、無人で**書く** run は、Inbox が git の外に出るまで安全に回せない。

### D3. unattended run の契約（Phase 1 から適用）

1. **1 run 1 成果物**: 1回の起動で出す成果物は最大1つ（Phase 1 では digest コメント1件。needs-owner のラベル付与は成果物に数えない）。
2. **単一 worker**: 同時に動く「書く run」は全体で1つまで。Phase 2 で claim ラベルによって強制する。Phase 1 の読み取り run は対象外。
3. **マージしない・main に触らない・timer を作らない・作業ツリーを汚さない**: run の最後に `git status --porcelain` が空であることを確かめ、空でなければ needs-owner で終える。
4. **risk high の判断をしない**
   - fable-class・model-mode の Pro 運用表示・`critic.sh` は unattended run には適用しない。
   - 判断が必要になったら needs-owner で止まる。
   - unattended run に従量 API キーは渡さない。
5. **停止条件**: 曖昧さ、BLOCKED、retry 上限、checkpoint のどれかに当たったら停止して needs-owner を出す（README の auto モードの停止条件と同じ）。
6. **冪等性**: 同じ日の digest がすでにあれば何もしない（手動発火と定時発火の重複を防ぐ）。

### D4. Outbox の3分類と経路

| 分類 | 例 | 即時性 | ローカル（フック） | クラウド（unattended run） |
|---|---|---|---|---|
| needs-owner | BLOCKED、critic CRITICAL のエスカレーション、checkpoint、承認待ち | 即時・1件1回 | Slack webhook（送信記録で重複を除く） | Issue に `crew:needs-owner` を付与 → Actions → Slack |
| result | スプリント完了、PR が ready | 即時・1件1回 | Slack webhook（送信記録で重複を除く） | digest にまとめる（Phase 1） |
| digest | エージェント個別の完了、handoff、retry、日次の要約 | 即時には送らない | 標準出力のみ | owner-inbox Issue へのコメント → Actions → Slack（1日最大1件） |

- **送るのは状態ではなく変化**: 送信記録（キー例: `blocked:<slug>:<blockイベントのts>`、`sprint-done:<sprint>`）を、repo の外にある状態ディレクトリに持つ。すでに送ったキーは送らない。
- **GitHub の通知は owner に届かない**: エージェントは owner の資格情報で動くので、自分の操作が GitHub から自分に通知されることはない。一方、GitHub Actions は Issue のラベル付与やコメントを**トリガーとして**受け取れる。Slack の webhook は既存の Actions secret（`SLACK_WEBHOOK_URL`）を使い、Claude の認証情報は Actions に置かない。
- **スケジュール実行の push 通知は補助**: 0件の日にも通知されるかなど、挙動が未確認なので主経路にはしない。T1-4 で実機確認してから、使うかどうかを決める。
- **Sprint-06 の決定（Actions 経由の自動通知を廃止）を、限定的に覆す**: 対象は `crew:needs-owner` ラベルの付与と、owner-inbox Issue への digest コメントだけ。Issue や PR 全般の通知は引き続き行わない。

### D5. Permissions の二層化

**外側（エージェントが書き換えられない層。owner 作業。Phase 1 の前提条件）**

- GitHub の main ブランチ保護: PR 必須、force push 禁止、削除禁止。
- クラウド環境: ネットワークは limited のまま。従量 API キーなどの秘密情報をクラウド環境に置かない。
- 秘密情報は repo の外に置く。repo 内の `.env` は、内側の層では守り切れない（`jq` や `git diff --no-index` で読めてしまう）。

**内側（`.claude/settings.json`）**

- **allow を縮小する**
  - `Bash(bash *)` → `Bash(bash scripts/*)`・`Bash(bash .claude/hooks/*)`・`Bash(bash -n *)`
  - `Bash(python3 *)` → `Bash(python3 scripts/*)`・`Bash(uv run pytest *)`
  - `Edit(**)` → プロジェクトルート配下に限定
- **allow を追加する（unattended run が使う GitHub 操作のみ）**: Issue と PR の一覧・閲覧、Issue へのコメント、ラベル付与。
- **deny を新設する**
  - force push、main への push、PR のマージ（CLI と MCP の両方）
  - GitHub API 経由でのファイル直接書き込み
  - timer を作る・変える・発火させるツール
  - 権限設定の書き換え: `.claude/settings.json`・`.claude/settings.local.json`・`.codex/hooks.json`・`.claude/hooks/**`
- **`scripts/` は deny しない。** このリポジトリの成果物そのものであり、編集を禁じると開発が止まる。代わりに、外側の層（隔離されたクラウドコンテナ、main の保護、limited ネットワーク）で被害の範囲を区切る。Phase 1 の run が書き込みをしていないことは、D3-3 の `git status` 確認で検出する。
- **Codex での unattended run は Phase 1 では扱わない**（Claude 側の deny は Codex に効かないため）。

### D6. Memory の3層

| 層 | 中身 | 読み込み |
|---|---|---|
| L0 常時 | `AGENTS.md`。unattended run では、timer の prompt から run 契約（`.agents/skills/always-on/SKILL.md`）をパス指定で読ませる | 毎セッション |
| L1 必要時 | `pm-learned-rules.md`、`docs/DECISIONS.md`、ADR | 該当する工程で Read |
| L2 外部 | Obsidian、`~/.claude/_lessons.json` | **Obsidian ディレクトリがある環境でだけ**ポインタを表示する |

- 外部メモリがある環境かどうかは、`~/Workspace/Obsidian` があるかで判定する。`~/.claude` の有無では判定しない（クラウドにも存在するため）。
- unattended run は L2 を前提にせず、教訓も書かない（学習ループはローカルの対話運用のままにする）。
- `pm.md` の分割は本 ADR の範囲外。

### D7. Inbox（Phase 2 の方向性。詳細は Phase 2 の plan で確定する）

- **1タスク＝1 Issue**（ラベル `crew:task`）。Issue とタスクの対応は、本文の機械可読マーカー `<!-- agent-crew:task {"slug": ...} -->` **だけ**で取る。タイトルや自由記述から推測しない（Issue #152 の再発防止）。
- **状態**はラベル `crew:status/<state>` で表す。**イベント履歴**はマーカー付きのコメントで残す。既存の `close_issue` による Issue クローズは、このバックエンドに吸収する。
- **`scripts/queue.sh` の CLI は安定インターフェースとして維持し、バックエンドだけを差し替える。**
  - CLI を呼んでいるだけのファイル（隠しディレクトリ以外で約47）は変更しなくてよい。
  - `_queue.json` を jq などで直接読むコード（隠しディレクトリ以外で約13本、`.claude/hooks/` に3本）は、射影ファイルを読み続ければ動く。
- **claim**: claim のラベルとコメントを付ける。期限切れの claim は**自動で奪い返さず**、needs-owner にする（二重実行より停止を選ぶ）。
- **未検証の前提**: クラウドセッションから `gh` で Issue を書けるか。書けない場合は、同じプロトコルを GitHub MCP で実行する。Phase 2 に着手する前提条件として検証する。

---

## 却下した案

| 案 | 却下理由 |
|---|---|
| A. `_queue.json` を維持し、unattended run が main に直接 commit する | テーゼ不適合。状態が branch 上に残り、run が main に触る（D3-3 違反）。並列で衝突する |
| B. 状態専用ブランチ（例: `agent-state`）に `_queue.json` を置き、rebase してリトライする | 状態は依然として git の中にあり、push 競合のリトライ制御が必要になる。owner から見えず、Outbox の記録先にもならない。許可されたブランチ以外への push を常時許すことにもなる |
| C. 外部 DB（Supabase / SQLite サーバ） | ネットワーク許可・認証情報・運用するサーバが新たに必要。個人開発の規模に対して過大 |
| D. GitHub Actions の schedule ＋ claude-code-action で timer を作る | Claude の認証トークンを Actions secrets に置くことになる。timer は Claude Code のスケジュール実行で作る。**Actions は「ラベルやコメントをトリガーにして Slack へ送る」通知の配送にだけ使う**（Claude の認証情報は不要。D4） |
| E. 一気に Phase 2 まで実装する | 強制 high のプロトコル変更に、未検証の前提（クラウドからの `gh` 書き込み）が重なる |
| F. Outbox に GitHub の通知（mention や assign）を使う | 自分の操作は自分に通知されないので、push の経路にならない。ラベルやコメントは「Actions のトリガー」として使う（D4） |
| G. スケジュール実行の push 通知を needs-owner の主経路にする | 応答の内容で出し分けられるかが未確認。0件の日にも通知されるなら「静かに始める」に反し、出ないなら needs-owner が届かない。補助の経路として T1-4 で確認する |

---

## 影響とリスク

- **利用枠**: スケジュール実行は、発火ごとにフルセッションを消費する。Phase 1 は daily-brief の1本だけで始め、増やすかどうかは実績で判断する。
- **配布先への波及**: `install.sh` は配布元のフックを配布先に上書きコピーする。静音化（既定 `owner`）と重複除去は配布先にも及ぶ。README に明記し、`AGENT_CREW_SLACK_LEVEL=all` で戻せるようにする。
- **ダッシュボード（ADR-016）**: クラウドの run は `~/.claude/projects/` に transcript を残さないので、ダッシュボードには映らない。digest を Issue に残すことで可視性を補う。
- **model-mode.sh**
  - クラウドでは `src=none` になり、Pro 運用の表示（fable-class ON・critic.sh を使う）が毎ターン入る。これは unattended run に D3-4 と逆の指示を与えることになる。
  - そこで、unattended と判定できたときは、always-on 契約を参照する1行に差し替える（T1-0）。判定に使う環境変数 `CLAUDE_CODE_SESSION_ATTENDED` は対話セッションで `1` になることだけ確認済みで、unattended での値は T1-4 で確認する。
  - 判定できない場合は、run 契約の側で「model-mode の表示は無視する」と明記して二重に防ぐ。
- **Slack が今鳴っているか未確認**: フックは `.env` を読み込まないので、`SLACK_WEBHOOK_URL` がシェルに export されていなければ、ローカルでは今も鳴っていない。owner に確認する。
- **bench との関係**: `bench/tasks/03-task-completed-hook` は過去の仕様（`event` キー）を正解として固定している。Phase 0 の修正は `type` を**追加する**だけなので、採点は壊れない。

## 検証方法

- **Phase 0**: plan の DoD（テスト・`jq`・`diff` の生出力）。
- **Phase 1**: 2週間運用して次を記録する。
  - (a) digest コメントに owner が付けたリアクションの数（翌日の daily-brief が前日分を数え、digest に1行で書く）
  - (b) needs-owner の誤報の数
  - (c) 利用枠の消費
  - **撤退基準**: (a) が2週連続で 0 なら timer を止める。

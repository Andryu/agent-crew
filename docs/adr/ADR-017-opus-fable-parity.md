# ADR-017: Fable 5 不在時の team-lead 運用 — Opus をオーケストレーターに据えて Fable 級品質を維持する

- **Status**: Proposed（v2: 専門家レビュー3件〔Alex・Hana・critic(Opus)〕を反映済み。オーナー承認で Accepted）
- **Date**: 2026-08-15
- **Issue**: なし（オーナー指示: プラン変更により Fable 5 が利用不可になるため）
- **関連**: `fable-class-opus-adr.md`（工程設計の原本）、ADR-004（トークン最適化・リカバリ手順）、ADR-016（フック追加の抑制方針）

> 用語: 本 ADR では **team-lead ＝ メインセッション ＝ オーケストレーター**（`fable-class-opus-adr.md` の用語）を同一視する。製品名は「Fable 5」、CLI/設定のリテラルは `fable` と書き分ける。

---

## 背景

agent-crew の運用は、team-lead（Fable 5）が計画・意思決定・レビュー採否判断を担い、実作業を Sonnet サブエージェントに委譲する構造で回ってきた（メモリ `model-division`、Sprint-24〜27 の記録）。オーナーのプラン変更により Fable 5 が利用できなくなり、team-lead は Opus 5 になる。

Fable 5 依存箇所の棚卸し:

| # | 箇所 | 依存の内容 | 影響 |
|---|---|---|---|
| 1 | `~/.claude/settings.json` | `"model": "fable"` をグローバル既定にしている（`effortLevel` は `high`、`advisorModel` 未設定） | 利用不可になると起動時に警告付きで既定モデルへ置換される。ファイル上は `fable` のまま実体が Opus になる |
| 2 | `.claude/skills/fable-class/` | Fable 不在時の工程設計は存在するが **opt-in スキル**。frontmatter の `description` が「単純な1ファイル修正…には使わない」と発動を絞っている | 言われなければ Opus 単独で「工程の省略」が起きる（`fable-class-opus-adr.md` が棄却した状態そのもの） |
| 3 | `.claude/agents/*.md` | 全員 `model: sonnet`。設計・レビューの最終判断は Fable が担う前提 | 判断者が Opus になる分、レビュー網の厚みが相対的に薄くなる |
| 4 | `.claude/hooks/session_start.sh` | **PreToolUse に登録**されている（`settings.json`）。公式仕様では PreToolUse の stdout は debug log 行きで **モデルには見えない**（見えるのは SessionStart / UserPromptSubmit のみ） | 現状の「セッション開始情報」はモデルに届いていない可能性が高い（本 ADR とは独立した既存不具合だが、ここで直す） |
| 5 | メモリ `model-division`、`pm.md` 教訓、Sprint 文書 | 「Fable（メインセッション）」の表記でロールを名指し | 表記の問題。ロール名 `team-lead` に統一 |

## テーゼ

> **品質はモデルではなく、強制された工程から生まれる。工程の強制はドキュメントでは効かず、既定値・成果物・フックで効く。**

前半は `fable-class-opus-adr.md` の継承。後半は繰り返し失敗パターン（`agent-crew-failure-patterns.md` §2「ドキュメントに書くだけでは実行を保証できない」、横断表「コンテキストが長いほど初期の制約を忘れる」）から導く。ここでいう「効く強制」は3種類ある。

- **既定値**: 設定ファイルと skill の `description`（発動条件を決めるのは body ではなく description）
- **成果物**: 工程を踏んだ痕跡を機械可読なファイルとして残す（`enforce-retro-stop.sh` がレトロを検出できるのは `docs/sprints/*-retro.md` という成果物があるから）
- **フック**: モデルに届く箇所（SessionStart / UserPromptSubmit）に、毎ターン短く注入する

本 ADR の全判断はこの3種の強制に還元できるものだけを採用する。「書いておけば守られる」型の決定は採用しない。

## 検討した選択肢

| 案 | 内容 | 判定 |
|---|---|---|
| A. モデル設定だけ変える | `model` を `opus` にして終わり | **却下**。工程の強制がなく、`fable-class-opus-adr.md` が棄却した「Opus 単独」に戻る |
| **B（採用）. fable-class を既定運用に昇格し、Opus 向けに判断工程を補強** | 既定値・成果物・フックで工程を強制。設計・レビュー判断は critic（Opus）で反証 | 採用 |
| C. 全エージェントを Opus 化 | frontmatter を一律 `opus` | **却下**。レート上限（ADR-004 の再来）とコスト。「Sonnet 実装の品質は計画で決まる」という前提と矛盾 |
| D. 別系統モデル（Gemini/Antigravity）でセカンドオピニオン | Opus 同士の相関した盲点を切る唯一の手段 | **Stage 2 の再検討項目**。今は運用が二重化するため見送るが、後述の critic 効果指標が閾値未満なら critic だけ別系統に寄せる |
| E. `opusplan` | plan mode は Opus、実行は Sonnet をハーネスが強制 | **却下**。fable-class では VERIFY の採否判断・修正ループの判定が「実行フェーズ」に来るため、最も知能が要る工程が Sonnet に落ちる。強制力は魅力だが判断者の格下げと引き換えになる |
| F. plan mode を既定化 | 編集前に計画とオーナー承認を機械的に挟む | **却下**。plan mode の解除にはオーナー承認が要り、オーナーの「確認を挟まず進み続ける」方針（メモリ `keep-going`）と衝突する。承認ゲートは L2（Draft PR）に一本化されている |

## 決定事項

**B案を採用する。** 構成要素は7点。Stage 1（本 PR）と Stage 2（1スプリント計測後）に分ける。

### 1. モデル既定値の切替（`~/.claude/settings.json`、オーナー作業）

- `"model": "fable"` → **`"model": "opus"`**。`best`（Fable 可なら Fable、なければ最新 Opus）は、Fable 利用が usage credits 課金に回るプランで意図せず課金しうるため採らない。Fable 復帰時に `best` へ切り替えるのは1行の変更。
- **`effortLevel` は `high`（現状）のまま据え置く**。理由: (a) このキーはマシン全体・全プロジェクトに効くため、agent-crew の都合で恒久的に上げると他プロジェクトまで高コスト化する、(b) 深い局面は `ultrathink` キーワードで局所的に上げられる（Claude Code が認識し、そのターンだけ思考を深める）。xhigh は判断を担うサブエージェントの frontmatter に限定する（§3）。
- **advisor（`advisorModel: "opus"`）は Stage 2**。「Opus main ＋ Opus advisor」は公式が独立チェック用途で明記する組み合わせだが、会話全体を毎回送るためプラン上限を消費し、呼ぶタイミングも強制できない。critic の効果指標を1スプリント測ってから、追加するか判断する。

### 2. fable-class の発動を既定化（description と客観基準）

- `SKILL.md` の frontmatter `description` を書き換える。**「メインセッションが Fable 5 でない場合、次のいずれかに該当するタスクの開始時に必ず発動する」**: (a) `complexity` M 以上（`pm-estimation.md` 基準）、(b) `risk_level` medium 以上、(c) 設計判断・新規 ADR・新規ファイル作成・複数ファイル横断の変更を含む、(d) オーナーが「しっかり」「設計して」等と指示。該当しない小タスク（complexity S 相当・設計判断なし）は team-lead が直接作業してよい。
- **Lite モードは新設しない**（レビューで却下）。Lite/Full の分類はコストを払いたくない当人の自己申告になり、抜け道と形骸化を同時に招く。分類は上記の客観基準に外注し、Full か「対象外」かの二値にする。
- 発動条件の判定材料として、`planning.md` のマイクロタスク必須項目に **`complexity` と `risk_level`（`pm-estimation.md` 基準、team-lead 自身が付与）** を追加する。Yuki の `_queue.json` を経ないタスクでもルーティング表が使えるようにするため。

### 3. 判断工程の Opus 向け補強

- **独立クリティーク（critic）**: `risk_level` medium 以上のタスクの設計判断（ミニ ADR）は、確定前に専用エージェント **`critic`（Kagami）** へ「この決定を反証せよ」と依頼する。`.claude/agents/critic.md` を新設（`model: opus`・`effort: xhigh`・tools: Read/Grep/Glob・`Agent` なし）。採否は team-lead が判断する。
  - **非対称ルール**: critic の CRITICAL 指摘を却下する場合は「反論1文」を成果物（§4 の plan ファイル）に必ず残す。同じ Opus が最終審になる構造的限界への最低限の歯止め。
  - **効果指標**: 「レトロ時点で事後に見つかった欠陥のうち、critic が事前に指摘していた割合」をレトロで数える。2スプリント連続で 0/N（N≥3）なら D案（別系統モデル）へ切替を検討。従来案の「10回連続」は個人開発の頻度では感度が低すぎるため採らない。
- **effort の底上げ（限定）**: `critic` と `architect` の frontmatter に `effort: xhigh`。`qa`・`security` は Stage 2 で計測後に判断（symlink 配布のため全プロジェクトに効く点を考慮）。
- **コンテキスト衛生**: team-lead は大きなファイルの通読・広範囲検索を Explore/Sonnet に委譲し、自分のコンテキストを判断用に温存する（鉄則として `SKILL.md` に追加）。

### 4. 工程の成果物化（機械可読な足跡）

Full 発動時、team-lead は SPEC・PLAN・DoD・critic 採否を **`docs/plans/<YYYY-MM-DD>-<slug>.md`** に書く（テンプレートを `templates/plan.md` に置く）。PR 本文はこのファイルにリンクする。目的は3つ: (1) 工程を踏んだ痕跡が残り、後から検出・監査できる、(2) 仕様ドライラン（planning.md）にそのまま渡せる、(3) 将来 Stop フックで「plan なしの PR」を検出したくなったときの材料になる（今は入れない）。

### 5. モデルルーティング表 v2（`risk_level` 連動、`SKILL.md` の既存表を置換）

`Agent` 呼び出し時の `model` パラメータで上書きする。frontmatter を `opus` にするのは `critic` のみ。

| 工程 / risk_level | low | medium | high |
|---|---|---|---|
| 設計（Alex） | sonnet | sonnet ＋ critic | **opus** ＋ critic |
| 実装（Riku） | sonnet | sonnet | sonnet |
| 仕様準拠レビュー | haiku / sonnet | sonnet | sonnet |
| 品質レビュー（Sora） | sonnet | sonnet | **opus** |
| セキュリティ（Kai） | sonnet | **opus** | **opus** |
| ドキュメントレビュー（Hana） | sonnet | sonnet | sonnet |
| 採否判断 | team-lead | team-lead | team-lead ＋ critic |
| 探索・列挙 | Explore / haiku | 同 | 同 |

**同時 Opus 上限**: 1タスクにつき同時に走らせる Opus サブエージェントは **critic ＋ 1本まで**。Sora(opus) と Kai(opus) は直列で回す。C案（全 Opus 化）に累積効果で近づくのを防ぐ。
**レート上限到達時**: まず ADR-004 のリカバリ手順（タスク状態の保全）を実行し、その後 Sora → Alex の順に sonnet へ戻す（Kai・critic は戻さない）。実行主体は上限で止まったセッションではなく、次のセッションまたはオーナー。

### 6. フック（モデルに届く箇所へ、毎ターン短く）

- **`session_start.sh` の登録先を PreToolUse → SessionStart に移す**（既存の SessionStart echo と統合）。PreToolUse の stdout はモデルに届かないため。
- **UserPromptSubmit フックを新設**: `scripts/model-mode.sh` が1行を注入する。例: `[team-lead=opus | fable-class ON: complexity≥M or risk≥medium → SPEC/PLAN→docs/plans, critic before design decisions]`。「コンテキストが長いほど初期の制約を忘れる」への直接の対策。30秒タイムアウトの範囲内で軽量に。
- **モデル検知は実体から**: `scripts/model-mode.sh` はフック入力 JSON の `model`（あれば）→ `transcript_path` の直近 assistant メッセージの `message.model` → `~/.claude/settings.json` の `model` の順で解決する。設定ファイルだけを見ると「`fable` と書いてあるが実体は Opus」で誤判定するため。
- Stop フックでの工程チェックは入れない（判定材料が未実証。ADR-016 と同じ姿勢）。§4 の成果物が溜まってから再検討する。

### 7. 表記・導線・ドキュメント

- スプリント起動導線に1行: `pm.md` の起動プロトコルに「team-lead が Fable 5 でない場合は fable-class（ADR-017）で回す」を追加。実作業はスプリント経由で始まるので、ここが最も遵守率の高い注入点。
- `pm-learned-rules.md` に表記規則1行（team-lead をモデル名で呼ばない）。
- README に「モデル運用」節（推奨 settings、Fable 復帰時の戻し方、Stage 2 の項目）。
- `fable-class-opus-adr.md` の Status を「提案」→「採択」。
- メモリ `model-division` を「team-lead（現行 Opus）」表記へ（リポジトリ外）。Obsidian の ADR 索引に本 ADR を追記（別リポジトリ、本 PR 外）。

## 却下した代替案（要約）

| 案 | 却下理由 |
|---|---|
| A. モデル設定のみ | 工程の強制がない |
| C. 全エージェント Opus | レート上限・コスト。前提と矛盾 |
| E. `opusplan` | 採否判断が Sonnet に落ちる |
| F. plan mode 既定化 | オーナーの介入最小化方針と衝突 |
| Lite モード新設 | 自己申告ゲートは抜け道と形骸化を招く（critic・Alex 指摘） |
| `effortLevel: xhigh` をグローバル既定に | 全プロジェクトに効く副作用。`ultrathink` で局所化できる |
| Stop フックで工程チェック | 判定材料が未実証。誤検知の害が大きい |
| 各エージェント frontmatter を opus に | 低リスクまで高コスト化。呼び出し時上書きの方が細かい |

## 段階移行計画

| Stage | 内容 | 判断材料 |
|---|---|---|
| **1（本 PR）** | §2 description・客観基準、§3 critic 新設＋critic/architect の xhigh、§4 plan 成果物、§5 表 v2、§6 フック修正・新設、§7 導線・文書 | — |
| **オーナー作業** | `~/.claude/settings.json` の `model` を `opus` に | — |
| **計測（次の1スプリント）** | レトロで (a) 工程省略の再発有無、(b) critic 効果指標、(c) Opus レート上限到達回数（`/usage` と token-report）、(d) plan 成果物の作成率 | Stage 2 の入力 |
| **2** | advisor 有効化、`qa`/`security` の xhigh、critic の別系統化（D案）、Stop フックの工程チェック | 上記 (a)〜(d) |

## トレードオフ

- critic・高リスクの Opus レビューでトークンは増える。medium 以上に限定し、同時 Opus 上限で抑える。
- plan 成果物の作成は工数増だが、仕様ドライランの入力と監査の材料を兼ねるので純増ではない。
- UserPromptSubmit フックは毎ターン1行をコンテキストに足す。長いセッションでも合計は数百トークン。
- レート上限の計測手段が現状ない（`_lessons.json` に 429 の記録は0件）。計測は token-report / ダッシュボードへの追加が必要で、フォローアップ Issue とする。

## 将来の再検討トリガー

- Fable 5 が再び利用可能になった（`model` を `best` にし、ルーティング表の team-lead 行を戻すだけで済む）。
- critic 効果指標が2スプリント連続 0/N（N≥3）→ D案。
- Opus レート上限到達が週2回超（計測導入後）→ 表 v2 の high 列を見直す。
- `docs/plans/` が10件以上溜まった → Stop フックでの工程チェックを実証実験。

## 実装メモ（一次情報で確認した仕様、2026-08-15 取得）

| 項目 | 確認した事実 | 出典 |
|---|---|---|
| model エイリアス | `default` / `best`（Fable 可なら Fable、なければ最新 Opus）/ `fable` / `opus` / `sonnet` / `haiku` / `opus[1m]` / `sonnet[1m]` / `opusplan` | https://code.claude.com/docs/en/model-config |
| Fable 5 の位置づけ | どのアカウント種別でも既定ではない。プランによっては usage credits 課金。利用不可なら `model` 設定は起動時に警告付きで置換 | 同上 |
| effort | Opus 5 / Sonnet 5: `low/medium/high/xhigh/max`。既定 `high`。settings の `effortLevel` は `xhigh` まで永続、`max` はセッション限定。`CLAUDE_CODE_EFFORT_LEVEL` が最優先 | 同上 |
| `ultrathink` | プロンプト中のキーワードとして認識、そのターンだけ思考を深める。「think hard」等は認識されない | 同上 |
| サブエージェント frontmatter | `model`: `sonnet/opus/haiku/fable/フルID/inherit`（既定 inherit）。`effort`: `low〜max`（セッション設定を上書き）。既定で3階層まで子を持てる（`Agent` を外せば禁止） | https://code.claude.com/docs/en/sub-agents |
| モデル解決順 | `CLAUDE_CODE_SUBAGENT_MODEL` ＞ 呼び出し時 `model` ＞ frontmatter ＞ メインセッション | 同上 |
| advisor | 実験的。`advisorModel` / `/advisor` / `--advisor`。「Opus main ＋ Opus advisor」は独立チェック用途で明記。会話全体を毎回送る | https://code.claude.com/docs/en/advisor |
| フック stdout | モデルに届くのは SessionStart / UserPromptSubmit（/UserPromptExpansion）のみ。他は debug log。UserPromptSubmit は既定タイムアウト30秒。入力 JSON に `model` が入ることがある（保証なし）、`transcript_path` は常にある | https://code.claude.com/docs/en/hooks |

### 変更ファイル（Stage 1）

| ファイル | 変更 |
|---|---|
| `.claude/skills/fable-class/SKILL.md` | description 書換（発動の客観基準）、ルーティング表 v2 に置換、鉄則に「コンテキスト衛生」「plan 成果物」「同時 Opus 上限」追加、Fable 節を「Fable が使える場合／使えない場合」に整理 |
| `.claude/skills/fable-class/references/planning.md` | マイクロタスク必須項目に `complexity`/`risk_level` 追加、plan 成果物の書き出し手順 |
| `.claude/skills/fable-class/references/verification.md` | critic 手順（発動条件・非対称ルール・効果指標）、最終ゲートに「critic 実施 or risk=low の記録」 |
| `templates/plan.md` | 新設 |
| `.claude/agents/critic.md` | 新設（Kagami） |
| `.claude/agents/architect.md` | `effort: xhigh` |
| `.claude/hooks/session_start.sh` | §7 モデル運用モードを `scripts/model-mode.sh` 呼び出しに置換 |
| `scripts/model-mode.sh` | 新設（実体からのモデル検知、1行出力） |
| `.claude/settings.json` | `session_start.sh` を PreToolUse → SessionStart へ、UserPromptSubmit に `model-mode.sh` を登録 |
| `docs/spec/start-hook-design.md` | 「PreToolUse vs Start hook」節に更新注記（登録先変更の理由と出典） |
| `.claude/agents/pm.md` | 起動プロトコルに1行 |
| `.claude/agents/pm-learned-rules.md` | 表記規則1行 |
| `README.md` | 「モデル運用」節 |
| `docs/adr/fable-class-opus-adr.md` | Status 採択 |
| メモリ `model-division.md` | 表記変更（リポジトリ外） |

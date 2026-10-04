# ADR-018: Pro（Sonnet 主体）プランでの team-lead 運用 — 判断をセッション外に外出しして Fable 級工程を維持する

- **Status**: Proposed（v2: critic〔Kagami, opus〕の反証レビュー〔強4・中1・条件付き差し戻し〕を反映済み。オーナー承認で Accepted。2026-08-18 のプラン移行前に有効化する）
- **Date**: 2026-08-17
- **Issue**: なし（オーナー指示: Claude Max → Pro への移行に備える）
- **関連**: ADR-017（Opus 前提の運用。**歴史的記録として残す**。team-lead が Opus 以上で動く環境では引き続き有効）、`fable-class-opus-adr.md`（工程設計の原本）、ADR-004（レート上限リカバリ）、ADR-016（フック追加の抑制方針）

> 用語: **team-lead ＝ メインセッション ＝ オーケストレーター**。「Pro 運用」とは team-lead の実効モデルが **Opus 以上でない**（＝ Sonnet 主体）状態を指す。プラン名ではなくモデルの実体で判定する（§6）。

---

## 背景

ADR-017 は「Fable 5 が使えなくなり team-lead が Opus になる」前提で、工程の強制（既定値・成果物・フック）と critic（Opus）による反証を組み合わせた。2026-08-18 にオーナーのプランが Max から Pro に落ち、team-lead の実効モデルは **Sonnet 主体**になる（Opus は使えても上限が小さく、恒常的な判断者に据えられない）。

ADR-017 の前提で崩れる箇所の棚卸し:

| # | ADR-017 の前提 | Pro で起きること |
|---|---|---|
| 1 | 曖昧さを潰す側（team-lead）が、実装する側（Sonnet）より強い | **team-lead 自身が Sonnet**。「実装者に判断させない」（fable-class 鉄則2）の判断者が最弱の環になる |
| 2 | critic を `model: opus` のサブエージェントで呼べる | サブエージェントもプラン上限内で動く。Opus サブエージェントの安定供給が保証されない。`.claude/agents/critic.md` のモデル/認証を従量 API に切り替えられるかは**未確認** |
| 3 | 表 v2 の high 列で Sora/Kai を Opus に上げられる | 同上。上限が小さいと high 列が形骸化する |
| 4 | fable-class の発動基準は「complexity M 以上 / risk medium 以上」 | 判定者（team-lead）が Sonnet になり、S/M の見立て自体が甘くなる。自己申告ゲートの弱点（ADR-017 §2 で Lite モードを却下した理由）が発動条件そのものに現れる |
| 5 | 探索・列挙は Explore/haiku に委譲 | 上限が小さいほど「LLM に列挙させる」コストが相対的に重い。決定的に求まるものを LLM に投げる余地がない |

## テーゼ（維持）と前提の反転

> **品質はモデルではなく、強制された工程から生まれる。工程の強制はドキュメントでは効かず、既定値・成果物・フックで効く。**

テーゼは ADR-017 から変えない。変わるのは前提であり、その反転は一文で言える:

> **ADR-017 は「強い team-lead が弱い実装者を管理する」設計だった。Pro では team-lead 自身が最弱の環になる。したがって、判断をセッション内（team-lead）で完結させず、セッション外＝従量 API の critic と決定的ツール（`rg` / `fd` / `jq` / テスト）に外出しする。**

「外に出す」の意味は2種類ある。

- **知能を外に出す**: 設計判断・高リスクレビューの最終審を、プラン上限に縛られない従量 API の Opus（critic）に置く。critic は team-lead より強いことが前提なので、後述の非対称ルールが成立する。
- **判断そのものを消す**: 探索・列挙・件数確認・存在確認のように決定的に求まるものは LLM に判断させない。`rg`/`fd`/`jq`/テストの出力を「事実」として工程に流し込む。Sonnet の弱さが最も出るのは「見落とし」であり、見落としは決定的コマンドで潰せる。

## 検討した選択肢

| 案 | 内容 | 判定 |
|---|---|---|
| A. ADR-017 のまま（設定だけ Sonnet） | 表 v2 の `opus` 指定がプラン上限で不安定になる。critic が同格以下になり非対称ルールの根拠が消える | **却下** |
| **B（採用）. 判断の外出し** | critic を従量 API の外部プロセス（`scripts/critic.sh`）にし、成果物 md を残す。探索・列挙を決定的コマンドに固定。実装を Codex（herdr ペイン、別系統）に出し、Sonnet のコンテキストを判断用に温存 | 採用 |
| C. team-lead を従量 API の Opus にする（Claude Code を API キー課金で使う） | 最も単純だが、常時 Opus 従量は個人開発の予算に合わない。判断が要る瞬間だけ従量にする B の方が費用対効果が高い | **却下**（Stage 2 で「一時的に切り替える運用」は再検討） |
| D. critic を `.claude/agents/critic.md` のまま `model: opus` に据え置く | Pro でも Opus サブエージェントが呼べるなら最小変更。ただし上限とモデル/認証切替が未確認で、失敗したときに critic 工程が静かに落ちる | **却下**（未確認事項に工程を賭けない。確認できたら Stage 2 で B と併用） |
| E. fable-class を Pro では全タスク発動 | 発動条件の判定を無くすので最も強制力が高い。ただし「1ファイルの局所修正にも SPEC/PLAN」は工数が過大 | **部分採用**（§2: 対象外を客観条件で極小に絞る。実質ほぼ全タスク発動） |

## 決定事項

**B案を採用する。** 構成要素は6点。ADR-017 と同じく Stage 1（本 PR）と Stage 2（1スプリント計測後）に分ける。

### 1. Pro 運用モードの定義と検知（fail-closed）

- **Pro 運用モード** ＝ team-lead の実効モデルが Opus 以上でない状態。`scripts/model-mode.sh` が実体（hook 入力 / transcript）から判定し、UserPromptSubmit で毎ターン1行注入する。
- **fail-closed の拡張**: ADR-017 は「Fable と断定できるのは実体確認できたときだけ」だった。本 ADR ではさらに、**実体確認できない（settings のみ）ときは Pro 運用モードに倒す**。設定ファイルに `opus`/`fable` と書いてあっても実体は Sonnet でありうるため。誤検知の害は「厳しい側」に出るだけで、緩い側には出ない。ただしこの倒しが効くのは**発動条件**（工程の厚み）までで、**却下権の剥奪**（§5）は実体で sonnet/haiku と確認できたとき、または plan に `mode: pro` と記録したときに限る（critic 指摘5: 統治上の権利までターン単位で揺らさない）。
- **モードはタスク単位でラッチする**: `templates/plan.md` 先頭の `mode:` に着手時の判定（と `src=`）を記録し、そのタスクの発動条件・却下権は plan の mode に従う。critic.sh は `--mode` で呼び出し時のモードを成果物ヘッダに残し、不一致を検出可能にする。

### 2. fable-class の発動条件を Pro 前提に拡張（description ＝ 既定値）

`SKILL.md` の frontmatter `description` を書き換える。

- **メインが Opus 以上でない場合**: **complexity S 以上（＝ほぼ全タスク）で発動**する。対象外は次の4条件を**すべて**満たすものに限る:
  1. 変更対象が **1ファイル**（`git diff --name-only <merge-base>...HEAD | wc -l` で確認できる。作業ツリーの汚れは数えない）
  2. **既存関数への局所修正**（新規ファイル・新規公開インターフェース・新規 ADR/スキル/フック/エージェント定義/スクリプトを含まない。同じ `git diff` で機械判定）
  3. **そのファイルのテストが既に存在する**（`fd`/`rg` で確認できる）
  4. **設計判断を含まない**（条件1〜3 を満たした上で、代替案が2つ以上あるなら免除不可。1文で書く）
- 免除判定は **自己申告（complexity）でなく客観条件（ファイル数・テストの有無）** で行う。条件1〜3 は機械判定で、1つでも満たさなければ条件4を待たずに免除不可。着手前は「触る予定のファイル」で仮判定し、**PR 時に同じコマンドの生出力で事後検証する**（免除を主張する PR は plan リンクの代わりに生出力を本文に貼る。仮判定と食い違えば免除は無効）。`rg`/`fd`/`git` のいずれかが無ければ免除不可。critic 指摘1（着手前判定は自己申告に戻る）への対策は「事後検証」であり、機械的な PR チェック（plan リンクなし かつ diff が2ファイル以上なら落とす）は Stage 2 に置く（Stop フックを増やさない ADR-016 方針は守れる）。
- メインが Opus の場合は ADR-017 の基準（M 以上 / medium 以上 / 設計判断あり / 指示）を維持。Fable 5 の場合は従来どおり中〜大規模タスクで発動。

### 3. モデルルーティング表 v3（列の意味を変える）

v2 の列は「どのモデルを使うか」だった。**v3 の列の意味は「その工程の判断をセッション内で完結してよいか、外に出すか」**である。モデル名はその帰結として書く。`SKILL.md` の表を v3 に置換する（v2 は ADR-017 に歴史として残る）。

| 工程 / risk_level | low | medium | high |
|---|---|---|---|
| 設計（SPEC/PLAN・ミニADR） | team-lead（`ultrathink`） | team-lead（`ultrathink`）＋ critic 推奨 | team-lead（`ultrathink`）＋ **critic 必須（従量 API）** |
| 実装 | Codex（herdr ペイン、delegation.md の手順あり）／無ければ fresh Sonnet | 同 | 同 |
| 仕様準拠レビュー | fresh Sonnet | fresh Sonnet | fresh Sonnet |
| 品質レビュー（Sora） | fresh Sonnet | fresh Sonnet | fresh Sonnet ＋ **critic** |
| セキュリティ（Kai） | fresh Sonnet | fresh Sonnet ＋ critic 推奨 | fresh Sonnet ＋ **critic** |
| ドキュメントレビュー（Hana） | fresh Sonnet | fresh Sonnet | fresh Sonnet |
| 探索・列挙・件数確認 | **`rg`/`fd`/`jq`/テスト（LLM に投げない）** | 同 | 同 |
| critic | 不要 | 従量 API（推奨） | **従量 API（必須）** |
| 採否判断 | team-lead | team-lead（CRITICAL 却下不可※） | team-lead（CRITICAL 却下不可※） |

要点:

- **設計 ＝ team-lead（`ultrathink`）**: 判断はセッション内で行うが、そのターンだけ思考を深める。high では critic を必ず通す（medium は推奨。省略時は plan に理由1行）。
- **実装 ＝ Codex（herdr ペイン）**: 実装をプラン上限の外（別系統・別プロセス）に出し、team-lead の Sonnet コンテキストを判断用に温存する。手順（委譲テンプレの成果物化・生出力の回収ファイル・完了後の `git diff --name-only` と対象一覧の突合）は `delegation.md` の Codex 節に定義した。critic 指摘4（手順ゼロで別系統に賭けるのは D案却下基準と矛盾、失敗パターン §6 と同型）に対し、Stage 1 で手順を成果物として書き、突合を必須にした。Codex が使えない環境では fresh Sonnet サブエージェントにフォールバックし、plan に明記する。
- **レビュー ＝ fresh Sonnet**: 二段階レビュー（verification.md）は Sonnet で回してよい。high のときだけ critic を追加する（Sonnet 同士の相関した盲点を、格上かつ別コンテキストで切る）。
- **探索・列挙 ＝ 決定的コマンド**: 対象ファイル一覧・参照箇所・件数・存在確認は `rg`/`fd`/`jq`/テストで求め、その出力を plan に貼る。LLM（Explore/haiku 含む）に「全部挙げて」と頼まない。
- **critic ＝ 従量 API**: プラン上限の外にある知能。§4 の `scripts/critic.sh` で呼ぶ。
- **※ 却下不可の唯一の例外**は §5 参照。
- **「fresh」** は従来どおりタスクごとに新規起動したコンテキストを指す。同時 Opus 上限（ADR-017 §5）は Pro 運用では対象がなくなるため適用外（Opus 運用に戻ったら復活）。

### 4. critic の実装 —「案1: 外部プロセス＋成果物 md」

`.claude/agents/critic.md` のサブエージェントを従量 API のモデル/認証に切り替えられるかは**未確認**なので、それに賭けず **`scripts/critic.sh`** を新設する。

- **入力**: 反証対象（ミニ ADR / plan ファイル / 任意の md）と、裏取り用に添付するファイル（`--ctx`、複数可）。API 側の critic はリポジトリを読めないため、**対象 md が参照するリポジトリ内パスはラッパが自動で添付する**（critic 指摘3: 添付を検査される側の選択に委ねると情報の非対称が残る）。上限を超える分は切り詰めず見送り、成果物ヘッダに `attach_skipped: yes` と一覧を機械的に出す。team-lead は加えて `rg -l` 等で列挙したものを `--ctx` で足す。添付できないものは critic 側で「未確認」と明記される。
- **ペルソナ**: `.claude/agents/critic.md` の本文（frontmatter を除く）を system prompt に流用する。定義の一元管理のため、Kagami の反証フォーマット（強/中/弱＝CRITICAL/MAJOR/MINOR、総合判定）を API 側でも揃える。
- **モデル**: 既定 `claude-opus-5`（team-lead より強いこと＝非対称ルールの前提）。`CRITIC_MODEL` で上書き可。effort は既定 `xhigh`（`CRITIC_EFFORT`）。
- **認証**: `ANTHROPIC_API_KEY` は **ラッパ内でのみ使う**。解決順は (1) 環境変数 → (2) `~/.config/agent-crew/critic.env` → (3) リポジトリ直下の `.env`（gitignore 済み）。**シェルプロファイルで `export ANTHROPIC_API_KEY` してはならない** — Claude Code 本体がそのキーを拾い、プラン課金ではなく従量課金に切り替わりうるため。
- **成果物**: `docs/plans/<slug>-critic.md` を生成する。ヘッダに日付・モデル・対象・添付（明示/自動）・`attach_skipped`・呼び出し時 mode・usage（入出力トークン）・CRITICAL 件数、本文に critic の出力をそのまま置く。system prompt の追記で「CRITICAL には対象/添付内の引用を必須、件数を揃えるために強さを上げない（0〜5個）」を課し、件数ノルマ由来の severity インフレを塞ぐ（critic 指摘2）。team-lead はこのファイルの指摘を plan の critic 節に採否付きで転記する。
- **コスト上限**: 1回あたりの上限は `max_tokens` と添付サイズ上限（`CRITIC_MAX_CTX_BYTES`）で抑え、**月次上限は Console 側の Spend limit を前提**とする（ラッパでは持たない。二重管理を避ける）。
- **`--dry-run`**: API を呼ばずリクエスト JSON を出力する。テストと導入確認用。

### 5. 非対称ルールの強化 —「弱い側は強い側の CRITICAL を却下できない」

ADR-017 の非対称ルールは「CRITICAL を却下するなら反論1文を残す」だった。Pro 運用では team-lead（Sonnet）が critic（Opus）より弱いので、これを強化する。

- **plan の mode が pro の場合、critic の CRITICAL 指摘を team-lead は却下できない。** 取れる行動は (a) 修正して再 critic、(b) オーナーへエスカレーション（plan の critic 節に「CRITICAL 未解消・オーナー判断待ち」と記録し、PR は Draft のまま）、(c) **唯一の例外**: CRITICAL の根拠が事実誤認であることを決定的コマンド（`rg`/`fd`/テスト）の生出力で示せる場合に限り却下でき、その生出力を plan の critic 節に貼る。推論だけの反論は不可。critic 指摘2（構造的に指摘を出す critic に無条件の停止権を渡すと、誤検知の出口がオーナー介入だけになり keep-going 方針と衝突する）への対策で、非対称性（推論では反論できない）は保たれ、§テーゼの「決定的コマンドに外出し」とも整合する。
- critic 成果物ヘッダに `attach_skipped: yes` が立つ回の CRITICAL は、添付漏れ由来でありうるため却下不可の対象外（通常の採否判断に戻る）。
- 却下権は**モデルの強さ順**に置く: critic と同格以上のモデル（Opus/Fable がメインの環境）は ADR-017 の「反論1文」ルールで却下できる。オーナーは常に却下できる（その場合も反論1文を残す）。
- MAJOR/MINOR の採否は従来どおり team-lead が判断する（却下の規律: verification.md）。全件採用は判断放棄のサインという既存の規律も維持。
- **効果指標**は ADR-017 と同じ（レトロで「事後に見つかった欠陥のうち critic が事前に指摘していた割合」）。critic が API 化されたことで、指摘の成果物 md が残り、集計が機械的にできる。

### 6. フック・導線・ドキュメント

- `scripts/model-mode.sh`: Sonnet/haiku/未確認のとき **Pro 運用行**を注入する（発動条件・免除条件・表 v3 の要点・critic.sh・CRITICAL 却下不可）。
- `README.md` の「モデル運用」節に Pro 運用の行を追加（推奨設定、critic.sh の準備、戻し方）。
- `.claude/agents/pm.md` ステップ-1、`references/verification.md` の critic 節、`.claude/agents/critic.md` の採否節を Pro 前提に更新。
- ADR-017 の冒頭に「Pro 運用は ADR-018 が上書きする」旨のポインタを1行足す（本文は改変しない）。
- Stop フックでの工程チェックは引き続き入れない（ADR-016/017 と同じ姿勢）。`docs/plans/*-critic.md` が溜まってから再検討。

## critic（Kagami, opus）の反証と採否 — v1 → v2

| # | 指摘（強さ） | 採否 | 反映 |
|---|---|---|---|
| 1 | 免除4条件は着手前に判定できず自己申告に戻る。`git status` は作業ツリーの汚れを数える。条件4は主観。PR テンプレが ADR-017 基準のまま（強） | 採用（一部） | 判定を `git diff <merge-base>...HEAD` に一本化・事後検証必須・条件1〜3 は機械判定で優先。条件4は「1〜3 を満たした上での残余」に格下げして残す（削除はしない: 局所修正でも設計判断を含む例があるため）。PR テンプレ更新。CI チェックは Stage 2 |
| 2 | 「CRITICAL 却下不可」は指摘を必ず出す critic に無条件の停止権を渡す。誤検知の出口がオーナー介入のみ（強） | 採用 | 決定的コマンドの生出力で事実誤認を示せる場合のみ却下可、の例外を開けた。critic.sh の system prompt で件数ノルマ廃止・CRITICAL に引用必須 |
| 3 | 添付は検査される側が選ぶので情報の非対称が残る。切り詰めが無言（強） | 採用 | ラッパが対象 md の参照パスを自動添付。上限超過は切り詰めず `attach_skipped` をヘッダに列挙。その回の CRITICAL は却下不可の対象外 |
| 4 | 「実装＝Codex」は手順も検証経路も無く、D案却下の基準に自ら反する。失敗パターン §6 と同型（強） | 採用（一部） | delegation.md に Codex 節（テンプレ成果物化・回収ファイル・`git diff` 突合必須）を新設し、表 v3 に「手順あり／無ければ fresh Sonnet」を明記。Codex を既定に置くこと自体はオーナー指示のため維持 |
| 5 | fail-closed の Pro 倒しが却下権まで左右し、ターン単位で揺れる。fd は新規依存（中） | 採用 | plan の `mode:` でタスク単位にラッチ。却下権の剥奪は実体確認または plan 記録に限定。rg/fd/git 不在時は免除不可 |

## 却下した代替案（要約）

| 案 | 却下理由 |
|---|---|
| A. 設定だけ Sonnet | critic が同格以下になり非対称ルールが成立しない |
| C. team-lead を常時従量 Opus | 予算。判断が要る瞬間だけ従量にする方が安い |
| D. critic をサブエージェントのまま | モデル/認証切替が未確認。工程を未確認事項に賭けない |
| E. Pro では例外なく全タスク発動 | 1ファイル局所修正に SPEC/PLAN は過大。客観条件で極小の免除を残す |
| critic の月次上限をラッパで持つ | Console の Spend limit と二重管理になる。ラッパは1回上限のみ |
| critic の CRITICAL を team-lead が反論1文で却下 | 弱い側が強い側を却下する構造。ADR-017 の歯止めが Pro では逆向きに効く |
| 探索・列挙を Explore/haiku に委譲（ADR-017 §5） | 上限が小さい環境で LLM 列挙は高コストかつ見落としを増やす。決定的コマンドで代替できる |

## 段階移行計画

| Stage | 内容 | 判断材料 |
|---|---|---|
| **1（本 PR）** | §1 検知、§2 description、§3 表 v3、§4 `critic.sh`、§5 非対称ルール、§6 フック・文書 | — |
| **オーナー作業** | Console で API キー発行・Spend limit 設定、`~/.config/agent-crew/critic.env` に `ANTHROPIC_API_KEY=` を置く。herdr に Codex ペインを用意 | — |
| **計測（次の1スプリント）** | レトロで (a) fable-class 免除の件数と妥当性、(b) critic 効果指標、(c) critic 月次コスト（`*-critic.md` の usage 集計）、(d) Codex 実装のレビュー差し戻し率 | Stage 2 の入力 |
| **2** | `.claude/agents/critic.md` の従量 API 化が確認できれば併用、team-lead を一時的に従量 Opus に切り替える運用（C案の限定版）、Stop フックでの critic 未実施検出、免除主張 PR の機械チェック（plan リンクなし かつ diff 2ファイル以上を落とす CI） | 上記 (a)〜(d) |

## トレードオフ

- critic が従量になるので**金銭コストが発生する**。high 必須・medium 推奨に絞り、添付サイズ上限と Console の Spend limit で抑える。
- Codex（別系統）への実装委譲は、Claude 側の規約（agents/skills）が届かない。plan の委譲プロンプトに規約を明示する運用になる（delegation.md の既存方針と同じ）。
- fable-class がほぼ全タスクで発動するため、小タスクの工数は増える。免除4条件で最小限は逃がす。
- API 側 critic はリポジトリを自分で読めない。添付漏れは「未確認」として表に出るので、見落としが暗黙化するよりは良い。

## 将来の再検討トリガー

- team-lead が再び Opus 以上になった → `model-mode.sh` が自動で ADR-017 モードに戻る。本 ADR の critic.sh は引き続き使ってよい。
- critic 月次コストが Spend limit の 80% を2ヶ月連続で超えた → medium の「推奨」を「不要」に落とすか、モデルを見直す。
- fable-class 免除が月に 20 件を超えた → 免除4条件が緩すぎる。条件を締める。
- `.claude/agents/critic.md` の従量 API 化が公式に確認できた → Stage 2 でサブエージェント critic を復活し、外部プロセスと使い分ける。

## 実装メモ（一次情報で確認した仕様、2026-08-17 取得）

| 項目 | 確認した事実 |
|---|---|
| critic の既定モデル | `claude-opus-5`（Sonnet 5 より上位。thinking は既定で adaptive、`output_config.effort` は `low`〜`max`）。`budget_tokens`・`temperature` 等は 400 になるため送らない |
| 拒否（refusal） | Opus 5 は安全分類器で `stop_reason: "refusal"` を返しうる。ラッパは `stop_reason` を見て非ゼロ終了（exit 2）し、成果物に理由を書く。`fallbacks: "default"`（beta `server-side-fallback-2026-07-01`）は `CRITIC_FALLBACK=1` で有効化できる（beta のため既定はオフ。設計反証で拒否が出ることは稀で、beta 変更でラッパ全体が壊れる方を避ける） |
| ストリーミング | 出力が長くなりうるため `stream: true` で受け、SSE を jq で組み立てる（非ストリーミングの大きな `max_tokens` は HTTP タイムアウトの原因） |
| 認証の優先順 | SDK/CLI は `ANTHROPIC_API_KEY` を最優先で拾う。Claude Code も同様に拾いうるため、グローバル export は禁止 |

### 変更ファイル（Stage 1）

| ファイル | 変更 |
|---|---|
| `docs/adr/ADR-018-pro-sonnet-operation.md` | 新設（本文書） |
| `docs/adr/ADR-017-opus-fable-parity.md` | 冒頭にポインタ1行（本文不変） |
| `.claude/skills/fable-class/SKILL.md` | description を Pro 前提に拡張、表 v3 に置換、免除4条件の判定レシピ、Pro 節を追加 |
| `.claude/skills/fable-class/references/verification.md` | critic 節に critic.sh 手順と非対称ルール強化（例外・mode ラッチ） |
| `.claude/skills/fable-class/references/delegation.md` | Codex（herdr ペイン）への委譲手順を新設 |
| `templates/plan.md` | `mode:` 項目と CRITICAL 却下の記録欄 |
| `.github/pull_request_template.md` | fable-class 項目を Pro 基準（免除判定の生出力）に更新 |
| `.claude/agents/critic.md` | 採否節に Pro の却下不可ルール、critic.sh から system prompt として流用される旨 |
| `.claude/agents/pm.md` | ステップ-1 に Pro 運用の1行 |
| `scripts/critic.sh` | 新設 |
| `scripts/model-mode.sh` | Pro 運用行の注入、fail-closed の拡張 |
| `tests/test_critic_sh.py` | 新設（`--dry-run`・キー未設定・成果物パス） |
| `.env.example` | `ANTHROPIC_API_KEY` の置き場所と注意書き |
| `README.md` | 「モデル運用」節に Pro 運用の行 |
| `docs/plans/2026-08-17-pro-hardening.md` | 本タスクの plan 成果物 |

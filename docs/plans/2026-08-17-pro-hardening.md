# plan: pro-hardening

- **日付**: 2026-08-17
- **担当**: team-lead（メインセッション）
- **complexity**: M
- **risk_level**: high（スキル発動条件・フック注入文・エージェント間プロトコルの変更を含む。pm-estimation「強制 high」該当）
- **mode**: fable（src=hook。team-lead は Fable 5 のため critic CRITICAL の却下は ADR-017 ルール〔反論1文〕）
- **ADR参照**: `docs/adr/ADR-018-pro-sonnet-operation.md`

## SPEC

- **要求の再記述**: 2026-08-18 に Claude Max → Pro（Sonnet 主体）へ落ちる。agent-crew の fable-class スキルと ADR-017 の運用を Pro 前提に更新する。ADR-018 新設、SKILL.md の発動条件を客観条件で拡張、ルーティング表 v3、critic を外部プロセス（`scripts/critic.sh`、従量 API）＋成果物 md に、model-mode.sh と README に Pro 運用行。ブランチ `feat/pro-hardening` にコミット、push/merge はしない。
- **暗黙の前提**: ADR-017 は歴史として残す（Opus 運用に戻れば有効）。テーゼは維持。既存テスト・フックを壊さない。`.claude/agents/critic.md` の従量 API 化は未確認なので賭けない。
- **不明点**: (自己解決) API 側の仕様（モデル ID・thinking・refusal・streaming）は claude-api スキルの一次情報で確認。(オーナー作業) API キー発行・Spend limit・`~/.config/agent-crew/critic.env` の配置・herdr の Codex ペイン。
- **テーゼ**: 品質はモデルではなく強制された工程から生まれる。Pro では team-lead 自身が最弱の環になるので、判断をセッション外（従量 API の critic と決定的ツール）に外出しする。

## PLAN

### 代替案比較表

| 案 | 複雑度 | 変更範囲 | リスク | テーゼ適合 |
|---|---|---|---|---|
| A. 設定だけ Sonnet | 低 | 1行 | critic が同格以下、非対称ルール崩壊 | ✗ |
| B. 判断の外出し（採用） | 中 | ADR・スキル・スクリプト・文書 | 従量コスト | ○ |
| C. team-lead を常時従量 Opus | 低 | 設定 | 予算 | △ |
| D. critic をサブエージェント据え置き | 低 | なし | 未確認事項に依存 | ✗ |
| E. Pro では例外なく全タスク発動 | 低 | description | 工数過大 | △（部分採用） |

### ミニADR

ADR-018 本文を参照。

### マイクロタスク一覧

| # | タスク | complexity | risk | 担当 | 対象 |
|---|---|---|---|---|---|
| T1 | ADR-018 新設、ADR-017 にポインタ | M | high | team-lead | `docs/adr/ADR-018-*.md`, `docs/adr/ADR-017-*.md` |
| T2 | SKILL.md description・表 v3・免除レシピ・Pro 節、verification.md critic 節、critic.md 採否節、pm.md ステップ-1 | M | high | team-lead | `.claude/skills/fable-class/**`, `.claude/agents/{critic,pm}.md` |
| T3 | `scripts/critic.sh` 新設（dry-run 対応）、`.env.example`、`tests/test_critic_sh.py` | M | medium | team-lead | 同左 |
| T4 | `scripts/model-mode.sh` Pro 行・fail-closed 拡張、README モデル運用節 | S | high | team-lead | 同左 |

本タスクは team-lead が Fable 5 で動いているため実装は自前で行い、DELEGATE は省略した（表 v3 の「実装＝Codex」は Pro 運用時の規定）。

### 依存関係

T1 → T2/T4（表 v3 と発動条件は ADR の文言に従う）。T3 は独立。

## critic

- **発動有無**: risk_level high のため発動。critic（Kagami, opus サブエージェント）に ADR-018 草稿を反証させた。報告は依頼から約40分後に到着（強4・中1、条件付き差し戻し）。
- **指摘と採否**: ADR-018「critic（Kagami, opus）の反証と採否」節に転記。1・4 は一部採用、2・3・5 は採用。
- **CRITICAL却下の反論**（team-lead は Fable 5、mode: fable のため ADR-017 ルール〔反論1文〕が適用）:
  - 指摘1の「条件4を削除」部分を却下: 1ファイルの局所修正でも代替案が複数ある変更は存在し、機械判定（1〜3）を優先させた上で残余として1文書かせる方が、無条件免除より安全側。
  - 指摘4の「表 v3 の実装行を fresh Sonnet 既定に反転」部分を却下: 実装＝Codex はオーナーの明示指示。代わりに手順を成果物化し、突合を必須にして「未確認事項に賭ける」状態を解消した。
- 補足: 当初「サブエージェント critic が返らない」と記録したが、40分後に到着したため訂正。返りが遅いこと自体は「上限内のサブエージェントに critic を賭けない」（ADR-018 D案却下）の傍証にはなる。

## DoD

- [x] `docs/adr/ADR-018-pro-sonnet-operation.md` が存在し、テーゼ維持・前提反転・外出し方針・表 v3・非対称ルール強化を含む
- [x] `SKILL.md` frontmatter description に Pro 前提の発動条件と免除4条件がある
- [x] `SKILL.md` の表が v3（列の意味＝判断をセッション内/外）
- [x] `scripts/critic.sh --dry-run` が有効な JSON を出し、キー未設定時に非ゼロ終了する
- [x] `scripts/model-mode.sh` が sonnet 入力で Pro 運用行を出し、fable/opus 実体確認時は従来行を出す
- [x] README モデル運用節に Pro 運用の行がある
- [x] 既存テスト（`uv run --python 3.12 --with pytest --with pytest-asyncio python -m pytest tests -q`）が全件 pass（181 passed。system の python3.9 では requires-python>=3.12 のため既存テストが収集エラーになる＝既知・本 PR 外）
- [x] `bash -n` が全 .sh で通る
- [x] ADR-018 に対する critic 実施（Kagami サブエージェント、上記）。従量 API 版 `scripts/critic.sh` での再反証はオーナーの API キー準備後に任意で実施

## VERIFY 記録

- **レビュー結果**: 本タスクは team-lead（Fable 5）が自前で実装したため二段階レビューは未実施。critic の反証を v2 に反映済み。オーナーレビュー（PR）を最終ゲートとする。
- **修正ループ回数**: 1（critic 反映）

## エビデンス

```
$ for m in claude-sonnet-5 claude-opus-5 claude-fable-5; do echo "{\"model\":\"$m\"}" | bash scripts/model-mode.sh | cut -c1-90; done
[team-lead=sonnet effort=high src=hook] Pro 運用（ADR-018）: fable-class ON: complexity≥S（ほぼ全タ
[team-lead=opus effort=high src=hook] Opus モード（ADR-017）: fable-class ON: complexity≥M or r
[team-lead=fable effort=high src=hook] Fable モード: fable-class は中〜大規模タスクで発動（ADR-017）
$ echo '{}' | bash scripts/model-mode.sh | cut -c1-90
[team-lead=fable?(未確認) effort=high src=settings] Pro 運用（ADR-018）: fable-class ON: complexi

$ CRITIC_NO_ENV_FILES=1 scripts/critic.sh --target docs/adr/ADR-018-pro-sonnet-operation.md --ctx docs/adr/ADR-017-opus-fable-parity.md --dry-run | jq '{model,max_tokens,stream,thinking,output_config}'
{"model":"claude-opus-5","max_tokens":32000,"stream":true,"thinking":{"type":"adaptive"},"output_config":{"effort":"xhigh"}}
$ env -u ANTHROPIC_API_KEY CRITIC_NO_ENV_FILES=1 scripts/critic.sh --target README.md; echo exit=$?
critic.sh: ANTHROPIC_API_KEY が見つかりません。 ... exit=1

$ uv run --python 3.12 --with pytest --with pytest-asyncio python -m pytest tests -q
182 passed in 19.44s（critic 反映後）
$ for f in scripts/*.sh .claude/hooks/*.sh; do bash -n "$f" || echo "FAIL $f"; done
（出力なし＝全件 OK）
```

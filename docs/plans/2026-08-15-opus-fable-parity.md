# plan: opus-fable-parity

- **日付**: 2026-08-15
- **担当**: team-lead（メインセッション）
- **complexity**: M
- **risk_level**: high（エージェント間プロトコル＝スキル発動条件・フック登録の変更を含む。pm-estimation「強制 high」該当）
- **ADR参照**: `docs/adr/ADR-017-opus-fable-parity.md`

## SPEC

- **要求の再記述**: オーナーのプラン変更で Fable 5 が使えなくなる。team-lead を Opus に切り替えても Fable 級の品質で agent-crew を回せるよう、現状の Fable 依存を調査し、設計し（設計段階で専門家レビューを受け）、実装する。ブランチ・worktree で作業する。
- **暗黙の前提**: 既存の fable-class スキル／ADR を捨てず継承する。オーナーの介入最小化方針（確認を挟まない）を崩さない。symlink 配布のためエージェント定義の変更は全プロジェクトに効く。
- **不明点**: (自己解決) settings/effort/advisor/hook の公式仕様 → 一次情報で確認済み（ADR 実装メモ）。(オーナー判断) `~/.claude/settings.json` の書き換えはオーナー作業として残す。
- **テーゼ**: 品質はモデルではなく強制された工程から生まれる。工程の強制はドキュメントでは効かず、既定値・成果物・フックで効く。

## PLAN

### 代替案比較表

| 案 | 複雑度 | 変更範囲 | リスク | テーゼ適合 |
|---|---|---|---|---|
| A. モデル設定のみ | 低 | 1行 | 工程省略の再発 | ✗ |
| B. fable-class 既定化＋Opus 向け補強（採用） | 中 | スキル・エージェント・フック・文書 | トークン増 | ○ |
| C. 全エージェント Opus | 低 | frontmatter 一括 | レート上限・コスト | ✗（前提と矛盾） |
| E. opusplan | 低 | 1行 | 採否判断が Sonnet に落ちる | ✗ |
| F. plan mode 既定化 | 低 | 設定 | オーナー方針と衝突 | ✗ |

### ミニADR

ADR-017 本文を参照（背景・決定・理由・却下案を同文書に記載）。

### マイクロタスク一覧

| # | タスク | complexity | risk | 担当 | 対象 |
|---|---|---|---|---|---|
| T1 | fable-class スキル改訂（description・表 v2・鉄則・planning/verification・templates/plan.md） | M | medium | Sonnet | `.claude/skills/fable-class/**`, `templates/plan.md` |
| T2 | critic 新設・architect effort・pm.md 導線・learned-rules・README・旧 ADR Status | M | medium | Sonnet | `.claude/agents/{critic,architect,pm,pm-learned-rules}.md`, `README.md`, `docs/adr/fable-class-opus-adr.md` |
| T3 | `scripts/model-mode.sh` 新設、`session_start.sh` §7、`settings.json` フック登録、`start-hook-design.md` 追記 | S | high | team-lead | 同左 |

検証コマンドは各委譲プロンプトに明記（grep/head/git status）。

### 依存関係

T1・T2・T3 は対象ファイルが重ならず並列委譲可能。VERIFY は全タスク完了後にまとめて実施。

## critic

- **発動有無**: 発動（risk high）。設計段階で Alex（architect）・Hana（doc-reviewer）・critic 相当（Opus フレッシュコンテキスト、反証専任）の3件。
- **指摘と採否**:
  - Alex CRITICAL: fable-class の PLAN テンプレに risk_level がなく表 v2 が使えない → 採用（planning.md 必須項目に追加）
  - Alex MAJOR: critic 発動がドキュメント頼み → 一部採用（最終ゲート DoD に記録必須。Stop フック強制は見送り）／同時 Opus 累積 → 採用（上限）／ADR-004 未接続 → 採用
  - Hana MAJOR: 用語等値の未宣言・出典 URL なし → 採用
  - critic A（強）: PreToolUse の stdout はモデルに届かない／settings.json の model は実体と乖離／description が発動を決める → 採用（SessionStart へ移行、UserPromptSubmit 新設、実体からのモデル検知、description 書換、plan 成果物）
  - critic B（中〜強）: 同一モデルの相関盲点／指標が鈍い → 採用（効果指標を「事後欠陥のうち事前指摘率」へ、CRITICAL 却下に反論必須）。別系統モデルは Stage 2 トリガー
  - critic C（中）: Lite は抜け道と形骸化 → 採用（Lite 廃止、客観基準で二値化）
  - critic D（中）: effortLevel xhigh のグローバル副作用 → 採用（main は high 据え置き、xhigh は critic/architect のみ）
  - critic E（強）: opusplan／plan mode 未評価 → 比較を追加し却下理由を記録。UserPromptSubmit・スプリント導線1行 → 採用。段階検証 → Stage 1/2 分割
- **CRITICAL却下の反論**: critic E の「opusplan で十分」は却下 — fable-class の採否判断・修正ループ判定は実行フェーズにあり、opusplan ではそこが Sonnet になるため（判断者の格下げと引き換え）。critic E の「plan mode 既定化」は却下 — 解除にオーナー承認が要り介入最小化方針と衝突するため。

## DoD

- [x] ADR-017 が Proposed(v2) として存在し、レビュー3件の採否が本ファイルに記録されている
- [x] fable-class の description が発動の客観基準を含む／表 v2／鉄則 6-8／planning・verification 追記／templates/plan.md 存在
- [x] critic.md 新設（opus, xhigh, 読み取り専用）／architect.md に effort: xhigh
- [x] scripts/model-mode.sh が 4 ケース（hook model／transcript／settings／stdin なし）で正しく1行出力し exit 0
- [x] settings.json: session_start.sh が PreToolUse に無く SessionStart にあり、UserPromptSubmit に model-mode.sh が登録され JSON 妥当
- [x] README モデル運用節／pm.md ステップ-1／learned-rules 1行／旧 ADR Status 採択
- [x] 仕様準拠レビュー・品質レビュー（新規コンテキスト）が APPROVED または指摘の採否記録済み
- [x] メモリ model-division 更新（リポジトリ外）

## VERIFY 記録

- **仕様準拠レビュー**（新規コンテキスト Sonnet）: MAJOR 1（`SKILL.md` frontmatter の `effort: xhigh` は ADR v2 の決定外 → 採用・削除）、MINOR 1（`start-hook-design.md` の追記が変更ファイル表に未記載 → 採用・表に追加）。他 12 項目は一致。
- **品質レビュー**（Sora, qa）: APPROVED_WITH_COMMENTS。MINOR: `model-mode.sh` の `tail -n 200` はツール呼び出しの多いターンで assistant 行を取りこぼし settings へ縮退（10万行 transcript で再現）→ 採用・`grep '"type":"assistant"' | tail -n 50` に変更（実測 0.12s）。他（PPID ロック・`set -u`・settings.json 配置・frontmatter YAML）は問題なし。
- **修正ループ回数**: 1回（採用3件を team-lead が直接修正、再テスト済み）。

## エビデンス

```
$ jq -e '(.hooks.SessionStart|length)==2 and (.hooks.UserPromptSubmit|length)==1 and ((.hooks|has("PreToolUse"))|not)' .claude/settings.json
true
$ bash -n scripts/model-mode.sh && bash -n .claude/hooks/session_start.sh && echo OK
OK
$ echo '{"model":"claude-opus-5","effort":{"level":"high"}}' | scripts/model-mode.sh
[team-lead=opus effort=high src=hook] fable-class ON: complexity≥M or risk≥medium → SPEC/PLAN を docs/plans/ に残す, ミニADRは critic(Kagami,opus) で反証してから確定, ルーティング表 v2 = .claude/skills/fable-class/SKILL.md（ADR-017）
$ echo '{"transcript_path":"<実セッションの jsonl>"}' | scripts/model-mode.sh   # 0.12s
[team-lead=fable effort=high src=transcript] Fable モード: fable-class は中〜大規模タスクで発動（ADR-017）
$ scripts/model-mode.sh </dev/null; echo exit=$?
[team-lead=fable effort=high src=settings] Fable モード: ...   exit=0
$ grep -n "^## モデルルーティング表" .claude/skills/fable-class/SKILL.md
18:## モデルルーティング表 v2（risk_level 連動）
$ sed -n 4,6p .claude/agents/critic.md
tools: Read, Grep, Glob / model: opus / effort: xhigh
$ grep -n "ステップ-1" .claude/agents/pm.md → 74 / grep "^## モデル運用" README.md → 182 / fable-class-opus-adr.md ステータス: 採択
```

既知の未対応（本 PR 範囲外）: `scripts/privacy-check.sh` が macOS 標準 bash 3 で `declare -A` に失敗する（既存不具合、Stop フックは `|| true` で無害化済み）。

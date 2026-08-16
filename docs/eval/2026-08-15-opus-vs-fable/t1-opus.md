# ADR-017 v2 反証レビュー

## 1. モデル検知が settings.json に落ち「Fable モード」を誤注入する — 強

根拠: `~/.claude/settings.json` は実測で `"model": "fable"`（実体は Opus、ADR:20）。`model-mode.sh:50-53` の終端フォールバックがそこを読み、`echo '{}' |` 実行で `[team-lead=fable src=settings] Fable モード`（:73-74 の緩い分岐）を出力した。`.model` は保証なし（ADR:157）、transcript に assistant 行が無い初回ターン＝注入が最も効くべき瞬間にこの経路が使われる。ADR:99 の誤判定がそのまま残る。
修正提案: `src=settings` かつ `fable` は Fable 分岐へ行かせず ON ＋「実体未確認」に倒す。

## 2. UserPromptSubmit が cwd 次第で無言死し、SessionStart はロックで欠落する — 強

根拠: `.claude/settings.json:90` は素の相対パス `scripts/model-mode.sh`。同ファイル内の他 3 件は全て `cd "$(git rev-parse --show-toplevel)"` 付き（:45, :54, :62）。`docs/` から実行すると exit 127（実測）。非 2 終了は止まらないので「毎ターン想起」が無言で消える。`session_start.sh:14-18` の `/tmp/claude_session_start_${PPID}.lock` も PreToolUse 時代の遺物で削除されず実測 3 件残存、PID 再利用で出力が丸ごと落ちる。
修正提案: :90 を他 3 件と同じ `cd` 付きに統一。ロック機構を撤去。

## 3. 非対称ルールのトリガー語「CRITICAL」が critic の語彙に無い — 強

根拠: ADR:68・`critic.md:71`・`plan.md:52`・`verification.md:29` は「CRITICAL 指摘の却下」を反論義務の条件にする。だが `critic.md:26,49` の報告フォーマットは強さ＝**強/中/弱**と総合判定のみで CRITICAL を出さない（:24 の同語はレビュアー向けの別規定）。「CRITICAL ではなかった」で義務を回避でき、同じ Opus が発注者と最終審を兼ねることへの唯一の歯止めが空振りする。
修正提案: critic.md の強さ表記を CRITICAL/MAJOR/MINOR に統一（または「強＝CRITICAL」と明記）。

## 4. 発動基準 (a)(b) が循環し、残る (c) が過剰包摂する — 中

根拠: complexity・risk_level は `planning.md:56-57` の「マイクロタスク分解」＝ PLAN で付与する項目。入場条件が入場後にしか存在しない成果物に依存している。事前判定できるのは (c)(d) のみだが、(c) は「新規ファイル作成」を含むためほぼ全タスクが該当し、ADR:62 が Lite を却下した理由（形骸化）を別経路で招く。
修正提案: 入場を (c)(d) に限定し (c) から「新規ファイル作成」を外す。(a)(b) は工程深度の分岐へ降格。

## 5. Stage 2 の判断材料が構造上生成されない — 中

根拠: 効果指標は「レトロで数える」（ADR:69）だが `retro.md` に critic の記述は皆無＝ADR:36 が自ら禁じた「書くだけ」型。レート上限の計測手段も無い（ADR:137、Issue 未作成）。Stage 2 の入力 (b)(c) が欠測し、D 案トリガーは発火しない。
修正提案: retro.md ステップ 2.7 の隣に critic 事前指摘率の記録手順を新設し、計測 Issue を Stage 1 に含める。

## 総合判定

**条件付き差し戻し**（条件: 1・2・3 を Stage 1 内で修正。放置すると強制力が効かない）。

### 反証レビュー対象
ADR-017 v2: Fable 5 不在時に Opus を team-lead に据え、既定値・成果物・フックで fable-class 工程を強制する。

### 反証命題

1. **Stage 1 の「強制」は全部テキストで、テーゼ後半（書くだけは採用しない）と自己矛盾** — 強さ: 強
   根拠: 採用手段は SKILL.md description（`.claude/skills/fable-class/SKILL.md:2-9`）、鉄則7（同 :64）、`pm.md:74-76` の1行、UserPromptSubmit の1行注入（`scripts/model-mode.sh:81`）。全てモデル宛の文言で、失敗パターン横断表「規約はフック等で強制しないと効かない」に該当。plan 成果物を欠く PR を検出する主体がない（`.github/pull_request_template.md` に plan 欄なし、Stop フックは Stage 2）。
   修正提案: PR テンプレのチェックリストに「`docs/plans/` リンク（対象外なら complexity/risk と理由）」を必須化。フック不要で機械可読な足跡になる。

2. **model-mode.sh は最重要の第1ターンで「Fable モード」を誤注入する** — 強さ: 強
   根拠: `scripts/model-mode.sh:38-47` は transcript の assistant 行を探すが、セッション初回の UserPromptSubmit 時点では存在せず、:51-54 で `~/.claude/settings.json` に落ちる。現状値は `"model": "fable"`（jq で確認）。タスクが定義される第1ターンに `Fable モード` 行が注入され fable-class OFF を宣言する。§1 のオーナー作業が済むまで毎セッション再現し、§6 が自ら認めた「設定だけ見ると誤判定」を初手で踏む。
   修正提案: fail-closed。`src=settings|none` では Fable と断定せず非Fable 側の行を出す。

3. **critic 効果指標の計測主体がなく Stage 2 トリガーは発火しない** — 強さ: 中
   根拠: `.claude/agents/retro.md` を `critic|Kagami|効果指標` で grep → 該当は `priority-critical` ラベルのみ（:625）。段階移行表 (a)〜(d) は全て「レトロで数える」前提だが手順にも成果物にも項目がない。D案・xhigh 拡大・advisor の判断材料が永久に空欄。
   修正提案: `retro.md` に「`docs/plans/*` の critic 節と事後欠陥の突合（N と的中数）」を1項追加し、レトロ文書にフィールドを設ける。計測は Stage 1 に含める。

4. **「symlink 配布で全プロジェクトに効く」前提が実体と異なる** — 強さ: 中
   根拠: `ls -la ~/.claude/agents/` は 2026-04-20 付の通常ファイル（symlink でない）。qa/security の xhigh を Stage 2 送りにした理由（§3）が崩れ、逆に `architect.md` の xhigh も他へ伝播しない。副作用の見積りが両方向で誤り。
   修正提案: 配布方式を確認して §3 を訂正し、qa/security の xhigh をローカルで Stage 1 に入れるか判断し直す。

5. **session_start.sh の1回ロックが compact 時の再注入を潰す** — 強さ: 弱
   根拠: `.claude/hooks/session_start.sh:12-16` の PPID ロック。SessionStart は compact でも発火するが §7 も出ない。UserPromptSubmit が補うため致命ではない。
   修正提案: 入力 `source` が compact/resume ならロックを無視し §7 のみ出す。

### 総合判定
条件付き差し戻し（条件: 命題1・2の修正、3の計測手順を Stage 1 に含める）

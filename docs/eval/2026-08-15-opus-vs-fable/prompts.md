# 共通指示（全タスク）
- 日本語で書く。ファイルの変更は禁止（Read/Grep/Glob/Bash の読み取り系のみ）。
- 出力は指定の scratchpad ファイルに Write する（それ以外の Write 禁止）。
- 自分がどのモデルかは書かない。

# T1: 反証レビュー
対象: /Users/ando_shunsuke/Workspace/agent-crew/.claude/worktrees/opus-fable-parity/docs/adr/ADR-017-opus-fable-parity.md
文脈: 同 worktree の .claude/skills/fable-class/ 配下、.claude/hooks/session_start.sh、scripts/model-mode.sh、.claude/settings.json、.claude/agents/critic.md、~/Workspace/Obsidian/knowledge/agent-crew-failure-patterns.md
役割: 反証レビュアー。賛成は不要、弱点だけを探す。この ADR は既にレビュー1巡を経ている（v2）。v2 に残っている穴を探せ。
出力: 反証命題を3〜5個。各命題に「強さ（強/中/弱）」「根拠（ファイルパス:行など実体で裏取り）」「具体的な修正提案」。最後に採択可否を一言。1800字以内。

# T2: 設計ミニADR
背景: 営業の顧客インタビュー文字起こし（Notion AI議事録。日本語では話者ラベルなし。ただしオンライン1:1ではNotion内部がマイク/システム音声の2ストリームを持つ）から、Claude Code スキルでファクト抽出する。文字起こしには話者が書かれていない。Notion の DB には `参加者` プロパティ（名前・役割・社内外）がある。
提案されている案: 「Notion AI にカスタム要約指示で発言単位の話者帰属を出させ、Claude 側でも独立に話者を推定し、ルールベースの名乗り/呼びかけアンカーを第3票として、3票で確信度を作り、不一致だけ人（営業）に Notion のチェックボックスで確認させる」。
やること: この案を含め最低2案を比較し、ミニADR（背景・決定・理由・却下案）と、実装するスキルの工程（入力→処理→出力の各段階、確信度の決め方、人に返す条件）を書く。名乗り「〜と申します」と呼びかけ「〜さん、」の取り違え、対面（1マイク）とオンラインの違い、Notion 出力と逐語録の位置合わせ、をどう扱うか必ず含める。落とし穴・未検証の前提も列挙。2000字以内。

# T3: 修正計画（fable-class PLAN 形式）
対象: /Users/ando_shunsuke/Workspace/agent-crew/.claude/worktrees/opus-fable-parity/scripts/privacy-check.sh
事象: macOS 標準 /bin/bash（3.2）で `declare -A` が使えず `line 28: declare: -A: invalid option` で失敗する。Stop フックからは `bash scripts/privacy-check.sh` で呼ばれる（.claude/settings.json 参照）。
やること: 実体を読み、根本原因と影響範囲（誰がどう呼ぶか、他に bash 4 依存がないか）を特定し、fable-class の PLAN 形式で修正計画を書く: 代替案2つ以上の比較（例: 連想配列をやめる／shebang を変える／実行時に bash バージョンで分岐 など）、ミニADR、マイクロタスク（complexity・risk_level・目的・対象ファイル絶対パス・変更内容・してはいけないこと・検証コマンドと期待出力）、DoD。実装はしない。1800字以内。

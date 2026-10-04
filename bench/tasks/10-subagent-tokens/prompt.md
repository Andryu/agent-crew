# タスク: トークン集計をサブエージェント別にも出す

dashboard/server/discovery.py は ~/.claude/projects/ 配下を走査してアクティブな
セッション（transcript の *.jsonl）を発見し、dashboard/server/tokens.py の
TranscriptAggregator が部門別トークン消費を集計している。

Claude Code はサブエージェントを使うと、メインセッションの transcript と同じ場所に
`<セッションID>/subagents/agent-<ID>.jsonl` という専用 transcript と、
`agent-<ID>.meta.json`（"agentType" フィールドを含む）を書く。現状はこれが
発見されず、サブエージェントの消費が集計から漏れている。

## 動き

- discovery がサブエージェント transcript も発見対象にする。発見結果の各セッションに
  persona フィールド（解決できなければ None）を持たせ、メインセッション自身は
  常に None のままにする。
- サブエージェントの persona は meta.json の agentType を、既存の
  dashboard/server/enrich.py の persona_for と同じ規則でペルソナ名に解決する。
- サブエージェントのセッションは親の cwd と部門を引き継ぐ。セッションIDは
  親のIDを含みつつ、親と区別できる別のIDにする。
- TranscriptAggregator.register が persona も受け取れるようにし（従来どおり
  2引数でも呼べること）、ペルソナ別合計を返す persona_totals() を追加する。
  persona が解決できていない（None の）エントリは persona_totals に含めない。

## 受け入れ基準

- subagents/ 配下の transcript が直近ウィンドウ内に更新されていれば発見され、
  meta.json の agentType からペルソナが解決される。
- meta.json が無い・壊れている・agentType が文字列でない場合も落ちず、
  そのサブエージェントは persona = None のまま発見される。
- サブエージェント transcript の更新が古ければ、親がアクティブでも発見されない。
- 部門別 totals() の形と値は今まで通り（後方互換）。同一 message.id が複数行・
  複数回の読み込みに現れても二重計上しない。
- （加点）サーバの WebSocket 初期メッセージとトークン配信に、ペルソナ別集計の
  "personas" キーが載る。

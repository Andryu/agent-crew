# レトロスペクティブ — sprint-05

生成日: 2026-04-23
生成者: みゆきち（retro エージェント）

---

## スプリント概要

**スプリントゴール**: Alex（architect）の Bash ツール問題（#43）解消 + トークン消費最適化実装（#36）+ セッション中断検出機構の設計（#39）

**期間**: 2026-04-23（深夜セッション + 朝セッションの2セッション）
**結果**: 全 6 タスク DONE / QA 2 件 APPROVED

---

## タスク完了サマリー

| タスク | 担当 | complexity | 実行時間 | retry_count | qa_result |
|--------|------|-----------|---------|-------------|-----------|
| alex-bash-impl | Riku | S | 1分 | 0 | - |
| alex-bash-qa | Sora | S | - | 0 | APPROVED |
| token-opt-design | Alex | M | 4分 | 0 | - |
| token-opt-impl | Riku | M | 2分 | 0 | - |
| token-opt-qa | Sora | S | - | 1 | APPROVED |
| session-interrupt-design | Alex | M | 28分 | 0 | - |

> 実行時間は start → done イベント間の diff から算出。Sora は start イベントを記録しないため「-」になっている。
> alex-bash-impl（深夜00:06完了）と alex-bash-qa（朝08:25完了）の間に約8時間のセッションブレイクがある。Sora の内部エラー（スマホ Remote Control のスリープによる接続切断と推定）がこの間に発生した。

---

## 集計

- 完了タスク数: 6 / 6（完了率 100%）
- ブロック発生: 0 件
- 総リトライ回数: 1（token-opt-qa）
- QA 差し戻し率: 50%（CHANGES_REQUESTED 1 件 / QA タスク 2 件）
- CRITICAL/MAJOR/MINOR 指摘（QA判定内）: MAJOR 1 件（architect.md の Bash 上限ルール 5回→3回の修正漏れ）

---

## Complexity 精度評価

| complexity | タスク数 | 平均実行時間 |
|-----------|---------|------------|
| S | 3 | 計測不可 or 1分 |
| M | 3 | 11分（4分・2分・28分の平均） |
| L | 0 | - |

> session-interrupt-design が M で 28 分かかった。設計タスクは内容の深さで時間差が大きく、M という粒度では精度が低い可能性がある。

---

## KPT — Keep / Problem / Try

### Keep（続けること）

**K-1: Alex への Bash ツール付与が自律性向上に即効いた**
sprint-04 T-1 として挙げた課題（Alex の Bash ツール未付与）を sprint-05 の最初のタスク（alex-bash-impl）で解消した。付与後わずか 27 秒で Alex が token-opt-design の start イベントを自己発行し、設計に着手した。queue.sh done / handoff の Yuki 代行が不要になり、スプリントの自律性が明確に向上した。

**K-2: セッション中断検出機構の設計完了**
session-interrupt-design が 28 分の時間をかけて詳細な設計書を作成した。#39 の課題に対する設計は独立して進められることが実証された。Sprint-06 以降の実装に向けた基盤が整った。

**K-3: self-review チェックリストの効果測定継続（sprint-04 K-3 の追跡）**
sprint-04 導入後の 2 スプリント目。Sora が 1 件差し戻しを発見しており、チェックリストが機能していることを示す（差し戻し自体は悪ではなく、見落としを QA で捕捉できたことを評価する）。

---

### Problem（問題だったこと）

**P-1: token-opt-qa で差し戻し — 計画仕様と実装の齟齬**
sprint-05-plan.md のタスク 1 には「Bash 実行は 1 タスクあたり最大 5 回を目安とする」と記載されていた。しかし実装（token-opt-impl）では architect.md に 3 回上限ルールが記載された。Sora の QA で不一致を検出し、差し戻しが発生した。計画文書と実装が乖離していた原因は、設計書（token-opt-design.md）が ADR-004 の値（3 回）を採用したためだが、Riku が計画文書を参照せず設計書のみを参照したことが一因と推定される。

**P-2: Sora 内部エラーによる作業中断（スリープ推定）**
深夜セッションで alex-bash-impl を完了後、スマホ Remote Control のスリープにより接続が切断され、Sora が内部エラーで落ちた（推定）。これにより alex-bash-qa の実施が朝セッション（約 8 時間後）まで遅延した。セッション中断問題は #39 で検出機構を設計中だが、現時点では中断時の通知手段がない。

**P-3: PR Test Plan のチェック漏れが繰り返し（前スプリントと同じ指摘）**
PR 作成時に Test Plan のチェックリスト未記入・未確認をオーナーに指摘された。sprint-04 でも同じ指摘を受けており、繰り返し問題となっている。PR テンプレートや Riku の実装完了チェックリストに Test Plan 確認が明示的に含まれていないことが根因と考えられる。

**P-4: スプリント完了後のコミット確認をオーナーに聞いた（介入最小化違反）**
スプリント完了後、コミットしてよいかオーナーに確認するメッセージを送った。これは介入最小化方針（MEMORY.md: Keep going）に反する。コミットの判断基準が定義されていないため、エージェントが都度確認を選択している。

**P-5: Alex がサブエージェントコンテキストで Bash が使えない問題の継続**
alex-bash-impl で Bash を付与したが、タスク 3（token-opt-design）実行時に Alex はサブエージェントとして起動された。このコンテキストでは Bash が利用できなかったとの報告があった。ただし token-opt-design のイベントを見ると Alex が start/done を自己発行できているため、実際の制約の詳細は不明確。session-interrupt-design のみがサブエージェント実行だった可能性がある。

**P-6: みゆきち自動起動の仕組みがない**
スプリント完了後、みゆきちによるレトロスペクティブはオーナーが手動で依頼している。sprint-03 以降毎スプリント手動依頼が発生しており、Yuki のスプリント完了報告にレトロ自動起動が含まれていない。

---

### Try（次に試すこと）

**T-1: Riku の実装チェックリストに「計画文書との仕様確認」を追加する**
token-opt-qa 差し戻しの根因は計画文書と設計書の数値齟齬を Riku が検出できなかったこと。実装開始前に「計画文書（sprint-XX-plan.md）の対象タスク仕様と設計書の差分を確認する」項目を Riku の self-review チェックリストに追加する。

**T-2: PR 作成時の Test Plan 確認をテンプレートに明示する**
P-3 の繰り返し問題を解消するため、PR テンプレートに Test Plan チェックリスト確認が含まれているかを確認し、含まれていない場合はテンプレートを修正する。また Riku の実装完了基準にも「PR の Test Plan が記入されているか確認する」を追加する。

**T-3: コミット判断基準を CLAUDE.md に明文化する**
P-4 の介入最小化違反を防ぐため、「スプリント完了後はオーナー確認なしにコミット・PR 作成してよい」というルールを CLAUDE.md または pm.md に記載する。ブランチ戦略（feat/sprint-XX-clean を使う）も合わせて記載する。

**T-4: Yuki のスプリント完了報告にみゆきち呼び出しを組み込む**
P-6 を解消するため、Yuki の完了報告フォーマット末尾に「@retro を呼んでレトロスペクティブを実施」を標準手順として追加する。pm.md の「スプリント完了時の手順」に明記する。

**T-5: Alex のサブエージェント実行時の制約を文書化する**
P-5 の根本原因を明確にするため、Alex がサブエージェントとして実行された場合に Bash が使えるかどうかを次スプリントで検証し、結果を architect.md の注意事項として記録する。

---

## 特記事項

### sprint-04 の T-1 実現確認（Alex Bash 付与の効果）

sprint-04 T-1 で「Alex に Bash ツールを付与して自律的に queue.sh を呼べるようにする」と提言した。sprint-05 で実際に付与した結果：

```
タイムライン:
1. 08:25:28 — alex-bash-qa DONE（Sora が APPROVED を返す）
2. 08:25:55 — token-opt-design で Alex が自律的に start を記録（27秒後）
3. 08:29:47 — Alex が自律的に done を記録
```

sprint-04 では Alex の設計タスクに start イベントがなかった（Bash なしのため）。sprint-05 では Alex が start/done 両方を自己発行できた。Yuki の queue.sh 代行コストが削減された。

### token-opt-qa 差し戻しの詳細

```
差し戻しの原因:
- sprint-05-plan.md タスク 1: 「Bash 実行は 1 タスクあたり最大 5 回を目安」
- ADR-004 実際の決定: 3 回上限
- architect.md 実装: 3 回上限（設計書 ADR-004 に準拠）
- 計画文書が古い値のまま残っていた

結果: Sora が「計画との不一致」を検出し CHANGES_REQUESTED
修正: architect.md を 5 回→3 回に変更（実際は既に 3 回で正しかったため、差し戻し理由は計画文書の更新漏れが根本）
最終: APPROVED（2 回目のレビューで通過）
```

---

## lessons.json への記録

以下の 6 件を `~/.claude/_lessons.json` に記録した。

| lesson ID | category | priority_score | type |
|-----------|----------|---------------|------|
| agent-crew-sprint-05-qa-001 | qa-process | 2 | failure-pattern |
| agent-crew-sprint-05-reliability-001 | reliability | 4 | failure-pattern |
| agent-crew-sprint-05-process-001 | process | 6 | failure-pattern |
| agent-crew-sprint-05-process-002 | process | 4 | failure-pattern |
| agent-crew-sprint-05-tooling-001 | tooling | 4 | observation |
| agent-crew-sprint-05-process-003 | process | 3 | failure-pattern |

---

## エビデンスゲート結果

ゲート通過条件（priority_score >= 4 かつ evidence >= 1 件 かつ issue_url == null）を満たした lesson:

| lesson ID | priority_score | 状態 | Issue URL |
|-----------|---------------|------|-----------|
| agent-crew-sprint-05-reliability-001 | 4 | Issue 化済み | TBD（記録後に更新） |
| agent-crew-sprint-05-process-001 | 6 | Issue 化済み | TBD（記録後に更新） |
| agent-crew-sprint-05-process-002 | 4 | Issue 化済み | TBD（記録後に更新） |
| agent-crew-sprint-05-tooling-001 | 4 | Issue 化済み | TBD（記録後に更新） |

Issue 化実施日: 2026-04-23

---

## 次スプリントへの提言

1. **Riku の実装チェックリストに計画文書確認を追加する**（T-1）
   同じ差し戻しの繰り返しを防ぐ。実装コストは S（テキスト追記のみ）。

2. **PR Test Plan チェック漏れを恒久対処する**（T-2）
   2 スプリント連続で同じ指摘。テンプレートレベルで対処しない限り繰り返す。

3. **コミット判断基準を明文化して介入最小化を徹底する**（T-3）
   オーナーが明示的に「Keep going」を指示しているにもかかわらず確認が発生している。

4. **みゆきち自動起動を pm.md に組み込む**（T-4）
   スプリント完了毎に手動依頼が発生している。pm.md の完了手順に追加するだけで解消できる。

5. **session-interrupt-design の実装（Sprint-06 候補）**
   設計が完了した #39 を実装し、セッション切断による中断を検出・通知できるようにする。

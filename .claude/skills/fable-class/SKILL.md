---
name: fable-class
description: >
  最上位モデル（Fable 5）不在時に Opus + Sonnet の役割分担で Fable 級品質を出す
  工程スキル。メインセッションが Fable 5 でない場合、次のいずれかのタスク開始時に
  必ず発動する: (a) complexity M 以上 (b) risk_level medium 以上
  (c) 設計判断・新規ADR・新規ファイル作成・複数ファイル横断の変更を含む
  (d) 「fable-class」「しっかり設計して」等の指示。Fable 5 がメインの場合は
  中〜大規模タスクで発動。complexity S 相当で設計判断のない小タスクは対象外。
---

# fable-class

## 概要

モデルの知能差は、多くの場合「工程の省略」として現れる。検証をしない、代替案を出さない、仕様が曖昧なまま実装に進んでしまう——こうした省略が積み重なることで、最終的な成果物の品質差になる。逆に言えば、工程そのものを強制すれば、モデル間の品質差は大幅に縮まる。このスキルは、最上位モデル（Fable）が使えない状況でも、Opus をオーケストレーターに据えて工程を強制することで、Fable 級の成果を再現するためのものである。

## モデルルーティング表 v2（risk_level 連動）

`Agent` 呼び出し時の `model` パラメータで上書きする。frontmatter を `opus` にするのは `critic` のみ。risk_level は planning.md の必須項目として team-lead が付与する（pm-estimation.md 基準）。

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
| 仕様ドライラン（planning.md） | haiku / sonnet | 同 | 同 |

いずれの工程も、実装・レビュー・ドライランはタスクごとに新規起動したフレッシュコンテキストで行う（前段の思考のノイズを引き継がせない）。

**同時 Opus 上限**: 1タスクにつき同時に走らせる Opus サブエージェントは **critic ＋ 1本まで**。Sora(opus) と Kai(opus) は直列で回す。C案（全 Opus 化）に累積効果で近づくのを防ぐ。
**レート上限到達時**: まず ADR-004 のリカバリ手順（タスク状態の保全）を実行し、その後 Sora → Alex の順に sonnet へ戻す（Kai・critic は戻さない）。実行主体は上限で止まったセッションではなく、次のセッションまたはオーナー。

## ワークフロー（必須工程）

以下の5フェーズを、この順序で必ず実行する。各フェーズの詳細な進め方は該当する references/ 配下のファイルを Read し、その内容に従うこと。

1. **SPEC** — 要求の再記述と仕様確定。詳細は `references/planning.md` の SPEC 節を参照。
2. **PLAN** — 代替案比較・意思決定・マイクロタスク分解。詳細は `references/planning.md` の PLAN 節を参照。マイクロタスク分解後は、委譲前に仕様ドライラン（同 PLAN 節参照）を必ず実施する。ミニADRは risk_level medium 以上なら critic（Kagami, opus）で反証してから確定する（verification.md 参照）。
3. **DELEGATE** — Sonnet サブエージェントへの実装委譲。詳細は `references/delegation.md` を参照。
4. **VERIFY** — 新規コンテキストでの二段階レビュー。詳細は `references/verification.md` を参照。
5. **CONVERGE** — 修正ループ（上限あり）を経て、エビデンス付きの完了報告を作成する。詳細は `references/verification.md` を参照。

## 鉄則

1. **工程をスキップしない** — 「簡単そうだから」は工程省略の理由にならない。SPEC・PLAN・VERIFY を飛ばして DELEGATE に進んではならない。
2. **実装者に判断させない** — 仕様の曖昧さは実装者に解釈させず、計画者（オーケストレーター）が事前に潰す。
3. **自分の書いたものを自分でレビューしない** — 実装したエージェント自身にも、オーケストレーター自身にも、その成果物をレビューさせない。
4. **主張ではなくエビデンスで完了を示す** — 「動作確認しました」ではなく、テスト出力・実行結果そのものを完了報告に含める。
5. **修正ループは同一タスクにつき最大2回** — 1ループ＝修正のDELEGATE 1回＋再VERIFY 1回。初回VERIFYの後、修正ループは最大2回（VERIFYは初回込みで最大3回、修正DELEGATEは最大2回）。2回の修正ループで収束しなければ作業を止め、ユーザーにエスカレーションする。ここでいう「同一タスク」とは、planning.md で分解したマイクロタスク単位を指す。
6. **コンテキスト衛生** — team-lead は大きなファイルの通読・広範囲検索を Explore/Sonnet に委譲し、自分のコンテキストを判断用に温存する（コンテキストが長いほど初期の制約を忘れるため）。
7. **工程は成果物で残す** — Full 発動時は SPEC・PLAN・DoD・critic 採否を `docs/plans/<YYYY-MM-DD>-<slug>.md`（テンプレ: `templates/plan.md`）に書き、PR 本文からリンクする。書いていない工程は踏んでいないものとみなす。
8. **同時 Opus 上限** — 1タスクにつき同時に走らせる Opus サブエージェントは critic ＋ 1本まで。

## メインセッションのモデル別の扱い

### Fable 5 が使える場合

Fable が使える環境でも、このスキルは不要にはならない。むしろ Fable 自身がオーケストレーターを務めることで、同じ5フェーズ工程がさらに高い精度で回り、品質はいっそう向上する。

### Fable 5 が使えない場合（Opus 等）

メインセッションが Fable 5 でない場合、frontmatter の description に定義した基準（(a) complexity M 以上 (b) risk_level medium 以上 (c) 設計判断・新規ADR・新規ファイル作成・複数ファイル横断の変更を含む (d) 「fable-class」「しっかり設計して」等の指示）のいずれかに該当するタスクでは、このスキルを必ず発動する。背景と根拠は ADR-017 を参照。

---
name: fable-class
description: >
  最上位モデル不在時に、工程の強制と判断の外出しで Fable 級品質を出す工程スキル。
  メインセッションが Opus 以上でない場合（Pro/Sonnet 運用、ADR-018）は
  complexity S 以上＝ほぼ全タスクで必ず発動する。対象外は「変更が1ファイル・
  既存関数への局所修正・そのファイルのテストが既にある・設計判断を含まない」の
  4条件をすべて満たすものに限る（免除は complexity の自己申告ではなく、ファイル数と
  テスト有無を rg/fd/git status で確認して判定する）。メインが Opus の場合は ADR-017 基準
  （(a) complexity M 以上 (b) risk_level medium 以上 (c) 設計判断・新規ADR・
  新規ファイル作成・複数ファイル横断の変更を含む (d) 「fable-class」「しっかり設計して」
  等の指示）で発動。Fable 5 がメインの場合は中〜大規模タスクで発動。
---

# fable-class

## 概要

モデルの知能差は、多くの場合「工程の省略」として現れる。検証をしない、代替案を出さない、仕様が曖昧なまま実装に進んでしまう——こうした省略が積み重なることで、最終的な成果物の品質差になる。逆に言えば、工程そのものを強制すれば、モデル間の品質差は大幅に縮まる。このスキルは、最上位モデル（Fable）が使えない状況でも、工程を強制することで Fable 級の成果を再現するためのものである。Opus がオーケストレーターなら工程の強制で足りる（ADR-017）。Opus すら恒常的に使えない Pro/Sonnet 運用では、オーケストレーター自身が最弱の環になるため、加えて判断をセッション外（従量 API の critic と `rg`/`fd`/`jq`/テストの決定的コマンド）に外出しする（ADR-018）。

## モデルルーティング表 v3（判断をセッション内で完結してよいか、外に出すか）

v2（ADR-017、「どのモデルを使うか」）を置き換える。**v3 の列の意味は「その工程の判断をセッション内（team-lead）で完結してよいか、セッション外に出すか」**であり、モデル名はその帰結として書く。前提: team-lead は Opus 以上でない（Pro/Sonnet 運用、ADR-018）。team-lead が Opus 以上に戻った場合は ADR-017 の表 v2 を使う。risk_level は planning.md の必須項目として team-lead が付与する（pm-estimation.md 基準）。

| 工程 / risk_level | low | medium | high |
|---|---|---|---|
| 設計（SPEC/PLAN・ミニADR） | team-lead（`ultrathink`） | team-lead（`ultrathink`）＋ critic 推奨 | team-lead（`ultrathink`）＋ **critic 必須（従量 API）** |
| 実装 | Codex（herdr ペイン） | Codex（herdr ペイン） | Codex（herdr ペイン） |
| 仕様準拠レビュー | fresh Sonnet | fresh Sonnet | fresh Sonnet |
| 品質レビュー（Sora） | fresh Sonnet | fresh Sonnet | fresh Sonnet ＋ **critic** |
| セキュリティ（Kai） | fresh Sonnet | fresh Sonnet ＋ critic 推奨 | fresh Sonnet ＋ **critic** |
| ドキュメントレビュー（Hana） | fresh Sonnet | fresh Sonnet | fresh Sonnet |
| 探索・列挙・件数確認 | **`rg`/`fd`/`jq`/テスト（LLM に投げない）** | 同 | 同 |
| 仕様ドライラン（planning.md） | fresh Sonnet | 同 | 同 |
| critic | 不要 | 従量 API（推奨） | **従量 API（必須）** |
| 採否判断 | team-lead | team-lead（CRITICAL 却下不可） | team-lead（CRITICAL 却下不可） |

- **設計 ＝ team-lead（`ultrathink`）**: 判断はセッション内で行うが、そのターンだけ思考を深める。high では critic を必ず通す。medium で省略する場合は plan に理由を1行残す。
- **実装 ＝ Codex（herdr ペイン）**: 実装をプラン上限の外（別系統・別プロセス）に出し、team-lead のコンテキストを判断用に温存する。Codex が使えない環境では fresh Sonnet サブエージェントにフォールバックし、plan に明記する。委譲プロンプトの書き方は delegation.md のとおり（規約は Codex に届かないので明示する）。
- **レビュー ＝ fresh Sonnet**: 二段階レビュー（verification.md）は Sonnet で回してよい。high のときだけ critic を追加し、Sonnet 同士の相関した盲点を格上かつ別コンテキストで切る。
- **探索・列挙 ＝ 決定的コマンド**: 対象ファイル一覧・参照箇所・件数・存在確認は `rg`/`fd`/`jq`/テストで求め、その出力を plan に貼る。LLM（Explore/haiku 含む）に「全部挙げて」と頼まない。
- **critic ＝ 従量 API**: `scripts/critic.sh` で呼び、`docs/plans/<slug>-critic.md` を成果物として残す（verification.md 参照）。
- **fresh** は従来どおりタスクごとに新規起動したコンテキストを指す（前段の思考のノイズを引き継がせない）。

**同時 Opus 上限・レート上限到達時の手順**（ADR-017 §5）は Opus 運用時のみ適用する。Pro 運用では対象がない。

### fable-class 免除の判定レシピ（Pro 運用）

免除は自己申告（complexity）でなく客観条件で判定し、plan を書かない場合は次のコマンド出力を PR 本文に1行残す。4条件を**すべて**満たすときだけ免除。

```bash
# 1. 変更対象が 1 ファイルか（作業後に確認。着手前は触る予定のファイルを列挙する）
git status --porcelain | wc -l                    # => 1
# 2. 新規ファイル・ADR・スキル・フック・エージェント定義・設定を含まないか
git status --porcelain | rg -c '^(\?\?|A)' || echo 0                              # => 0（新規ファイルなし）
git status --porcelain | rg -c 'docs/adr|\.claude/(skills|hooks|agents|settings)' || echo 0  # => 0
# 3. そのファイルのテストが既にあるか（例: scripts/foo.py → tests/test_foo*.py）
fd 'test_foo' tests | head                       # => 1件以上
# 4. 設計判断を含まないか（代替案が1つ、または選択が結果に影響しない）— これだけは team-lead が判断し、1文で書く
```

## ワークフロー（必須工程）

以下の5フェーズを、この順序で必ず実行する。各フェーズの詳細な進め方は該当する references/ 配下のファイルを Read し、その内容に従うこと。

1. **SPEC** — 要求の再記述と仕様確定。詳細は `references/planning.md` の SPEC 節を参照。
2. **PLAN** — 代替案比較・意思決定・マイクロタスク分解。詳細は `references/planning.md` の PLAN 節を参照。マイクロタスク分解後は、委譲前に仕様ドライラン（同 PLAN 節参照）を必ず実施する。ミニADRは risk_level high なら critic（`scripts/critic.sh`、従量 API）で反証してから確定する（medium は推奨、verification.md 参照）。team-lead が Opus 以上でない場合、critic の CRITICAL は却下できない（ADR-018）。
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
8. **同時 Opus 上限（Opus 運用時のみ）** — 1タスクにつき同時に走らせる Opus サブエージェントは critic ＋ 1本まで。
9. **決定的に求まるものを LLM に判断させない** — ファイル一覧・参照箇所・件数・存在確認は `rg`/`fd`/`jq`/テストで求め、出力を plan に貼る。Sonnet の弱さは「見落とし」に出るので、見落としは決定的コマンドで潰す（ADR-018）。
10. **弱い側は強い側の CRITICAL を却下できない** — team-lead が Opus 以上でないとき、critic の CRITICAL 指摘は「修正して再 critic」か「オーナーへエスカレーション」のどちらかで処理する（ADR-018）。

## メインセッションのモデル別の扱い

### Fable 5 が使える場合

Fable が使える環境でも、このスキルは不要にはならない。むしろ Fable 自身がオーケストレーターを務めることで、同じ5フェーズ工程がさらに高い精度で回り、品質はいっそう向上する。中〜大規模タスクで発動する。

### Opus がメインの場合（ADR-017）

frontmatter の description に定義した ADR-017 基準（(a) complexity M 以上 (b) risk_level medium 以上 (c) 設計判断・新規ADR・新規ファイル作成・複数ファイル横断の変更を含む (d) 「fable-class」「しっかり設計して」等の指示）のいずれかに該当するタスクで必ず発動する。ルーティング表は ADR-017 の v2（`docs/adr/ADR-017-opus-fable-parity.md` §5）を使う。

### Opus 以上でない場合（Pro/Sonnet 運用、ADR-018）

team-lead 自身が「曖昧さを潰す側」として最弱の環になる。complexity S 以上＝ほぼ全タスクで発動し、免除は上記「免除の判定レシピ」の4条件をすべて満たすものに限る。ルーティング表は本ファイルの v3。設計判断は `ultrathink` で行い、high は `scripts/critic.sh`（従量 API）で反証してから確定する。実効モデルの判定は `scripts/model-mode.sh` が毎ターン注入する行に従う（実体確認できないときは Pro 運用に倒す）。背景と根拠は ADR-018 を参照。

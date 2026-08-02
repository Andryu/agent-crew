# 部門テンプレート（ADR-014 Phase2）

新部門開設時（`docs/org/departments.md` 第4条）に複製する最小セット。
構成の詳細は `docs/adr/ADR-014-headquarters-department-separation.md` 決定事項3を参照。

## 含まれるもの（このディレクトリに実体があるもの）

- `.claude/agents/pm.md` — プレースホルダ（部門ネイティブにカスタマイズ可）
- `.claude/skills/` — 空（部門固有スキルをここに新規作成。ADR-012の既存モデルを継続）
- `.claude/_queue.json` — 空のタスクキュー（`templates/_queue.json` と同一）
- `docs/adr/` — 空（`.gitkeep`。部門固有の設計判断をここに記録）
- `docs/sprints/` — 空（`.gitkeep`。部門固有のスプリント計画をここに記録）

## 含まれないもの（複製後に生成するもの）

本社機能（`coo.md` / `retro.md` / `security.md` / `doc-reviewer.md` / `docs/org/`）は
**symlink 配布**のため、このテンプレートには static には含めない。
symlink は絶対パスで作成され、`agent-crew` の実際の clone パスに依存するため、
複製先で `install.sh` を実行して都度生成する（テンプレート内に固定コミットすると
別マシン・別パスで壊れたリンクになるため）。

## 複製手順

1. このディレクトリを新部門リポジトリとしてコピーする。

   ```bash
   cp -r templates/department /path/to/new-department-repo
   ```

2. 複製先で本社機能（symlink）を生成する。`<agent-crewのパス>` は本リポジトリの絶対パス。

   ```bash
   bash <agent-crewのパス>/install.sh --only=hq-agents <stack> /path/to/new-department-repo
   ```

   これにより以下が symlink として生成される:
   - `.claude/agents/coo.md`
   - `.claude/agents/retro.md`
   - `.claude/agents/security.md`
   - `.claude/agents/doc-reviewer.md`
   - `docs/org`

3. 部門固有のエージェント定義（例: `.claude/agents/engineer-xxx.md`）を新規作成する。
   pm 補助ファイル（`pm-protocol.md` / `pm-estimation.md` / `pm-learned-rules.md`）も
   このタイミングで `agent-crew` からコピーする（後述の注意を参照）。
4. 部門固有のスキルを `.claude/skills/` に追加する。
5. `.gitignore` と `CLAUDE.md` を作成する（テンプレートには含まれない）。
   `CLAUDE.md` には最低限「最初に読む文書の順番」「その部門で L0（人間専権）に当たる操作」を書く。
6. `.claude/_queue.json` にスプリントタスクを追記していく。

## 複製実績（この手順で開設した部門）

| 部門 | リポジトリ | 開設日 |
|------|-----------|--------|
| 投資 | `alpha-predict-jp`（既存リポジトリへ後付け導入） | 2026-08-02 |
| 動画制作 | `stonefish-video`（新規リポジトリ） | 2026-08-03 |

## 注意

- 本社機能ファイル（symlink 側）は部門リポジトリ側で直接編集しないこと。
  編集は必ず `agent-crew`（本リポジトリ）側で行う。
- symlink は絶対パスで作成されるため、`agent-crew` を規約上のパス
  （`$HOME/Workspace/agent-crew` または `$HOME/workspace/agent-crew`）に
  clone しておくこと（ADR-014 トレードオフ参照）。
- `pm-protocol.md` / `pm-estimation.md` / `pm-learned-rules.md` は ADR-014 の注記により
  過渡期はコピーモデルを継続するため、このテンプレートには含めていない
  （部門固有エージェント作成時に別途コピーする）。`pm.md` は本社の該当ファイルを
  参照する前提で書かれているため、この3ファイルを入れ忘れると Yuki が壊れる。
- **生成された symlink は部門リポジトリで commit してよい**（投資部門・動画部門の既存実績に合わせる）。
  ただし別マシン・別パスでは壊れるため、部門の `README.md` に
  「`install.sh --only=hq-agents` を再実行して復元する」手順を必ず書くこと。
- キュー運用スクリプト（`scripts/queue.py` / `queue.sh`）は現状 `--only=hq-agents` の配布対象外である。
  部門側では `.claude/_queue.json` を直接編集する運用になる（配布方式の統一は本社側の課題）。

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
4. 部門固有のスキルを `.claude/skills/` に追加する。
5. `.claude/_queue.json` にスプリントタスクを追記していく。

## 注意

- 本社機能ファイル（symlink 側）は部門リポジトリ側で直接編集しないこと。
  編集は必ず `agent-crew`（本リポジトリ）側で行う。
- symlink は絶対パスで作成されるため、`agent-crew` を規約上のパス
  （`$HOME/Workspace/agent-crew` または `$HOME/workspace/agent-crew`）に
  clone しておくこと（ADR-014 トレードオフ参照）。
- `pm-protocol.md` / `pm-estimation.md` は ADR-014 の注記により過渡期は
  コピーモデルを継続するため、このテンプレートには含めていない
  （部門固有エージェント作成時に別途コピーする）。

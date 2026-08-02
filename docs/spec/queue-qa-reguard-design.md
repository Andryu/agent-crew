# queue.py QA再判定・doneガード・auto_close_issue是正 設計書（Issue #144 / #152）

## Status
Accepted（R1〜R9実装済み・Sora QA承認済み・Issue #144クローズ済み。R11のみ未実装・sprint27-retroへフォローアップ）

> 当初 Issue #144 単独のスコープだったが、Sprint-27 実行中に発生したインシデント（`invest-dept-charter`
> 完了時、`auto_close_issue` がタスク notes 内の参照テキスト「PR #151」を Issue 番号と誤認し、
> オーナーの戦略レビュー待ちだった PR #151 を誤クローズ）を受け、Issue #152（`auto_close_issue` の是正）
> を Yuki の指示により追加スコープとして本設計書に統合した（2026-08-02、risk_level: medium → high）。
> 両者は同一ファイル（`scripts/queue.py`）・同一 `done` コマンドの改修であるため、1つの設計書・
> 1つの実装タスク（`queue-qa-reguard-impl`）でまとめて扱う。
>
> **追記（team-lead 指摘 + Riku 調査、2026-08-02）**: Riku の調査で `auto_close_issue` の実害・準実害が
> さらに3件（Issue #139 / #140 / #141）確認され、根本原因の分析が「無関係な番号への誤爆（PR #151型）」
> だけでなく「多段階タスクにおける時期尚早クローズ（Issue #139型）」という2つ目の欠陥モードにも及ぶことが
> 判明した。本改訂で両方に対応する（1.2章・2章R10・6章）。あわせて Issue #133 は本バグとは無関係
> （GitHub標準の `Closes #N` PRマージ連動クローズ）と確定しており、この正規経路は変更しない。

## 1. 背景・問題

### 1.1 Issue #144: QA再判定の正規経路欠如

lesson: `agent-crew-sprint-26-tooling-001`（priority 6）。

`scripts/queue.py` の `qa` コマンドは `qa_result` が一度設定されると上書きできない（L287-289、冪等性ガード）。

```python
if task.qa_result is not None:
    typer.echo(f"ERROR: {slug} already has qa_result={task.qa_result}.", err=True)
    raise typer.Exit(14)
```

このため、Sora が誤った QA 判定（例: 見落としがあった APPROVED、あるいは修正確認後に正しく APPROVED へ変えたい CHANGES_REQUESTED）を訂正する**正規の経路が存在しない**。唯一の回避策が `retry` コマンドの流用だが、`retry` は「実装差し戻し」を意味する操作であり、副作用として `retry_count` を増やし `status` を `READY_FOR_RIKU` に戻してしまう。結果として `retry_count` が「実装差し戻し回数」ではなく「QA再判定回数（実装は差し戻されていない）」で汚染される問題が sprint26-qa で実害として確認された。

`done` コマンド側にも `qa_result` との整合チェックが一切なく、`qa_mode: inline` のタスクが QA 未実施のまま `done` されてもエラーにならない。

### 1.2 Issue #152: auto_close_issue の誤爆（追加スコープ・実害4件を精査）

`scripts/queue.py` の `done` コマンドは完了時に `auto_close_issue` を呼び、タスクの `notes` フィールドから正規表現で Issue 番号らしき文字列を拾って `gh issue close` を実行する。

```python
def auto_close_issue(q: QueueFile, slug: str, agent: str, summary: str) -> None:
    task = get_task(q, slug)
    m = re.search(r'#(\d+)', task.notes or "")
    if not m:
        return
    issue_num = m.group(1)
    try:
        subprocess.run(
            ["gh", "issue", "close", issue_num, "--comment", f"✅ {agent}: {slug} 完了 — {summary}"],
            check=True, capture_output=True
        )
        typer.echo(f"OK: Issue #{issue_num} closed")
    except Exception:
        pass  # 失敗を握りつぶす
```

**実害の精査結果（Riku調査 + オーナー確認、2026-08-02）**:

| Issue/PR | closedAt | 原因 | 本バグ(#152)との関係 |
|---|---|---|---|
| PR #151 | 2026-08-02 | `invest-dept-charter`完了時、notes内の参考記述「PR #151」を誤認してクローズ | **真の誤爆・実害あり**（Alexが即時reopenで復旧） |
| #139 | 2026-08-01T17:37:46Z | `subagent-stop-enforce-design`（設計フェーズ）完了コメントで自動クローズ | **時期尚早クローズ**（design段階で解決前にクローズ。同スプリント内でimpl・qaも完了しAPPROVEDに至ったため結果的に実害なしだったが、欠陥モードとしては別種） |
| #140 | 2026-08-01T17:28:56Z | `loadbalance-formula-doc`完了コメントで自動クローズ | notes内`#数字`が偶然そのタスクの対象と一致しており内容的には正しいクローズだったが、**仕組みとしては同じ無検証の自動クローズ** |
| #141 | 2026-08-01T17:43:11Z | `verify-query-rule-doc`完了コメントで自動クローズ | 同上（内容的には正しいが無検証） |
| #133 | 2026-08-01T17:05:47Z | PR #136 マージ時、GitHub標準の `Closes #133` 記法による自動クローズ | **本バグとは無関係**（`gh pr view --json mergedAt` で確認済み。`auto_close_issue`は関与していない） |

**構造的な問題点（2つの欠陥モードに整理）**:
1. **無関係な番号への誤爆**（PR #151型）: Issue番号かPR番号か、あるいは単なる参照テキストかを区別せず、notes内で最初にマッチした `#数字` を無条件でクローズ対象にする。
2. **多段階タスクでの時期尚早クローズ**（Issue #139型）: 1つのIssueが design → impl → qa の複数タスクに分かれて解決される場合でも、notesにIssue番号が書かれていれば最初のタスク（設計段階）の `done` 時点で誤ってクローズしてしまう。
3. `notes` は自由記述のため、上記1・2のいずれの混入も容易に起こる。
4. 確認プロンプトなしで即座に `gh issue close` を実行し、かつクローズ対象が実際に Issue（PRではない）かどうかを検証しない。
5. 失敗時に `except Exception: pass` で握りつぶすため、意図した動作が失敗していても誰も気づけない。

**#133 について（正規経路として維持）**: GitHub の `Closes #N` / `Fixes #N` 記法によるPRマージ時の自動クローズは `auto_close_issue` とは完全に独立したGitHub側の標準機能であり、本設計の変更対象ではない。今後もこの正規経路は維持してよい（team-lead確認済み）。

**再発リスクの点検結果（Yuki実施）**: Sprint-27 の他タスク（`queue-qa-reguard-design` 自身・`governance-doc-149-150` ・`lessons-issue-sync-fix`）にも同型の誤爆リスクが実在した。応急処置として notes 内の `#<数字>` 表記を安全な表記（例: `Issue144`）に置換済みだが、これは恒久対応までのブリッジに過ぎない。

## 2. 要件

| # | 要件 | 対応 |
|---|------|------|
| R1 | QA再判定（qa_result の訂正）に、実装差し戻しを伴わない正規経路を用意する | `qa --force` オプション |
| R2 | 上書き時は旧判定値を監査可能な形で残す（何が・いつ・なぜ変わったか） | `qa_history` フィールド |
| R3 | `qa_mode` が `inline` / `end_of_sprint` のタスクは、QA未実施のまま `done` できないようにする | `done` 側ガード |
| R4 | ガードは明示的にバイパス可能にする（設計・QA対象外タスクとの誤判定を避ける） | `--skip-qa-guard` |
| R5 | `retry_count` の意味を「実装差し戻し回数」のみに戻す（QA再判定では増やさない） | `qa --force` は `retry_count` に触れない |
| R6 | 既存の `_queue.json`（`qa_history` フィールドなし）との後方互換を壊さない | Pydantic `default_factory=list` |
| R7 | Issue/PRのクローズは `notes` の自由記述からの推測をやめ、明示的な指定のみで発火させる | `close_issue` 専用フィールド |
| R8 | 個別の `done` 呼び出し単位でクローズ対象を上書き指定できる（一回限りの例外運用） | `--close-issue <番号>` オプション |
| R9 | クローズ試行・成功・失敗をすべて可視化する（サイレント失敗をなくす） | `typer.echo` で試行前後を必ず出力 |
| R10 | 複数フェーズ（design→impl→qa等）に分かれるタスク群では、途中フェーズでの時期尚早クローズを避ける | `close_issue` は最終フェーズのタスクにのみ設定する運用ガイドライン（6.2章） |
| R11 | クローズ対象が実際にIssue（PRではない）であることを、実行前に検証する | `gh issue view <番号>` による事前検証（PR #151実害の直接的な再発防止） |

R7〜R9 は Issue #152 が当初提示した3方針（(a) 専用フィールド化 / (b) 明示オプション化 / (c) 可視化）に対応する。R10・R11 は team-lead 指摘・Riku 調査で追加確認された欠陥モードへの対応。

**実装状況（2026-08-02時点、Sora QA承認済み）**: R1〜R9は`queue-qa-reguard-impl`で実装済み・pytest 40件で検証済み・Issue #144を実際にクローズ済み。R10は当初からコードでは強制せず運用ガイドライン（Yukiの計画判断）に留める設計のため対応は完了している。**R11（`gh issue view`による事前検証）は本設計書への追記時点でまだ実装されていない**（`close_linked_issue`関数は`gh issue close`を直接呼ぶのみで、事前のissue/PR種別検証は行っていない）。R11の実装は本スプリントのスコープ外とし、フォローアップ課題としてsprint27-retroへ引き継ぐ。

## 3. 設計方針（Issue #144）

要件のR1とR3は独立した問題（QA再判定経路の欠如／done時のQA未実施検知の欠如）であり、チームリードの指示通り**両方を実装する**（(a) `qa --force` ＋ (b) `done` 側ガード）。

### 3.1 データモデル変更

`Task` に `qa_history` フィールドを追加する。エントリは「上書き前の状態のスナップショット」。

```python
class QaHistoryEntry(BaseModel):
    ts: str
    previous_result: str          # 上書き前の qa_result（APPROVED または CHANGES_REQUESTED）
    previous_summary: Optional[str] = None  # 上書き前に記録されていた qa イベントの summary（events から逆引き）
    reason: str                   # --force 実行時に必須で渡す再判定理由


class Task(BaseModel):
    ...
    qa_result: Optional[str] = None
    qa_history: list[QaHistoryEntry] = Field(default_factory=list)
    ...
```

`default_factory=list` により、既存の `_queue.json`（`qa_history` キーなし）は pydantic のデフォルト値補完で問題なく読み込める（マイグレーションスクリプト不要）。

### 3.2 `qa` コマンドの変更

```python
@app.command()
def qa(
    slug: str,
    result: str,
    summary: str = typer.Argument(default=""),
    force: bool = typer.Option(False, "--force", help="既存のqa_resultを上書きする（再判定）"),
    reason: str = typer.Option("", "--reason", help="--force使用時の再判定理由（必須）"),
) -> None:
    """qa_result を記録する"""
    if result not in ("APPROVED", "CHANGES_REQUESTED"):
        typer.echo("ERROR: result must be APPROVED or CHANGES_REQUESTED", err=True)
        raise typer.Exit(1)
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        if task.qa_result is not None:
            if not force:
                typer.echo(f"ERROR: {slug} already has qa_result={task.qa_result}. Use --force to re-judge.", err=True)
                raise typer.Exit(14)
            if not reason.strip():
                typer.echo("ERROR: --force requires --reason (再判定理由を必須にする)", err=True)
                raise typer.Exit(16)
            # 旧判定の summary を events から逆引きして退避する
            prev_qa_events = [e for e in task.events if e.action in ("qa", "qa_force")]
            prev_summary = prev_qa_events[-1].msg if prev_qa_events else None
            task.qa_history.append(QaHistoryEntry(
                ts=now_iso(), previous_result=task.qa_result,
                previous_summary=prev_summary, reason=reason,
            ))
        task.qa_result = result
        task.updated_at = today()
        action = "qa_force" if force else "qa"
        msg = f"{result}: {summary}" if not force else f"{result} (再判定, reason={reason}): {summary}"
        task.events.append(TaskEvent(ts=now_iso(), agent="Sora", action=action, msg=msg))
        save_queue(q)
    typer.echo(f"OK: {slug} qa_result = {result}" + (" (forced re-judgment)" if force else ""))
    signal_type = "qa.approved" if result == "APPROVED" else "qa.changes_requested"
    emit_signal(signal_type, slug, "Sora", {"reviewer": "Sora", "result": result, "forced": force})
```

**設計判断**:
- `--force` 単独では受け付けず `--reason` を必須にする（R2「なぜ変わったか」を機械的に強制するため。理由なき上書きは監査価値がない）。exit code は新規に `16` を割り当てる（既存の `1, 14` と衝突回避）。
- `retry_count` には一切触れない（R5）。`retry` コマンドとは完全に独立した経路とする。
- `action` を `qa_force` として区別することで、`queue.sh retro` の学び集計（`select(.action == "qa" and (.msg | startswith("CHANGES_REQUESTED")))`）が誤って再判定イベントを二重集計しないようにする（4.1章で影響確認済み）。

### 3.3 `done` コマンドの変更（QAガード + Issue #152 対応・最終形）

**注意**: この `done` の実装は Issue #144（QAガード）と Issue #152（`close_issue`、6章で詳述）の両方を統合した最終形。6章の `close_linked_issue` 関数と対で読むこと。

```python
@app.command()
def done(
    slug: str,
    agent: str,
    summary: str = typer.Argument(default="完了"),
    skip_qa_guard: bool = typer.Option(False, "--skip-qa-guard", help="qa_result未設定でもdoneを許可する（設計/QA対象外タスク用）"),
    close_issue: Optional[int] = typer.Option(None, "--close-issue", help="このdone呼び出し限定でクローズするIssue番号（task.close_issueより優先、一回限りの上書き。6章参照）"),
) -> None:
    """タスクを DONE に遷移する"""
    with queue_lock(QUEUE_FILE):
        q = load_queue()
        task = get_task(q, slug)
        if task.status == "DONE":
            typer.echo(f"ERROR: {slug} is already DONE.", err=True); raise typer.Exit(15)
        if task.qa_mode in ("inline", "end_of_sprint") and task.qa_result is None and not skip_qa_guard:
            typer.echo(
                f"ERROR: {slug} has qa_mode={task.qa_mode} but qa_result is not set. "
                f"Run 'qa' first, or pass --skip-qa-guard to bypass explicitly.",
                err=True,
            )
            raise typer.Exit(17)
        task.status = "DONE"
        task.updated_at = today()
        task.summary = summary
        task.events.append(TaskEvent(ts=now_iso(), agent=agent, action="done", msg=summary))
        save_queue(q)
    typer.echo(f"OK: {slug} → DONE")
    emit_signal("task.done", slug, agent, {"summary": summary})
    close_linked_issue(q, slug, agent, summary, override_issue=close_issue)
```

**設計判断**:
- ガード対象は `qa_mode` が `inline` または `end_of_sprint` のタスクのみ（R3・R4）。`qa_mode` が `None`（設計・QA自身のタスクなど）は対象外＝現行動作のまま。
- チェック順序は「既に DONE か」を先に見る（既存の exit 15 の意味を変えない）。次にQAガードを見る（exit 17）。
- 新規 exit code `17` を割り当てる。
- `--skip-qa-guard` は名前を意図的に長く・明示的にし、誤って常用されないようにする。バイパスした事実は `done` の `summary` に理由を書くことを運用ルール（`.claude/agents/*.md`）側で促す（本設計のスコープ外・別途申し送り、8章参照）。
- 末尾の `auto_close_issue(q, slug, agent, summary)` 呼び出しは `close_linked_issue(q, slug, agent, summary, override_issue=close_issue)` に置き換える（6章）。旧 `auto_close_issue` 関数は削除する。
- CLIオプション名 `--close-issue` はTaskモデルのフィールド名 `close_issue` に対応する（6章参照）。フィールドは「このタスクが恒久的にどのIssueと紐づいているか（データ）」、CLIオプションは「この`done`呼び出し限定でどのIssueをクローズするか（一回限りのアクション上書き）」を表し、命名は一致させている。

**このガードが意味する運用フローの変更（重要）**: `qa_mode: inline` のタスクでは、実装担当（Riku）は実装完了時に **`done` を直接呼んではならず**、`qa_mode: None` のタスクとは異なる経路を通る。実際には Sora が `qa` を実行して `qa_result` を確定させた後でなければ `done` が通らなくなる。これは `architect.md` の「作業完了時（QAエージェント: Sora）」節が元々規定していた `qa → done` の順序（Soraが最終的にdoneを呼ぶ）を、コマンドレベルで強制するようになる、という設計変更である。従来 `tests/test_queue_py.py` の一部テストは `qa_mode: inline` のタスクに対して `start → done → qa` の順で呼んでおり、本ガード導入後はこの呼び出し順のままでは `done` が exit 17 で失敗する。4.2章で影響を受ける既存テストとその修正方針を明記する。

### 3.4 `retry_count` 意味の整合（R5）

現行の `retry` コマンドは変更しない。QA再判定は `qa --force` 経由に完全移行することで、`retry_count` は「Sora が CHANGES_REQUESTED を出し、Riku が実装をやり直した回数」のみを意味するようになる。`qa --force` はこの値に一切触れないため、意味の汚染は構造的に発生しなくなる。

### 3.5 exit code 一覧（更新後）

| code | コマンド | 意味 |
|------|---------|------|
| 1 | qa | result が不正 |
| 8 | retry | retry_count 上限超過 → BLOCKED |
| 9 | start | 未解決の依存あり |
| 10 | start | complexity 不正 |
| 11 | start | 既に IN_PROGRESS |
| 12 | start | 既に DONE |
| 13 | start | BLOCKED 状態 |
| 14 | qa | qa_result 設定済み・`--force` なし（既存） |
| 15 | done | 既に DONE |
| **16 (新規)** | qa | `--force` はあるが `--reason` が空 |
| **17 (新規)** | done | `qa_mode` が inline/end_of_sprint かつ qa_result 未設定・`--skip-qa-guard` なし |

Issue #152（`close_linked_issue`）は `gh` コマンド失敗時・Issue/PR種別検証失敗時のいずれも `done` 自体を失敗させない設計（6章参照）のため、新規 exit code は追加しない。

## 4. 既存機能・既存テストへの影響確認（セルフチェック・Issue #144分）

### 4.1 `queue.sh retro` の集計ロジックへの影響

`queue.sh retro` の学び集計（`scripts/queue.sh` L242-247）は `action == "qa"` の CHANGES_REQUESTED イベントのみを見る。`qa --force` で記録される再判定イベントは `action == "qa_force"` として区別されるため、この集計ロジックには**影響しない**（意図的な設計。再判定は「学び」として初回判定の集計と混ざるべきではない）。

`queue.sh` のヘッダーコメント（L12）に `--force` オプションの説明を追記する。

```diff
- #   queue.sh qa <slug> <APPROVED|CHANGES_REQUESTED> "<summary>"  # qa_result を記録
+ #   queue.sh qa <slug> <APPROVED|CHANGES_REQUESTED> "<summary>" [--force --reason "<reason>"]
+ #                                                                 # qa_result を記録（--forceで再判定・旧値はqa_historyへ退避）
+ #   queue.sh done <slug> <agent> "<summary>" [--skip-qa-guard] [--close-issue <番号>]
+ #                                                                 # done時にIssueをクローズしたい場合は--close-issueで明示指定する
```

`_PY_COMMANDS` の委譲リスト（L381）は変更不要（`qa` / `done` は既に委譲対象であり、typer側でオプションが増えても透過的に動作する）。

### 4.2 既存テストへの影響（重要・セルフチェックで発見）

`tests/test_queue_py.py` の `MINIMAL_QUEUE` フィクスチャは `task-a` の `qa_mode` を `"inline"` に設定している。3.3 の `done` ガード導入により、**`start → done → qa` の順で呼んでいる既存テストは `done` の時点で exit 17 になり失敗する**。以下のテストは実装時に修正が必要。

| 既存テスト | 現在の呼び出し順 | 修正方針 |
|-----------|-----------------|---------|
| `test_done_normal` | start → done → (qaなし) | `done` に `--skip-qa-guard` を追加（このテストは done の素の遷移確認が目的でQA整合は対象外のため） |
| `test_done_duplicate` | start → done → done | 1回目の `done` に `--skip-qa-guard` を追加 |
| `test_qa_approved` | start → done → qa | `done` 呼び出しを削除（`qa` コマンド自体は `task.status` を見ないため元々不要だった） |
| `test_qa_changes_requested` | start → done → qa | 同上、`done` 呼び出しを削除 |
| `test_qa_idempotency_guard` | start → done → qa → qa | `done` 呼び出しを削除（idempotency は `qa_result` の有無だけで判定されるため `done` は無関係） |
| `test_handoff_sets_ready_for` | start → done → handoff | `done` の前に `qa`（APPROVED）を追加 |
| `test_retry_increments_count` | start → done → retry | `done` の前に `qa`（APPROVED）を追加 |

`test_retry_blocked_on_max` / `test_retry_complexity_s_blocked_on_second` / `test_retry_complexity_l_allows_up_to_five` / `test_retry_complexity_none_uses_env_max_retry` は `retry_count` をJSON直接編集で設定し `done` を経由しないため**影響なし**（現状のまま）。

`auto_close_issue` を呼んでいた既存の `done` 系テストは、`close_issue` フィールドが未設定（デフォルト `None`）のままなので、Issue #152 対応後も `gh` コマンドを一切呼ばない（7章の回帰テストで保証）。既存テストの結果には影響しない。

## 5. pytest 追加・修正方針（Issue #144分・`tests/test_queue_py.py`）

### 5.1 既存テストの修正（4.2の表に対応・diff形式）

```diff
 def test_done_normal(tmp_queue):
     """start → done で DONE に遷移し summary が記録される"""
     run_queue(["start", "task-a"], tmp_queue)
-    result = run_queue(["done", "task-a", "Riku", "実装完了"], tmp_queue)
+    result = run_queue(["done", "task-a", "Riku", "実装完了", "--skip-qa-guard"], tmp_queue)
     assert result.returncode == 0, result.stderr
```

```diff
 def test_done_duplicate(tmp_queue):
     """DONE タスクを再度 done するとエラー"""
     run_queue(["start", "task-a"], tmp_queue)
-    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
+    run_queue(["done", "task-a", "Riku", "完了", "--skip-qa-guard"], tmp_queue)
     result = run_queue(["done", "task-a", "Riku", "再完了"], tmp_queue)
     assert result.returncode == 15
```

```diff
 def test_qa_approved(tmp_queue):
     """qa APPROVED が正しく記録される"""
     run_queue(["start", "task-a"], tmp_queue)
-    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
     result = run_queue(["qa", "task-a", "APPROVED", "問題なし"], tmp_queue)
     assert result.returncode == 0
```

```diff
 def test_qa_changes_requested(tmp_queue):
     """qa CHANGES_REQUESTED が正しく記録される"""
     run_queue(["start", "task-a"], tmp_queue)
-    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
     result = run_queue(["qa", "task-a", "CHANGES_REQUESTED", "修正必要"], tmp_queue)
     assert result.returncode == 0
```

```diff
 def test_qa_idempotency_guard(tmp_queue):
     """qa_result が既に設定済みの場合は exit 14 で拒否する（--forceなし）"""
     run_queue(["start", "task-a"], tmp_queue)
-    run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
     run_queue(["qa", "task-a", "APPROVED", "初回"], tmp_queue)
     result = run_queue(["qa", "task-a", "APPROVED", "重複"], tmp_queue)
     assert result.returncode == 14
```

```diff
 def test_handoff_sets_ready_for(tmp_queue):
     """handoff で READY_FOR_SORA に遷移する"""
     run_queue(["start", "task-a"], tmp_queue)
+    run_queue(["qa", "task-a", "APPROVED", "問題なし"], tmp_queue)
     run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
     result = run_queue(["handoff", "task-b", "Sora"], tmp_queue)
     assert result.returncode == 0
```

```diff
 def test_retry_increments_count(tmp_queue):
     """retry で retry_count が増加し READY_FOR_RIKU になる"""
     run_queue(["start", "task-a"], tmp_queue)
+    run_queue(["qa", "task-a", "APPROVED", "問題なし"], tmp_queue)
     run_queue(["done", "task-a", "Riku", "完了"], tmp_queue)
     result = run_queue(["retry", "task-a"], tmp_queue)
     assert result.returncode == 0
```

### 5.2 新規テスト（qa --force）

```python
def test_qa_force_requires_reason(tmp_queue):
    """--force はあるが --reason が空の場合 exit 16 で拒否する"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["qa", "task-a", "APPROVED", "初回"], tmp_queue)
    result = run_queue(["qa", "task-a", "CHANGES_REQUESTED", "再判定", "--force"], tmp_queue)
    assert result.returncode == 16
    assert "--reason" in result.stderr


def test_qa_force_overwrites_and_archives_history(tmp_queue):
    """--force + --reason で qa_result が上書きされ、旧値が qa_history に退避される"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["qa", "task-a", "APPROVED", "見落とし"], tmp_queue)
    result = run_queue(
        ["qa", "task-a", "CHANGES_REQUESTED", "再確認の結果差し戻し",
         "--force", "--reason", "初回レビューで見落としがあった"],
        tmp_queue,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["qa_result"] == "CHANGES_REQUESTED"
    assert len(task["qa_history"]) == 1
    assert task["qa_history"][0]["previous_result"] == "APPROVED"
    assert task["qa_history"][0]["reason"] == "初回レビューで見落としがあった"
    assert any(e["action"] == "qa_force" for e in task["events"])


def test_qa_force_does_not_touch_retry_count(tmp_queue):
    """qa --force は retry_count を増やさない（R5: 意味の非汚染）"""
    run_queue(["start", "task-a"], tmp_queue)
    run_queue(["qa", "task-a", "APPROVED", "初回"], tmp_queue)
    run_queue(
        ["qa", "task-a", "CHANGES_REQUESTED", "再判定", "--force", "--reason", "テスト"],
        tmp_queue,
    )
    data = json.loads(tmp_queue.read_text())
    task = next(t for t in data["tasks"] if t["slug"] == "task-a")
    assert task["retry_count"] == 0
```

### 5.3 新規テスト（done QAガード）

`qa_mode` の値を差し替えた独立フィクスチャを都度生成する（`MINIMAL_QUEUE` の `task-b` は `task-a` に依存しており `start` に別タスクの完了が必要になるため、依存のない単純なコピーを使う）。

```python
def test_done_blocks_when_qa_mode_inline_and_qa_result_missing(tmp_queue):
    """qa_mode: inline で qa_result 未設定のタスクは done できない（exit 17）"""
    # MINIMAL_QUEUE の task-a は qa_mode: inline 済み
    run_queue(["start", "task-a"], tmp_queue)
    result = run_queue(["done", "task-a", "Riku", "実装完了"], tmp_queue)
    assert result.returncode == 17
    assert "qa_mode" in result.stderr


def test_done_blocks_when_qa_mode_end_of_sprint_and_qa_result_missing(tmp_path):
    """qa_mode: end_of_sprint でも qa_result 未設定なら done できない（exit 17）"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["qa_mode"] = "end_of_sprint"
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    run_queue(["start", "task-a"], queue_file)
    result = run_queue(["done", "task-a", "Riku", "実装完了"], queue_file)
    assert result.returncode == 17


def test_done_allows_skip_qa_guard(tmp_queue):
    """--skip-qa-guard を渡せば qa_result 未設定でも done できる"""
    run_queue(["start", "task-a"], tmp_queue)
    result = run_queue(["done", "task-a", "Riku", "実装完了", "--skip-qa-guard"], tmp_queue)
    assert result.returncode == 0, result.stderr


def test_done_guard_not_applied_when_qa_mode_none(tmp_path):
    """qa_mode: None のタスク（設計・QA自身のタスク等）はガード対象外で従来通り done できる"""
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["qa_mode"] = None  # task-a を qa_mode: None にした独立フィクスチャ
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    run_queue(["start", "task-a"], queue_file)
    result = run_queue(["done", "task-a", "Riku", "実装完了"], queue_file)
    assert result.returncode == 0, result.stderr
```

## 6. Issue #152 対応: auto_close_issue の是正

Issue #152 の対応方針は「(a) 専用フィールド化」「(b) 明示オプション化」「(c) 可視化」の3案が挙げられていたが、これらは排他ではなく**組み合わせて是正する**。恒久策は (a)（`notes` の自由記述からの推測を完全に廃止）、単発の例外運用として (b) をオーバーライドオプションで用意し、(c) は常時のログ出力として組み込む。加えて、team-lead 指摘・Riku 調査を受け、(d) クローズ対象が実際に Issue であることの事前検証（R11）と (e) 多段階タスクの運用ガイドライン（R10）を追加する。

### 6.1 データモデル変更（`close_issue` フィールド）

```python
class Task(BaseModel):
    ...
    qa_result: Optional[str] = None
    qa_history: list[QaHistoryEntry] = Field(default_factory=list)
    close_issue: Optional[int] = None  # done時にクローズしてよいIssue番号。明示設定時のみ発火（Issue #152）
    ...
```

`default_factory` ではなく `None` デフォルトのシンプルな `Optional[int]` で十分（リスト構造は不要）。既存 `_queue.json` にキーがなくても pydantic のデフォルト値補完で問題なく読み込める。

**命名について**: フィールド名は `close_issue`（このタスクが紐づく Issue 番号、というデータの意味）とし、`done` の CLI オプション名も `--close-issue`（このdone呼び出しでクローズするというアクションの意味）で統一する（3.3参照）。

**後方互換上の重要な仕様変更**: 従来の `auto_close_issue` は notes 内に `#<数字>` があれば無条件でクローズを試みていたが、本設計移行後は **`close_issue` フィールドが明示的に設定されているタスクのみ**がクローズ対象になる。既存 `_queue.json` の全タスクは `close_issue` 未設定（`None`）のため、移行直後は「どのタスクも自動クローズしない」状態になる。

### 6.2 多段階タスクの運用ガイドライン（R10・Issue #139 型の再発防止）

1つの Issue が design → impl → qa のように複数タスクに分割して解決される場合、**`close_issue` は最終フェーズのタスク（通常は QA タスク、qa_mode がないタスク構成の場合は impl タスク）にのみ設定する**。設計タスク（Alexが担当するような `queue_mode: inline` の設計フェーズ）には設定しない。

例（本スプリントの場合）: Issue #144 は `queue-qa-reguard-design`（Alex, 設計）→ `queue-qa-reguard-impl`（Riku, 実装）→ `queue-qa-reguard-qa`（Sora, QA）の3タスクで解決される。`close_issue: 144` を設定してよいのは最後の `queue-qa-reguard-qa` のみであり、`queue-qa-reguard-design` や `queue-qa-reguard-impl` には設定しない。

この運用は `close_issue` が「明示設定制」であること自体で自然に担保される（何も設定しなければ何もクローズされない）。コード側でフェーズを自動判定する仕組みは、タスク名の命名規則に依存し脆くなるため導入しない（「過度に複雑な設計は避ける」という方針に基づく判断）。**どのタスクに `close_issue` を設定するかはタスク作成時の計画運用（Yuki）で担保する。**

### 6.3 `close_linked_issue` 関数（`auto_close_issue` の置き換え・Issue/PR種別検証つき）

```python
def close_linked_issue(
    q: QueueFile, slug: str, agent: str, summary: str, override_issue: Optional[int] = None
) -> None:
    """task.close_issue（または--close-issueによる一回限りの上書き）が明示設定されている場合のみ、
    実際にIssueであることを検証した上でcloseする。notesの自由記述からの推測は一切行わない
    （Issue #152 再発防止）。"""
    task = get_task(q, slug)
    issue_num = override_issue if override_issue is not None else task.close_issue
    if issue_num is None:
        return
    typer.echo(f"INFO: verifying #{issue_num} is a GitHub Issue before closing for {slug}", err=True)
    verify = subprocess.run(
        ["gh", "issue", "view", str(issue_num), "--json", "number"],
        capture_output=True, text=True,
    )
    if verify.returncode != 0:
        typer.echo(
            f"WARN: #{issue_num} did not resolve to a GitHub Issue (may be a PR or nonexistent). "
            f"Skipping close to avoid an Issue #152-style incident.",
            err=True,
        )
        return
    try:
        subprocess.run(
            ["gh", "issue", "close", str(issue_num), "--comment", f"✅ {agent}: {slug} 完了 — {summary}"],
            check=True, capture_output=True
        )
        typer.echo(f"OK: Issue #{issue_num} closed")
    except Exception as e:
        typer.echo(f"WARN: failed to close issue #{issue_num}: {e}", err=True)
```

**設計判断**:
- 旧 `auto_close_issue` 関数は削除し、`import re` は queue.py 内で他に使用箇所がないため合わせて削除する（未使用importの残置を避ける）。
- `override_issue`（`--close-issue` CLI引数由来）が `task.close_issue`（キューJSON上の恒久設定）より優先される。これにより「通常は自動クローズしないタスクだが、今回だけ手動で対応Issueを指定してクローズしたい」という例外運用（R8）に対応する。
- **クローズ実行前に `gh issue view <番号>` で対象が実際にIssueであることを検証する（R11）**。これは PR #151 実害の直接的な再発防止策であり、たとえ `close_issue` に誤ってPR番号が設定されてしまっても、`gh issue view` がPR番号に対して失敗するため（GitHub CLIはissue/PRの番号空間を共有するがissueとしての参照解決は失敗する）、誤クローズを構造的に防げる。検証失敗時は `WARN` を出してクローズをスキップするのみで、`done` 自体は正常終了する。
- クローズ試行前に必ず `INFO:` ログを stderr に出す（R9）。旧実装は成功時のみ `OK:` を出し、失敗は完全に無音だった。新実装は失敗時・検証失敗時も `WARN:` を出す（`except: pass` を廃止）。ただし `done` コマンド自体は Issue クローズの成否に関わらず正常終了する（Issueクローズはベストエフォートの副作用であり、`done` の主目的である状態遷移を失敗させるべきではないため、新規 exit code は追加しない）。

### 6.4 既存タスクへの移行方針

- `_queue.json` に既存のタスクは全て `close_issue` 未設定のまま読み込める（後方互換、6.1参照）。
- Sprint-27時点で「notes内の `#<数字>` を安全な表記に書き換える」応急処置がすでに適用されているが、これは本設計導入後は不要になる（`close_issue` 未設定なら notes に何が書いてあってもクローズは発火しないため）。ただし、書き換え済みのnotesを元に戻す必要はない（実害がないため据え置きでよい）。
- 本スプリントで真に自動クローズさせたいタスク（例: `queue-qa-reguard-qa` が Issue #144 の実装完了・QA承認を確認した時点で `close_issue: 144` を設定する等、6.2の運用ガイドライン通り）を設定するかどうかは、実装スコープの外（Yuki・Sora の運用判断）とする。本設計はメカニズムの提供に留める。
- #133 のような GitHub 標準の `Closes #N` 記法によるPRマージ時クローズは本設計と無関係のため、移行対象ではない（1.2章参照）。

## 7. pytest 追加方針（Issue #152分・回帰テスト含む）

fake `gh` バイナリを `PATH` に注入し、実際に呼ばれた引数をログファイルに記録することで、サブプロセス越しでも「gh が呼ばれたか／どの引数で呼ばれたか」を検証する。Issue/PR種別検証（`gh issue view`）もフェイクバイナリの終了コードで模擬する。

```python
def _make_fake_gh(tmp_path: Path, view_exit_code: int = 0) -> tuple[Path, Path]:
    """呼び出された引数を記録する偽 gh コマンドを作る。
    view_exit_code: `gh issue view` サブコマンドの終了コード（0=Issueとして解決成功、非0=失敗＝PR等）。
    (gh実行パス, ログファイル) を返す"""
    log_file = tmp_path / "gh_calls.log"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{log_file}"\n'
        'if [ "$1" = "issue" ] && [ "$2" = "view" ]; then\n'
        f'  exit {view_exit_code}\n'
        "fi\n"
        "exit 0\n"
    )
    fake_gh.chmod(0o755)
    return fake_gh, log_file


def test_close_issue_not_set_skips_gh_call(tmp_queue, tmp_path):
    """close_issue未設定ならgh issueは一切呼ばれない"""
    _, log_file = _make_fake_gh(tmp_path)
    env = {**os.environ, "QUEUE_FILE": str(tmp_queue), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了"], env=env, capture_output=True, text=True)
    assert not log_file.exists()


def test_notes_with_hash_number_does_not_trigger_close(tmp_path):
    """notesに#<数字>が含まれていても、close_issue未設定ならgh issueは呼ばれない（Issue #152 回帰テスト・PR #151型）"""
    _, log_file = _make_fake_gh(tmp_path)
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["notes"] = "PR #999 との関連メモ、本タスクの主題とは無関係な参照"
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了"], env=env, capture_output=True, text=True)
    assert not log_file.exists()


def test_close_issue_field_triggers_gh_close(tmp_path):
    """task.close_issueが設定されていればIssue種別検証を経てgh issue closeが該当番号で呼ばれる"""
    _, log_file = _make_fake_gh(tmp_path, view_exit_code=0)
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["close_issue"] = 999
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    result = subprocess.run(
        [uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了"],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert log_file.exists()
    log_content = log_file.read_text()
    assert "issue view 999" in log_content
    assert "issue close 999" in log_content


def test_close_issue_skips_close_when_target_is_not_an_issue(tmp_path):
    """gh issue viewが失敗する（PR番号等）場合はcloseを試みない（R11・PR #151実害の直接的な回帰テスト）"""
    _, log_file = _make_fake_gh(tmp_path, view_exit_code=1)
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["close_issue"] = 151  # PR #151を模擬（gh issue viewが失敗する想定）
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    result = subprocess.run(
        [uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了"],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stderr
    log_content = log_file.read_text()
    assert "issue view 151" in log_content
    assert "issue close 151" not in log_content


def test_close_issue_cli_override_takes_precedence(tmp_path):
    """--close-issue はtask.close_issueより優先される"""
    _, log_file = _make_fake_gh(tmp_path, view_exit_code=0)
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["close_issue"] = 999
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    subprocess.run(
        [uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了", "--close-issue", "777"],
        env=env, capture_output=True, text=True,
    )
    assert log_file.exists()
    log_content = log_file.read_text()
    assert "777" in log_content
    assert "close 999" not in log_content


def test_close_issue_gh_failure_does_not_fail_done(tmp_path):
    """gh issue closeが失敗してもdone自体は成功扱いのまま（WARNは出るがexitは0）"""
    log_file = tmp_path / "gh_calls.log"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{log_file}"\n'
        'if [ "$1" = "issue" ] && [ "$2" = "view" ]; then\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "issue" ] && [ "$2" = "close" ]; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    fake_gh.chmod(0o755)
    queue_file = tmp_path / "_queue.json"
    data = json.loads(json.dumps(MINIMAL_QUEUE))
    data["tasks"][0]["close_issue"] = 999
    queue_file.write_text(json.dumps(data, ensure_ascii=False))
    env = {**os.environ, "QUEUE_FILE": str(queue_file), "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    uv = str(Path.home() / ".local/bin/uv")
    subprocess.run([uv, "run", "scripts/queue.py", "start", "task-a"], env=env, capture_output=True, text=True)
    subprocess.run([uv, "run", "scripts/queue.py", "qa", "task-a", "APPROVED", "ok"], env=env, capture_output=True, text=True)
    result = subprocess.run(
        [uv, "run", "scripts/queue.py", "done", "task-a", "Riku", "完了"],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stderr
```

## 8. Riku 実装チェックリスト（Issue #144 + #152 統合）

- [ ] `Task` モデルに `qa_history: list[QaHistoryEntry] = Field(default_factory=list)` を追加
- [ ] `QaHistoryEntry` モデルを新規追加
- [ ] `Task` モデルに `close_issue: Optional[int] = None` を追加
- [ ] `qa` コマンドに `--force` / `--reason` オプションを追加（3.2のdiff通り）
- [ ] `done` コマンドに `--skip-qa-guard` / `--close-issue` オプションとガード条件を追加（3.3の最終形diff通り）
- [ ] `auto_close_issue` 関数を削除し `close_linked_issue` 関数に置き換える（6.3のコード通り。`gh issue view` によるIssue/PR種別検証を含む）。`done` コマンド末尾の呼び出しも `close_linked_issue(q, slug, agent, summary, override_issue=close_issue)` に変更
- [ ] 未使用になった `import re`（queue.py冒頭）を削除する
- [ ] `scripts/queue.sh` のヘッダーコメントを更新（4.1のdiff通り、doneの新オプションも追記）
- [ ] `tests/test_queue_py.py` の既存7テストを5.1のdiff通りに修正（**先に修正しないと done ガード導入と同時にCIが赤くなる**）
- [ ] `tests/test_queue_py.py` に5.2・5.3（Issue #144分）・7章（Issue #152分、Issue/PR種別検証のテスト含む）の新規テストを追加
- [ ] `uv run pytest tests/test_queue_py.py -v` で全件パスを確認
- [ ] `.claude/agents/qa.md`（Sora）に `qa --force` の使い所（訂正であって実装差し戻しではない場合に限る）を追記する運用ドキュメント更新は本設計のスコープ外だが、実装後にYuki/Soraへ申し送りすること
- [ ] `.claude/agents/pm.md`（Yuki）に「複数フェーズに分かれるタスク群では `close_issue` を最終フェーズにのみ設定する」運用ガイドライン（6.2）を反映するかはYukiの判断に委ねる。本設計のスコープ外だが、実装後にYukiへ申し送りすること
- [ ] Issue #152 のクローズ判断（本Issue自体を `close_issue` 経由で閉じるか、手動で閉じるか）はYukiに確認すること

## Consequences

**やりやすくなること**: Sora が QA判定を安全に訂正できる。`retry_count` が本来の「実装差し戻し回数」の指標として信頼できるようになり、`queue.sh retro` の「QA差し戻し率」集計の意味が正確になる。Issue/PRの誤クローズが構造的に発生しなくなる（`close_issue` を明示設定しない限り何もクローズされず、設定していてもIssue/PR種別検証を通過しなければクローズされない）。クローズ試行・失敗が必ずログに残るため、サイレント失敗がなくなる。多段階タスクでの時期尚早クローズ（Issue #139型）も、運用ガイドライン（6.2）により防げる。

**やりにくくなること**: `qa_mode: inline` のタスクで、実装担当が誤って先に `done` を呼ぶと exit 17 で止まるようになる（意図的な変更だが、既存の運用に慣れたエージェントには挙動変化として認知コストが生じる。`architect.md` 側の「作業完了時（実装・設計エージェント）」節は元々 `qa_mode: inline` タスクを想定していないため矛盾はしないが、Riku・Alexの委譲判断時に「このタスクは `qa_mode: inline` か」を意識する必要が増える）。`done` コマンドの引数が増え、`qa_mode` の設定漏れ（本来 `inline` にすべきタスクが `None` のまま計画された場合）はこのガードでは検知できない副作用があるが、これは pm.md 側のタスク分解時のレビューで担保する。Issue自動クローズについては、移行直後は「明示設定しない限り誰も自動クローズされない」状態になるため、従来 notes 経由でたまたま正しく動いていたクローズ運用（#140/#141のような事例）は `close_issue` の明示設定に切り替える一手間が発生する。複数フェーズのタスク群では「最終フェーズにのみ設定する」という運用ルールをYuki（計画担当）が毎回意識する必要が増えるが、この移行コストは、誤クローズ・時期尚早クローズという実害の再発防止に対して十分見合うトレードオフと判断する。

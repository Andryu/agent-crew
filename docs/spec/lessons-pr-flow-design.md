# lessons → agent .md 自動 PR 提案フロー — 設計書

**Issue**: #59
**設計者**: Alex（architect）/ Sprint-15

---

## 1. 概要

`~/.claude/_lessons.json` に蓄積された高優先度 lesson を、対象エージェントの `.md` ファイルへの差分として提案し、Draft PR を自動作成するフロー。

オーナーが PR をレビュー・マージすることでエージェント定義に学びが反映される（安全版：自動マージしない）。

---

## 2. スクリプト仕様

### ファイル: `scripts/propose-lesson-rules.sh`

**言語**: Bash（lessons.sh / queue.sh と統一）

### 実行フロー

```
1. ~/.claude/_lessons.json を読み込み
2. priority_score >= 4 かつ status が open/proposed/issue_created の lesson を抽出
3. 各 lesson の category から対象エージェントを決定（マッピングテーブル参照）
4. 対象エージェント .md の末尾「禁止パターン」セクションへの追記差分を生成
5. git diff で差分があれば Draft PR を作成
6. 差分がなければ "No new lessons to propose" で終了
```

### category → エージェントマッピング

| category | 対象エージェント .md |
|----------|---------------------|
| `process` | `pm.md` |
| `planning` | `pm.md` |
| `reliability` | `engineer-go.md` |
| `implementation` | `engineer-go.md` |
| `qa` | `qa.md` |
| `tooling` | `engineer-go.md` |
| `architecture` | `architect.md` |
| `communication` | `pm.md` |

### 引数

```bash
scripts/propose-lesson-rules.sh [--dry-run] [--min-priority <N>]
```

- `--dry-run`: PR 作成せず差分のみ表示
- `--min-priority`: フィルタ閾値（デフォルト: 4）

### 出力ブランチ名

```
fix/lesson-rules-YYYYMMDD
```

（既存ブランチが存在する場合は上書きせず終了し警告を出す）

### 追記フォーマット

各エージェント .md の末尾に以下を追加する（セクション未存在なら新規作成）:

```markdown
## 禁止パターン（lessons より自動提案）

> このセクションは `scripts/propose-lesson-rules.sh` によって生成されました。
> オーナーのレビュー後にマージしてください。
> 最終更新: YYYY-MM-DD

### [lesson_id]
- **lesson**: [description の先頭100文字]
- **禁止行動**: [action から「〜してはいけない」を抽出、または action をそのまま記載]
- **priority**: [priority_score] / sprint: [sprint]
```

---

## 3. hook 設定仕様

### トリガー条件

`Stop` hook（Claude セッション終了時）を使用し、全タスク DONE かつ全 QA APPROVED の場合のみスクリプトを実行する。

### `.claude/settings.json` への追記

既存の `Stop` hooks エントリに `propose-lesson-rules.sh` の呼び出しを追加する。

**現在の設定（抜粋）**:
```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": ".claude/hooks/subagent_stop.sh"
      }
    ]
  }
]
```

**変更後**:
```json
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": ".claude/hooks/subagent_stop.sh"
      }
    ]
  },
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "bash -c 'scripts/propose-lesson-rules.sh --dry-run 2>/dev/null || true'"
      }
    ]
  }
]
```

**注意**: Stop hook での PR 自動作成はリスクが高い（意図しないブランチ作成）ため、hook では `--dry-run` のみ実行し、差分レポートを STDOUT に出力するに留める。実際の PR 作成はスプリント完了フロー（Yuki の自動フロー ステップ3の後）で Yuki が明示的に `scripts/propose-lesson-rules.sh` を呼ぶ形とする。

---

## 4. スプリント完了フローへの組み込み

pm.md の「スプリント完了後の自動フロー」に以下のステップを追加する（ステップ3.5として）:

```
3.5. lessons PR 提案フローを実行
     scripts/propose-lesson-rules.sh
     差分があれば Draft PR URL をオーナーへ報告
```

---

## 5. 実装上の注意

- `jq` は `.claude/settings.json` の permissions で許可済み。lesson フィルタリングに使う。
- スクリプトは `set -euo pipefail` で書く。
- PR 作成に `gh pr create --draft` を使う（permissions で許可済み）。
- ブランチは `git checkout -b fix/lesson-rules-$(date +%Y%m%d)` で作成。
- 差分がない場合（全 lesson 反映済み）は正常終了（exit 0）でメッセージのみ出力。
- `--dry-run` フラグ時は git checkout / commit / push / gh pr create を一切実行しない。

---

## 6. 完了基準（Riku 向け）

- [ ] `scripts/propose-lesson-rules.sh --dry-run` が実行でき、差分を STDOUT に出力する
- [ ] `scripts/propose-lesson-rules.sh` が Draft PR を作成し URL を出力する
- [ ] `.claude/settings.json` の `Stop` hook に `--dry-run` 実行エントリが追加されている
- [ ] `pm.md` のスプリント完了フローにステップ 3.5 が追記されている
- [ ] Issue #59 がクローズされている

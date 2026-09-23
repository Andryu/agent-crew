# P5 v2 benchmark

P5はChromeやmacOSアプリのUI自動操作を使わず、Codex CLI、固定fixture、OS sandboxで実行する。`batch.py`は正式run前に`sandbox_preflight.py`を必須実行し、失敗時はモデルを呼ばない。

## 実行順序

1. 通常shellで`python3.12 -B sandbox_preflight.py`を実行し、`passed: true`を確認する。
2. `python3.12 -B selftest.py`と`python3.12 -B analysis_selftest.py`を実行する。
3. `python3.12 -B batch.py`で24runを実行する。private artifactは`/private/tmp/agent-crew-p5-benchmark/formal/<campaign>`だけに保存する。
4. runごとに、実装と別の新規contextで回答・変更・検証証跡を確認し、次のJSONを作る。
5. `python3.12 -B analyze.py --campaign-dir <campaign-dir> --reviews <review.json> --public-output <report.md>`で集計する。

## 独立review JSON

```json
{
  "schema": 1,
  "campaign": "p5-<fingerprint-prefix>",
  "fingerprint": "<full fingerprint>",
  "reviews": [
    {
      "task_id": "C1",
      "condition": "A",
      "repeat": 1,
      "acceptance_pass": true,
      "handoff_pass": true,
      "scope_pass": true,
      "review_findings": [],
      "reviewed_by": "<independent context identifier>",
      "reviewed_at": "<RFC 3339>"
    }
  ]
}
```

24件すべてに上記fieldが必要。`unknown`、欠損、重複、fingerprint不一致は合格にしない。自動keyword判定は`handoff_pass`の代用にならない。

## 保存境界

prompt、answer、event要約、validator結果、preflight、summary、独立review、private aggregateは公開repoへcommitしない。campaign directoryは0700、fileは0600、保持は14日。公開aggregateを作成してレビューが完了した後に削除する。期限までに未完なら期限前に保持延長を明示記録する。公開Markdown候補には生command、回答本文、reviewerの記述、private pathを含めない。

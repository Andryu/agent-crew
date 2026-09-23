# P5 v2 benchmark

P5はChromeやmacOSアプリのUI自動操作を使わず、Codex CLI、固定fixture、OS sandboxで実行する。`batch.py`は正式run前に`sandbox_preflight.py`を必須実行し、失敗時はモデルを呼ばない。

## 固定する比較条件

P0の`migration-baseline/snapshot-index.json`とSHA-256が一致する非機密ファイルだけを、`/private/tmp/agent-crew-p5-benchmark/formal/p5-<fingerprint>/`以下の独立runへ復元する。各fixtureは架空のローカルGit identityでcommitし、元repo、global設定、認証、実資産本文、会話ログをコピーしない。

順序は課題ごとに`ABBA`と`BAAB`を交互に使う。A/Bとも`gpt-6-astra`、reasoning `medium`、OpenAI provider、`codex-cli 0.155.1`を明示し、hook・user config・rulesを無効にする。これは隔離比較の条件であり、実運用hookのE2Eとは別に検証する。model/providerのサーバ側実効値を観測できなければ`unknown`とする。

Bは`b-contract/{agent_crew,wealth_advisor}/`と`b-contract-index.json`、Aのwealth skillは`a-contract/`と`a-contract-index.json`でpath/hashを固定する。wealthのA入力はP0 manifest記載HEADのGit blobから取得した非機密skillで、元P0 manifestとsnapshotを変更しない。A/Bのwealth開始script/testは同じbytesとし、契約とskillだけを条件差にする。

旧campaign `p5-cd6cbf5b9eec05c0`、旧C1 smoke、2026-09-21のpreflightは歴史的証跡として保持し、新campaignへ合算しない。旧campaignの安全判定unknownとC5/C6利用上限失敗は[formal-report](formal-report.md)、旧ハーネスの当時説明は[README v1](README-v1-2026-09-21.md)を参照する。

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

集計は、validator、課題受入、安全、handoffの4ゲートをrunごとに分ける。24件すべてが4ゲートに合格した場合だけ、各課題のA/B各2本の`wall_seconds`中央値と、6課題の`B/A`比の中央値を計算する。比率中央値が`0.80`以下なら限定20%短縮を達成とする。campaign完走、全run合格、速度目標達成は別fieldで記録する。

## 保存境界

prompt、answer、event要約、validator結果、preflight、summary、独立review、private aggregateは公開repoへcommitしない。campaign directoryは0700、fileは0600、保持は14日。公開aggregateを作成してレビューが完了した後に削除する。期限までに未完なら期限前に保持延長を明示記録する。公開Markdown候補には生command、回答本文、reviewerの記述、private pathを含めない。

`.benchmark-events.json`は生JSONLを保存せず、event/item種別、tool lifecycle、cwd、許可したcommand、exit code、出力hashだけを保存する。未知・伏字・必須情報欠落・失敗tool・未分類commandは安全合格にしない。単語によるhandoff予備判定は独立reviewの代用にしない。費用、承認待ち、LLM/tool時間を取得できなければ推測せず`unknown`とする。

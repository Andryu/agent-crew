# レトロスペクティブ — sprint-04

生成日: 2026-04-22
生成者: みゆきち（retro エージェント）

---

## スプリント概要

**スプリントゴール**: Sora の重複実行バグ修正（#38）と Riku self-review チェックリスト導入（#40）

**期間**: 2026-04-22
**結果**: 全 6 タスク DONE / QA APPROVED

---

## タスク完了サマリー

| タスク | 担当 | complexity | 実行時間 | retry_count | qa_result |
|--------|------|-----------|---------|-------------|-----------|
| fix-sora-dup-design | Alex | M | - | 0 | - |
| fix-sora-dup-impl | Riku | M | 1分 | 0 | - |
| fix-sora-dup-qa | Sora | M | 3分 | 0 | APPROVED |
| riku-self-review-design | Alex | M | 2分 | 0 | - |
| riku-self-review-impl | Riku | M | 0分 | 0 | - |
| riku-self-review-qa | Sora | S | 0分 | 0 | APPROVED |

> 実行時間は start → done イベント間の diff から算出。Alex は Bash ツールを持たないため start イベントを自己発行できず、一部 - 表示になっている。

---

## 集計

- 完了タスク数: 6 / 6（完了率 100%）
- ブロック発生: 0 件
- 総リトライ回数: 0
- QA 差し戻し率: 0%（CHANGES_REQUESTED 0 件 / QA タスク 2 件）
- CRITICAL/MAJOR/MINOR 指摘: 全タスク合計 0 件

---

## Complexity 精度評価

| complexity | タスク数 | 平均実行時間 |
|-----------|---------|------------|
| S | 1 | 0分 |
| M | 5 | 1分 |
| L | 0 | - |

> 実測値はいずれも短時間。fix-sora-dup-design は Alex の start イベントがないため計測不可。

---

## KPT — Keep / Problem / Try

### Keep（続けること）

**K-1: Design → Impl → QA の 3 段階フロー**
全 6 タスクがリトライなしで DONE になった。設計書が Riku への引き継ぎ情報として十分に機能し、実装のブレがなかった。sprint-02 から継続してきたこのフローの有効性が再確認された。

**K-2: queue.sh 重複防止ガードの TOCTOU 対応設計**
設計書（fix-sora-dup-design.md）で「ガードチェックは必ず acquire_lock の後で実行する」と明示され、実装でも忠実に守られた。Sora の QA でも「TOCTOU防止のためacquire_lock後にガード配置」が合格基準として確認された。

**K-3: self-review チェックリストの導入効果**
sprint-02 では QA フェーズで MAJOR 指摘が 2 件発生した。sprint-04 では self-review チェックリスト導入後の初スプリントで CRITICAL/MAJOR/MINOR ゼロを達成した。チェックリストが意図した効果を出している可能性がある（1 スプリントのみのため継続観察が必要）。

**K-4: 重複防止ガードの実戦的検証**
Riku の done 完了後に Yuki が誤って done を呼ぼうとした際、exit 15 で正しく弾かれた。実装したガードが想定外の呼び出し（Yuki の誤操作）に対しても機能することが本番で確認された。

---

### Problem（問題だったこと）

**P-1: Alex が Bash ツールを持たず、queue.sh 操作を Yuki が代行**
Alex（architect エージェント）は Bash ツールを持たないため、設計完了後に queue.sh done / handoff を自己実行できなかった。これはスプリント中 2 回（fix-sora-dup-design 完了時、riku-self-review-design 完了時）発生した。Yuki が代行したため作業は進んだが、Yuki の介入コストが発生し、スプリントの自律性が下がった。

**P-2: Alex タスクの実行時間が計測不能**
Alex が start イベントを自己発行できないため、fix-sora-dup-design の実行時間が「-」になった。retro の Complexity 精度評価に空白が生じる。また riku-self-review-design は start イベントが handoff 後に記録されているが、timing が実態と合っていない可能性がある。

**P-3: 並列グループがなく逐次実行になった**
fix-sora-dup-design と riku-self-review-design は独立したタスクであり、parallel_group による並列化が可能だった。しかし両タスクともに Alex が担当しており、実質的に逐次実行された。parallel-handoff を活用して並列展開する余地があった。

---

### Try（次に試すこと）

**T-1: Alex に Bash ツールを付与するか、代行プロセスを明文化する**
architect.md に「done / handoff は Yuki に依頼する」と明記し、誰が何をするかを明示化する。あるいは Alex のツールセットに Bash を追加して自律的に queue.sh を呼べるようにする。後者のほうが根本的な解決になる。

**T-2: Alex タスクに start イベントを記録する仕組みを整える**
Alex が start を自己発行できない現状では、Yuki が Alex の作業開始時に `queue.sh start <slug>` を代行するか、handoff コマンドで自動的に start 相当のイベントを記録する拡張を検討する。

**T-3: self-review チェックリストの効果を継続的に測定する**
sprint-04 は 1 スプリントのみのデータ。次スプリント以降も MAJOR 指摘数を記録し、導入前（sprint-02: MAJOR 2 件）との比較を 3 スプリント分継続して効果を定量化する。

**T-4: 独立タスクの並列化を計画時に明示する**
次スプリント計画時、depends_on がない複数タスクは parallel_group を付与して明示的に並列化する。担当エージェントが同一（Alex）でも、並列化の意図を queue に記録しておくことで計画の透明性が上がる。

---

## 特記事項

### 重複防止ガードの実証（sprint-04 ハイライト）

sprint-02 で発覚した Sora 重複実行バグ（#38）への対策として実装した重複防止ガードが、sprint-04 本番で予期しない形で検証された。

```
シナリオ:
1. Riku が fix-sora-dup-impl の done を実行 → DONE
2. Yuki が誤って同タスクに done を呼ぶ
3. exit 15 "already DONE" でガードが弾く → 重複イベント記録を防止
```

これは「ガードが必要になるのはエージェントの誤動作時」という前提を超えて、「人間オペレーター（Yuki）の誤操作」に対しても有効であることを示す。防御的設計の重要性を裏付ける実例として記録する。

---

## lessons.json への記録

以下の 3 件を `~/.claude/_lessons.json` に記録した。

| lesson ID | category | priority_score | type |
|-----------|----------|---------------|------|
| agent-crew-sprint-04-tooling-001 | tooling | 9 | success |
| agent-crew-sprint-04-process-001 | process | 4 | failure-pattern |
| agent-crew-sprint-04-qa-001 | qa-process | 3 | success |

---

## エビデンスゲート結果

ゲート通過条件（priority_score >= 4 かつ evidence >= 1 件 かつ issue_url == null）を満たした lesson:

| lesson ID | priority_score | 状態 | Issue URL |
|-----------|---------------|------|-----------|
| agent-crew-sprint-04-process-001 | 4 | Issue 化済み | https://github.com/Andryu/agent-crew/issues/43 |

Issue 化実施日: 2026-04-22
ラベル: `priority-medium`, `retro`, `lessons-learned`
Issue タイトル: `[lesson] Alex が Bash ツールを持たず queue.sh done/handoff を Yuki が代行`

---

## 次スプリントへの提言

1. **Alex の Bash ツール付与を最優先で検討する**
   スプリントの自律性を高めるうえで最も効果が高い。architect.md のツール定義を確認し、Bash を追加できるか Yuki に判断を求める。（Issue #43 参照）

2. **self-review チェックリストの効果測定を継続する**
   1 スプリントではデータ不足。sprint-05、06 でも MAJOR 指摘数を記録し、3 スプリント後に定量評価を行う。

3. **重複防止ガードのエラーログを retro 集計に含める**
   exit 11〜15 が発火した回数をスプリント集計に含めると、重複呼び出し頻度のモニタリングになる。queue.sh retro コマンドへの集計追加を検討する。

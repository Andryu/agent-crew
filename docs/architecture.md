# agent-crew アーキテクチャガイド

> バージョン: Sprint-22 時点 (2026-06-15)  
> 対象読者: このリポジトリを初めて読む開発者・agent-crew を別プロジェクトへ展開する人

---

## 目次

1. [概要](#1-概要)
2. [エージェント一覧と関係図](#2-エージェント一覧と関係図)
3. [スプリントライフサイクル](#3-スプリントライフサイクル)
4. [自律成長ループ（クロスリポジトリ）](#4-自律成長ループクロスリポジトリ)
5. [フック・イベント設計](#5-フックイベント設計)
6. [データフロー](#6-データフロー)
7. [スキル・プラグイン構成](#7-スキルプラグイン構成)
8. [ユースケース別使用例](#8-ユースケース別使用例)
9. [ファイル構成リファレンス](#9-ファイル構成リファレンス)

---

## 1. 概要

agent-crew は **個人開発者がひとりで複数のAIエージェントを動かしてソフトウェアを開発するための Claude Code プラグイン**です。

PM・設計・実装・QA・セキュリティ・DevOps・データ分析・ドキュメントレビューの各専門エージェントが、スクラムライクなスプリントサイクルで協調動作します。スプリント終了後は教訓を自動蓄積し、クロスリポジトリで知見を共有する「自律成長ループ」が動作します。

### 設計思想

| 原則 | 内容 |
|------|------|
| **介入最小化** | オーナーは「何を作るか」を伝えるだけ。手順・承認・コミットは自動 |
| **専門分化** | 各エージェントは1つの責務のみを持つ（PM は実装しない・Riku は設計しない） |
| **学習継続** | 失敗も成功も教訓として記録し、次のスプリントに自動反映 |
| **プラグイン配布** | `claude plugin install github:Andryu/agent-crew` で他プロジェクトへ即展開 |

---

## 2. エージェント一覧と関係図

### エージェント一覧

| ペルソナ | ファイル | 役割 | ツール権限 |
|---------|---------|------|-----------|
| **Yuki** (PM) | `pm.md` | 統括・タスク分解・委譲・Slack通知 | Read/Write/Bash/Glob/WebSearch |
| **Alex** (Architect) | `architect.md` | システム設計・ADR・DB設計 | Read/Write/Glob/Grep/Bash |
| **Mina** (UX) | `ux-designer.md` | UXフロー・ワイヤーフレーム・コンポーネント仕様 | Read/Write/Glob |
| **Riku** (Engineer) | `engineer-go.md` / `engineer-vue.md` / `engineer-next.md` | 実装・テスト | Read/Write/Edit/Bash/Glob/Grep |
| **Sora** (QA) | `qa.md` | コードレビュー・受け入れ基準チェック | Read/Grep/Glob/Bash（読み取り専用） |
| **Kai** (Security) | `security.md` | OWASP/脆弱性スキャン | Read/Grep/Glob/Bash（読み取り専用） |
| **Tomo** (DevOps) | `devops.md` | CI/CD・Docker・デプロイ | Read/Write/Edit/Bash/Glob/Grep |
| **Ren** (Data) | `data-analyst.md` | データパイプライン・SQL・ダッシュボード | Read/Write/Edit/Bash/Glob/Grep |
| **Hana** (DocReview) | `doc-reviewer.md` | PRD・仕様書・README レビュー | Read/Grep/Glob（読み取り専用） |
| **みゆきち** (Retro) | `retro.md` | 振り返り・教訓記録・Issue化 | Read/Write/Bash/Glob |

### エージェント関係図

```mermaid
graph TD
    Owner["👤 オーナー<br/>(ユーザー)"]
    Yuki["🗂️ Yuki<br/>PM / オーケストレーター"]
    Alex["🏗️ Alex<br/>Architect"]
    Mina["🎨 Mina<br/>UX Designer"]
    Riku["⚙️ Riku<br/>Engineer"]
    Sora["✅ Sora<br/>QA"]
    Kai["🔒 Kai<br/>Security"]
    Tomo["🚀 Tomo<br/>DevOps"]
    Ren["📊 Ren<br/>Data Analyst"]
    Hana["📝 Hana<br/>Doc Reviewer"]
    Retro["🔄 みゆきち<br/>Retro"]

    Owner -->|"要件・方針"| Yuki
    Yuki -->|"設計タスク"| Alex
    Yuki -->|"UX設計タスク"| Mina
    Yuki -->|"実装タスク"| Riku
    Yuki -->|"QA依頼"| Sora
    Yuki -->|"セキュリティ依頼"| Kai
    Yuki -->|"インフラ依頼"| Tomo
    Yuki -->|"データ設計依頼"| Ren
    Yuki -->|"ドキュメント依頼"| Hana
    Yuki -->|"スプリント完了後"| Retro
    Alex -->|"設計書"| Riku
    Mina -->|"コンポーネント仕様"| Riku
    Riku -->|"実装完了"| Sora
    Sora -->|"APPROVED / CHANGES_REQUESTED"| Yuki
    Kai -->|"脆弱性レポート"| Yuki
    Retro -->|"教訓 (_lessons.json)"| Yuki

    style Yuki fill:#f9f,stroke:#333
    style Owner fill:#bbf,stroke:#333
```

### 並列実行ルール

同一 `parallel_group` に属し、`depends_on` が全て DONE のタスクは並列委譲できます。

```mermaid
gantt
    title スプリント並列実行例
    dateFormat X
    axisFormat %s

    section Phase 1（並列）
    Alex: 設計        :a1, 0, 3
    Mina: UX設計      :a2, 0, 2

    section Phase 2（直列）
    Riku: 実装        :b1, after a1, 5

    section Phase 3（並列）
    Sora: QA          :c1, after b1, 2
    Kai:  セキュリティ :c2, after b1, 2
```

---

## 3. スプリントライフサイクル

### ステップ全体図

```mermaid
flowchart LR
    A["オーナーが要件を伝える"] --> B["Yuki: タスク分解<br/>_queue.json に登録"]
    B --> C["Phase 1<br/>並列実行"]
    C --> D["Phase 2<br/>実装"]
    D --> E["Phase 3<br/>QA / Security"]
    E --> F{全タスク DONE?}
    F -->|No| G["BLOCKED 解消<br/>リトライ"]
    G --> E
    F -->|Yes| H["Yuki: コミット・Draft PR"]
    H --> I["みゆきち: レトロスペクティブ"]
    I --> J["教訓 → _lessons.json"]
    J --> K["オーナーへ報告<br/>+ Slack通知"]
```

### タスクステータス遷移

```mermaid
stateDiagram-v2
    [*] --> TODO
    TODO --> IN_PROGRESS : エージェント着手
    IN_PROGRESS --> DONE : 完了
    IN_PROGRESS --> BLOCKED : ブロック発生
    BLOCKED --> TODO : ブロック解消
    DONE --> [*]

    TODO --> READY_FOR_ALEX : 設計待ち
    TODO --> READY_FOR_RIKU : 実装待ち
    TODO --> READY_FOR_SORA : QA待ち
    READY_FOR_ALEX --> IN_PROGRESS
    READY_FOR_RIKU --> IN_PROGRESS
    READY_FOR_SORA --> IN_PROGRESS
```

### `_queue.json` スキーマ（主要フィールド）

```json
{
  "sprint": "sprint-22",
  "tasks": [
    {
      "slug": "my-task",
      "title": "タスクタイトル",
      "status": "TODO",
      "assigned_to": "Riku",
      "complexity": "M",
      "risk_level": "medium",
      "parallel_group": "phase-1",
      "depends_on": ["another-task"],
      "qa_mode": "inline",
      "qa_result": null,
      "notes": "実装の詳細・前提条件"
    }
  ]
}
```

---

## 4. 自律成長ループ（クロスリポジトリ）

agent-crew の最も特徴的な仕組みです。どのリポジトリで作業しても教訓が蓄積され、agent-crew 自身の改善に使われます。

### 全体フロー

```mermaid
flowchart TD
    subgraph "任意のリポジトリ (例: alpha-predict-jp)"
        A1["Claude Code セッション"] -->|"SubagentStop"| B1
        B1["capture-learning.sh<br/>(グローバルフック)"] -->|"JSONL 追記"| C1["~/.claude/learning-logs.jsonl"]
        A1 -->|"エージェント完了後"| D1["教訓発生"]
        D1 -->|"scope=global<br/>priority>=6"| E1["Plugin Feedback<br/>(retro.md)"]
        E1 -->|"gh issue create"| F1["agent-crew Issue"]
    end

    subgraph "~/.claude/ (グローバル)"
        C1
        G1["~/.claude/_lessons.json<br/>(全PJ共通教訓DB)"]
    end

    subgraph "agent-crew"
        F1 -->|"次スプリント計画時"| H1["Yuki: 外部教訓の確認<br/>(pm.md Step 0.7)"]
        H1 -->|"取り込み"| I1["スプリント計画"]
        I1 -->|"実装・マージ"| J1["agent-crew 改善"]
        J1 -->|"git pull"| K1["~/.claude/hooks/*.sh<br/>自動更新（symlink）"]
    end

    C1 -->|"Stop フック"| L1["aggregate-learnings.sh<br/>当日の外部活動サマリー表示"]

    style C1 fill:#ffd,stroke:#999
    style G1 fill:#ffd,stroke:#999
```

### 教訓のスコープ分類

| scope | 対象 | 主な用途 |
|-------|------|---------|
| `project` | 特定リポジトリ専用 | そのリポジトリの次スプリントに反映 |
| `stack` | 同技術スタック共通 | Go / Vue / Next ごとの知見共有 |
| `global` | 全PJ共通 | agent-crew 本体への改善フィードバック |

### `_lessons.json` スキーマ

```json
{
  "lesson_id": "alpha-sprint-01-process-001",
  "title": "教訓タイトル",
  "scope": "global",
  "priority_score": 7,
  "source_repo": "git@github.com:Andryu/alpha-predict-jp.git",
  "issue_url": null,
  "tags": ["process", "hook"]
}
```

---

## 5. フック・イベント設計

### フック一覧

| イベント | スクリプト | 場所 | 役割 |
|---------|-----------|------|------|
| `SessionStart` | `session_start.sh` | `.claude/hooks/` | 未完了タスク・直近 lesson の表示 |
| `TaskCompleted` | `task_completed.sh` | `.claude/hooks/` | `_signals.jsonl` にシグナル emit |
| `SubagentStop` | `subagent_stop.sh` | `.claude/hooks/` | 次ステップ提示・スプリント完了宣言 |
| `SubagentStop` | `capture-learning.sh` | `~/.claude/hooks/` | 全PJ の活動を `learning-logs.jsonl` に記録 |
| `Stop` | `aggregate-learnings.sh` | `~/.claude/hooks/` | 当日の外部リポジトリ活動サマリーを出力 |
| `Stop` | `privacy-check.sh` | `scripts/` | 変更ファイルの個人情報パターンスキャン |

### フックのスコープ

```mermaid
graph LR
    subgraph "プロジェクトスコープ (.claude/hooks/)"
        H1["session_start.sh"]
        H2["task_completed.sh"]
        H3["subagent_stop.sh"]
    end

    subgraph "グローバルスコープ (~/.claude/hooks/)"
        H4["capture-learning.sh"]
        H5["aggregate-learnings.sh"]
    end

    H3 -->|"次ステップ判断"| Q["_queue.json"]
    H2 -->|"記録"| S["_signals.jsonl"]
    H4 -->|"追記"| L["learning-logs.jsonl"]
    H5 -->|"集計・表示"| STDOUT["stderr (サマリー)"]
```

### Stop フックでのプライバシーチェック（`.claude/settings.json`）

コミット前に自動で個人情報パターンを検出します。

```
検出パターン:
  - メールアドレス (@ を含む文字列)
  - 絶対パス (/Users/<name>/)
  - Slack Webhook URL
  - GitHub PAT (ghp_)
  - OpenAI / Anthropic API キー
  - 日本の電話番号
```

---

## 6. データフロー

### 主要ファイルとデータ流れ

```mermaid
flowchart TD
    subgraph "プロジェクトローカル"
        Q[".claude/_queue.json<br/>タスクキュー"]
        SIG[".claude/_signals.jsonl<br/>イベントログ"]
        SET[".claude/settings.json<br/>フック・権限設定"]
    end

    subgraph "グローバル (~/.claude/)"
        LES["_lessons.json<br/>教訓DB（全PJ共通）"]
        LOG["learning-logs.jsonl<br/>活動ログ（全PJ）"]
    end

    Yuki -->|"タスク登録"| Q
    Riku -->|"実装完了 → DONE"| Q
    Q -->|"SubagentStop 読み込み"| SSHook["subagent_stop.sh"]
    SSHook -->|"Slack 通知"| Slack
    Q -->|"TaskCompleted"| SIG
    Retro -->|"教訓書き込み"| LES
    Yuki -->|"外部教訓参照"| LES
    AllProjects["全リポジトリのセッション"] -->|"capture-learning.sh"| LOG
    LOG -->|"aggregate-learnings.sh"| Summary["当日サマリー (stderr)"]
```

---

## 7. スキル・プラグイン構成

### プラグイン構成

```
agent-crew/
├── .claude-plugin/
│   ├── plugin.json          ← プラグインマニフェスト
│   └── marketplace.json     ← マーケットプレイス登録情報
├── .claude/
│   ├── agents/              ← エージェント定義（pm.md, qa.md...）
│   ├── skills/              ← スキル定義
│   │   ├── life-planner/
│   │   ├── life-plan-review/
│   │   └── privacy-audit/
│   └── hooks/               ← プロジェクトスコープのフック
└── scripts/                 ← ユーティリティスクリプト
```

### スキル一覧

| スキル | 呼び出し | 用途 |
|--------|---------|------|
| `life-planner` | `/life-planner` | ライフプラン（資産・保険・老後）初回作成 |
| `life-plan-review` | `/life-plan-review` | ライフプラン定期見直し |
| `privacy-audit` | `/privacy-audit` | リポジトリ全体の個人情報・機密情報スキャン |

### インストール方法

```bash
# Claude Code プラグインとして（推奨）
claude plugin install github:Andryu/agent-crew

# 手動セットアップ（開発・カスタマイズ用）
git clone https://github.com/Andryu/agent-crew ~/Workspace/agent-crew
cd ~/Workspace/agent-crew
bash install.sh go /path/to/my-project   # go/vue/next を選択

# グローバルフック（クロスリポジトリ学習）の有効化
bash install.sh --only=global-hooks go .
```

### マルチスタック対応

```
go   → engineer-go.md を riku.md としてコピー
vue  → engineer-vue.md を riku.md としてコピー
next → engineer-next.md を riku.md としてコピー
```

---

## 8. ユースケース別使用例

### ユースケース A: 新機能を1スプリントで開発する

**トリガー**: 「Yukiに〇〇を実装する計画を立てて」

```mermaid
sequenceDiagram
    participant O as オーナー
    participant Y as Yuki (PM)
    participant A as Alex (Architect)
    participant R as Riku (Engineer)
    participant S as Sora (QA)

    O->>Y: 「ユーザー認証機能を追加したい」
    Y->>Y: タスク分解 → _queue.json 登録
    Y-->>O: スプリント計画を提示・承認確認
    O->>Y: 承認
    Y->>A: 設計タスク委譲
    A->>A: ADR + API設計書作成
    A-->>Y: 完了
    Y->>R: 実装タスク委譲
    R->>R: コード実装・テスト作成
    R-->>Y: 完了
    Y->>S: QAタスク委譲
    S->>S: コードレビュー・受け入れ基準チェック
    S-->>Y: APPROVED
    Y->>Y: コミット・Draft PR作成
    Y-->>O: PR URL + 完了報告
```

---

### ユースケース B: セキュリティレビューを実施する

**トリガー**: 「Kaiにセキュリティレビューしてもらって」

```mermaid
sequenceDiagram
    participant O as オーナー
    participant Y as Yuki (PM)
    participant K as Kai (Security)

    O->>Y: 「リリース前にセキュリティを確認したい」
    Y->>K: セキュリティレビュー委譲
    K->>K: OWASP Top 10 チェック
    K->>K: 依存関係脆弱性スキャン
    K->>K: 認証・認可フロー検証
    K-->>Y: 脆弱性レポート (🔴/🟡/🟢)
    Y-->>O: レポート + 修正優先度の提示
```

---

### ユースケース C: 別リポジトリに agent-crew を展開する

**例**: `alpha-predict-jp` に株式分析エージェントを追加する

```bash
# 1. セットアップ（agent-crew を使って対象PJに設定を流す）
bash ~/Workspace/agent-crew/scripts/setup-sprint.sh \
  ~/Workspace/alpha-predict-jp sprint-1

# 2. プロジェクト固有スキルを直接作成
mkdir -p ~/Workspace/alpha-predict-jp/.claude/skills/jp-stock-analyst
# SKILL.md を作成（claude /skill-creator で作成補助も可）

# 3. スプリント開始
# → session_start.sh が自動実行され未完了タスクを表示
# → agent-crew の全エージェント（Yuki/Alex/Riku/Sora...）が利用可能
```

---

### ユースケース D: 自動プライバシーチェック

**仕組み**: Stop フックで自動実行（手動実行も可）

```bash
# 手動実行
/privacy-audit

# または自動: セッション終了時に差分ファイルをスキャン
# 検出時のみ警告出力（終了コード 0 で続行）
```

---

### ユースケース E: クロスリポジトリ学習の確認

```bash
# 当日のクロスリポジトリ活動を確認
cat ~/.claude/learning-logs.jsonl | \
  jq -r 'select(.ts | startswith("2026-06-15")) | "\(.repo) [\(.agent_type)]"'

# agent-crew 以外の教訓を確認
jq '[.lessons[] | select(.source_repo != "agent-crew" and .scope == "global")]' \
  ~/.claude/_lessons.json
```

---

### ユースケース F: レトロスペクティブ（スプリント振り返り）

**トリガー**: 「みゆきちを呼んで」または Yuki がスプリント完了後に自動起動

```mermaid
sequenceDiagram
    participant Y as Yuki (PM)
    participant M as みゆきち (Retro)
    participant L as _lessons.json
    participant GH as GitHub Issues

    Y->>M: スプリント完了後に自動起動
    M->>M: _queue.json から失敗/成功パターン収集
    M->>M: 教訓を lesson_id 付きで生成
    M->>L: 新規 lesson を追記
    M->>M: priority_score >= 3 を pm-learned-rules.md に反映
    M->>GH: priority_score >= 5 の lesson を Issue 化
    M-->>Y: レトロサマリー
```

---

## 9. ファイル構成リファレンス

```
agent-crew/
│
├── .claude-plugin/
│   ├── plugin.json               プラグインマニフェスト
│   └── marketplace.json          マーケットプレイス登録情報
│
├── .claude/
│   ├── agents/
│   │   ├── pm.md                 Yuki — PM オーケストレーター
│   │   ├── pm-protocol.md        委譲ルール・QAモード補助定義
│   │   ├── pm-estimation.md      複雑度・見積もり補助定義
│   │   ├── pm-learned-rules.md   スプリントから蓄積した学習ルール
│   │   ├── architect.md          Alex — アーキテクト
│   │   ├── ux-designer.md        Mina — UX デザイナー
│   │   ├── engineer-go.md        Riku (Go スタック)
│   │   ├── engineer-vue.md       Riku (Vue3 スタック)
│   │   ├── engineer-next.md      Riku (Next.js スタック)
│   │   ├── qa.md                 Sora — QA・コードレビュー
│   │   ├── security.md           Kai — セキュリティレビュー
│   │   ├── devops.md             Tomo — DevOps・インフラ
│   │   ├── data-analyst.md       Ren — データ分析
│   │   ├── doc-reviewer.md       Hana — ドキュメントレビュー
│   │   └── retro.md              みゆきち — レトロスペクティブ
│   │
│   ├── skills/
│   │   ├── life-planner/         SKILL.md — ライフプラン初回作成
│   │   ├── life-plan-review/     SKILL.md — ライフプラン定期見直し
│   │   └── privacy-audit/        SKILL.md — 個人情報スキャン
│   │
│   ├── hooks/
│   │   ├── session_start.sh      SessionStart: 未完了タスク・lesson 表示
│   │   ├── task_completed.sh     TaskCompleted: _signals.jsonl emit
│   │   └── subagent_stop.sh      SubagentStop: 次ステップ提示・Slack通知
│   │
│   ├── _queue.json               現スプリントのタスクキュー
│   ├── _signals.jsonl            タスクイベントログ
│   └── settings.json             Claude Code 権限・フック設定
│
├── scripts/
│   ├── capture-learning.sh       グローバルSubagentStop: 活動ログ記録
│   ├── aggregate-learnings.sh    グローバルStop: 外部活動サマリー表示
│   ├── privacy-check.sh          個人情報パターンスキャン（Stop フック）
│   ├── setup-sprint.sh           別リポジトリへのスプリント機能展開
│   ├── propose-lesson-rules.sh   教訓 → pm-learned-rules.md 反映提案
│   ├── lessons.sh                _lessons.json 操作ユーティリティ
│   └── queue.sh / queue.py       _queue.json 操作ユーティリティ
│
├── docs/
│   ├── architecture.md           ← このファイル
│   ├── adr/                      アーキテクチャ決定記録 (ADR-001〜013)
│   ├── spec/                     設計仕様書
│   └── DECISIONS.md              スプリントごとの判断記録
│
├── templates/
│   ├── _queue.json               新規プロジェクト用キューテンプレート
│   └── settings.json             新規プロジェクト用設定テンプレート
│
└── install.sh                    セットアップスクリプト
```

### グローバルファイル（`~/.claude/`）

```
~/.claude/
├── agents/          グローバルエージェント（install.sh でコピー）
├── skills/          グローバルスキル（install.sh でシンボリックリンク）
├── hooks/
│   ├── capture-learning.sh   → agent-crew/scripts/capture-learning.sh
│   └── aggregate-learnings.sh → agent-crew/scripts/aggregate-learnings.sh
├── _lessons.json    全プロジェクト共通の教訓DB
├── learning-logs.jsonl  全プロジェクトの活動ログ
└── settings.json    グローバル設定（フック登録・権限）
```

---

*このドキュメントは agent-crew の主要コンポーネントが揃った Sprint-22 時点のスナップショットです。アーキテクチャの変更は `docs/adr/` に ADR として記録されます。*

# マルチスタック設計メモ — phase1-multistack-design

## 背景と目的

現在の `engineer-go.md`（Riku）はGoとVue3のフルスタックを一つのファイルで担う設計になっている。
Issue #10 では Vue3 専用プロジェクト・Next.js 専用プロジェクトへの対応が求められており、
スタックごとに専門化されたエージェント定義を分離することで以下を実現する：

- スタック固有の知識・規約をエージェントに正確に持たせる
- install.sh の `STACK` 引数（go / vue / next）と 1:1 で対応するファイルを配置する
- Yuki のスタック自動検出により、オーナーが STACK を手動指定しなくてもよい状態を目指す

---

## 設計方針

### ファイル命名

`install.sh` の既存フォールバックロジックに従い、以下の命名を採用する：

```
agents/engineer-vue.md   # vue スタック用 Riku
agents/engineer-next.md  # next スタック用 Riku
```

install.sh はすでに以下の順序でソースを探索している：

```
riku-<STACK>.md  →  engineer-<STACK>.md  →  engineer-go.md（フォールバック）
```

`engineer-vue.md` と `engineer-next.md` を追加するだけで既存のインストールフローと即座に統合される。
追加の install.sh 変更は不要。

### 共通構造

`engineer-go.md` の章構成をテンプレートとして維持し、スタック固有の内容のみ差し替える。

| 章 | engineer-go.md | engineer-vue.md | engineer-next.md |
|---|---|---|---|
| ペルソナ | Go/Vue3フルスタック | Vue3フロントエンド専門 | Next.js フロントエンド専門 |
| コーディング規約 | Go + Vue3 | Vue3（詳細化） | Next.js（App Router中心） |
| テスト | go test + vitest | vitest + Vue Testing Library | Jest + React Testing Library |
| DoD | go test/build + npm | npm run test/build | npm run test/build |
| 環境チェック | go, git | node, git | node, git |
| タスクキュープロトコル | 共通（そのままコピー） | 共通（そのままコピー） | 共通（そのままコピー） |

---

## engineer-vue.md 概要仕様

### ペルソナ

Riku の Vue3 専門版。バックエンドAPIは既存のものとして、フロントエンド実装に特化する。
Composition API・Pinia・Vue Router に精通しており、コンポーネント設計と状態管理が得意。

### コーディング規約

`engineer-go.md` の「フロントエンド（Vue3）」節を拡充・独立させる形とする。

- `<script setup>` + TypeScript を標準とし、Options API は書かない
- `defineProps` / `defineEmits` には型を常に明示
- コンポーネントは 100 行を超えたら分割、1 コンポーネント = 1 責任
- グローバル状態は Pinia（stores/ ディレクトリ）、ローカル状態は `ref` / `reactive`
- CSS は `<style scoped>`、デザイントークンは CSS 変数
- `any` 禁止、`unknown` + 型ガード、zod でAPIレスポンスをバリデーション

**ツール・ライブラリ知識**

| カテゴリ | ライブラリ |
|---|---|
| フレームワーク | Vue 3.x（Composition API） |
| 状態管理 | Pinia |
| ルーティング | Vue Router 4.x |
| HTTP | axios または fetch（プロジェクトに従う） |
| バリデーション | zod |
| スタイル | CSS Modules / scoped styles |
| ビルド | Vite |

**テスト戦略**

- ユニット: `vitest` + `@vue/test-utils`
- コンポーネントテスト: Vue Testing Library（`@testing-library/vue`）
- E2E: Playwright（任意）
- テーブルドリブン形式は vitest の `test.each` で再現
- 外部API呼び出しは `vi.mock` でモック化

**環境チェック（preflight）**

```bash
command -v node >/dev/null 2>&1 || { echo "BLOCKED: missing tool: node"; exit 1; }
command -v git  >/dev/null 2>&1 || { echo "BLOCKED: missing tool: git";  exit 1; }
```

**DoD（実装完了の定義）**

- `npm run test` がパスする
- `npm run build` が成功する
- 新規コンポーネントに JSDoc / インラインコメントがある
- Props / Emits の型定義が明示されている
- TODO/FIXME があればコメントに理由を書く

---

## engineer-next.md 概要仕様

### ペルソナ

Riku の Next.js 専門版。App Router（Next.js 13+）を前提とし、
Server Components / Client Components の境界設計とデータフェッチパターンに精通している。

### コーディング規約

- App Router 基準（`app/` ディレクトリ）、Pages Router には対応しない
- Server Components をデフォルトとし、インタラクティビティが必要な箇所のみ `'use client'` を付与
- データフェッチは `fetch()` with キャッシュ制御（`cache: 'force-cache'` / `revalidate`）
- Route Handler（`app/api/`）でAPIエンドポイントを実装
- 状態管理: グローバルは Zustand、フォームは React Hook Form、サーバー状態は SWR または TanStack Query
- TypeScript strict モード必須、`any` 禁止
- zod でAPIレスポンス・フォーム入力をバリデーション

**ツール・ライブラリ知識**

| カテゴリ | ライブラリ |
|---|---|
| フレームワーク | Next.js 14.x（App Router） |
| 状態管理 | Zustand |
| フォーム | React Hook Form + zod |
| サーバー状態 | SWR または TanStack Query |
| スタイル | Tailwind CSS または CSS Modules |
| バリデーション | zod |
| ビルド | Turbopack（開発）/ Next.js build（本番） |

**テスト戦略**

- ユニット: Jest + React Testing Library
- Server Components のテスト: `jest` + `@testing-library/react`（async render）
- API Route Handler のテスト: `jest` でリクエスト/レスポンスをモック
- E2E: Playwright（任意）
- `'use client'` / Server Component の境界をテストで意識的に分離

**環境チェック（preflight）**

```bash
command -v node >/dev/null 2>&1 || { echo "BLOCKED: missing tool: node"; exit 1; }
command -v git  >/dev/null 2>&1 || { echo "BLOCKED: missing tool: git";  exit 1; }
```

**DoD（実装完了の定義）**

- `npm run test` がパスする
- `npm run build` が成功する（型エラー0件）
- Server / Client Component の境界が意図通りである
- 新規コンポーネント・Route Handler にコメントがある
- TODO/FIXME があればコメントに理由を書く

---

## Yuki のスタック自動検出ロジック

### 設計方針

Yuki（pm.md）のタスク分解フローの冒頭に「スタック検出ステップ」を追加する。
オーナーから STACK 指定がない場合、プロジェクトルートのファイルを見て自動判定する。

### 検出アルゴリズム（優先順位順）

```
1. go.mod が存在する
   → STACK=go

2. next.config.js / next.config.mjs / next.config.ts のいずれかが存在する
   → STACK=next
   （package.json より先にチェックすることで next を vue より高優先度にする）

3. package.json が存在し、dependencies または devDependencies に "vue" を含む
   → STACK=vue

4. package.json のみ存在する（vue を含まない）
   → STACK=next（Node.jsプロジェクトのデフォルト）
   ※ 判断が確定できない場合はオーナーへ確認を求める

5. 上記いずれも存在しない
   → STACK 不明。オーナーへ「スタックを教えてください（go / vue / next）」と問い合わせ
```

### 実装イメージ（pm.md への追記）

スタック分解前に以下のシェルロジックを Bash ツールで実行する想定：

```bash
detect_stack() {
  local dir="${1:-.}"

  if [ -f "$dir/go.mod" ]; then
    echo "go"
    return
  fi

  if ls "$dir"/next.config.* 2>/dev/null | grep -q .; then
    echo "next"
    return
  fi

  if [ -f "$dir/package.json" ]; then
    if grep -q '"vue"' "$dir/package.json"; then
      echo "vue"
    else
      # next.config が無くても package.json だけあれば next をデフォルトとする
      # ただし確信が持てないため警告を出す
      echo "next"
      echo "WARNING: next.config が見つかりません。next と仮定しますが、確認してください。" >&2
    fi
    return
  fi

  echo "unknown"
}
```

Yuki はこの結果を受けて `install.sh` の STACK 引数とキューの `notes` フィールドに記録する。

### pm.md への追記場所

「スプリント計画フォーマット」の前に「スタック検出」節として追記する。
以下の形式でオーナーに提示する：

```
## スタック検出結果
検出ファイル: go.mod / next.config.js / package.json（vue含む） など
判定スタック: go / vue / next / unknown

スタックが正しくない場合は訂正してください。
Go → `scripts/queue.sh` では STACK=go
Vue → STACK=vue
Next.js → STACK=next
```

---

## 依存関係と実装順序

```
phase1-multistack-design（このタスク、Alex）
  ↓
engineer-vue.md の実装（Riku）
engineer-next.md の実装（Riku）
pm.md へのスタック検出ロジック追記（Riku）
  ↓
Sora によるレビュー（qa_mode: inline）
```

engineer-vue.md と engineer-next.md は並列実装可能（互いに依存しない）。
ただし pm.md 追記は両ファイルの内容確認後が望ましい。

---

## トレードオフ記録

### Go専用Riku との統合 vs 分離

**分離を選んだ理由：**
- Go バックエンドと Vue/Next フロントエンドでは使用コマンド・テストフレームワーク・ DoD が異なる
- 一つのファイルに詰め込むと「このプロジェクトのスタックには関係ない節」が増えてノイズになる
- install.sh が既にスタック別ファイル選択をサポートしており、分離コストが低い

**失うもの：**
- Go + Vue3 フルスタックプロジェクト（現行の engineer-go.md のユースケース）は engineer-go.md で引き続き対応
- 3ファイルへの重複（タスクキュープロトコル節など）が生まれる → 許容範囲とみなす

### スタック自動検出の精度

`package.json` + vue/next の判定は依存関係の書き方によっては誤検知する。
（例: Next.js プロジェクトで vue ライブラリを補助的に使っている場合）

この場合はオーナーへ確認を求めるフォールバックで対応する。
検出ロジックを過度に精緻化するより「不明なら聞く」を優先する（シンプルさを取る）。

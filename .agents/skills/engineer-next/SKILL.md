---
name: engineer-next
description: Next.js App RouterとReact・TypeScriptの機能実装、バグ修正、テスト作成や手順相談に使う。Server/Client Componentの境界とデータ取得を扱う。Pages Router、Vue、Next.jsを使わないReact実装には使わない。
---

# Next.js App Router実装

## 着手

手順への質問だけなら説明し、実装やファイル作成を開始しない。実作業では関連コード・テスト・設計書・ADR、使用バージョンと依存構成、受入条件を確認し、方針を1〜3行で示す。既存のPages Routerを本スキルの適用のために移行しない。

実装前に `command -v node` と `command -v git`、プロジェクトのパッケージ管理・検証コマンドの利用可否を確認する。必要ツールが欠けていれば実装を止め、不足ツール、実施不能な作業、解決候補を報告する。検証の省略や静的確認への切替を隠して完了扱いしない。

## 実装の判断

- Server Componentを基本とし、操作・ブラウザ機能が必要な最小範囲に `'use client'` を置く。データ取得はサーバー側を基本とし、Client Componentへ必要なデータをpropsで渡す。
- データの鮮度と共有範囲に合わせ、使用バージョンでの `fetch` のキャッシュ・再検証の挙動を確認して明示する。すべてのデータに同じキャッシュ設定を適用しない。
- APIが必要な場合は既存設計に沿って `app/api/` のRoute Handlerへ配置する。新規APIの追加を依頼から推測しない。
- TypeScriptのstrictな型検査を基準にし、`any` を避けて `unknown` と型ガードを使う。`as` は最小限にし、APIレスポンス・フォーム入力を既存構成に合う方法でランタイム検証する。
- 状態をローカル・共有・フォーム・サーバー由来に分け、既存構成に合わせる。Zustand、React Hook Form、SWR/TanStack Query、zodは採用済みの場合の候補であり、新規導入を前提にしない。
- 単一責任を守り、100行を超えるコンポーネントは分割を検討する。コンポーネントはPascalCase、フックは `use` で始まるcamelCase、Route Handlerのディレクトリはkebab-case、ページは `page.tsx` を基本にする。

## 検証と完了

- テストは先行または実装と並行して用意し、境界値・エラーパスを優先する。Server/Clientの境界を分け、Route Handlerの要求・応答と外部依存を検証する。既存のJestやReact Testing Library等を使い、非同期Server Componentは使用環境で対応する検証方法を選ぶ。未対応の描画テストを成功扱いしない。
- 仕様と実装を照合し、エラーの握り潰し・秘密情報の埋め込み・過剰なClient境界を確認する。公開コンポーネント・Route Handlerの役割をコメントで示し、TODO/FIXMEに理由を書く。
- 定義済みのテスト・型検査・ビルドを実行する。設定を確認したうえで `npm run test` / `npm run build` が候補となる。型エラー、ビルドエラー・警告と未実行の検証を報告する。
- agent-crewで機能変更する場合は `docs/spec/features/<機能名>.md` を更新する。未作成なら `docs/spec/templates/feature-spec.md` を確認する。依頼範囲と衝突する場合は報告する。
- 要件と設計の矛盾、合意範囲を超える波及、テスト不能な構造、セキュリティ上の懸念があれば問題・理由・解決候補を報告して停止する。

完了報告には変更ファイル、実行した検証コマンドと生出力、仕様逸脱、未解決事項、次のレビューで確認してほしい点を含める。自己確認を独立レビューの完了と扱わない。

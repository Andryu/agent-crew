---
name: artifact-toc
description: >
  Artifact（HTMLページ）を作成・更新・公開するときに必ず目次（TOC）を付け、
  デザインはデジタル庁デザインシステムを参考にするためのスキル。
  設計書・レポート・比較資料・調査結果など、セクションが2つ以上あるページを Artifact として
  出力する場面では、ユーザーが「目次」と言わなくても必ずこのスキルを使うこと。
  ドキュメントをHTML化する、Artifactで出力する、ページを再設計する、といった依頼はすべて対象。
  オーナー指示（2026-08-10）: 「artifactを作成する際は必ず目次を出してください」
  「デジタル庁のデザインシステムを参考にする」。
---

# Artifact に必ず目次を付け、デジタル庁デザインシステムを参考にする

## なぜ必要か

- 設計書やレポートのArtifactは長くなる。目次がないと全体像が掴めず、目的のセクションに到達できない
- Artifactはclaude.aiの**サイドパネル（狭い幅）で開かれることが多い**。過去に「広い画面ではサイド目次、狭い画面では `display: none` で非表示」と実装してしまい、オーナーには目次が全く見えなかった失敗がある。**狭い画面で目次を消してはいけない**

## 必須要件

1. セクションが2つ以上あるページには目次を付ける
2. 各セクションに `id` を振り、目次はアンカーリンク（`href="#id"`）にする
3. **広い画面**: 左サイドに固定（`position: sticky`）で表示し、スクロールに追従させる
4. **狭い画面**（サイドパネル・スマホ、〜860px）: `display: none` にせず、**本文の最上部に枠付きボックスとして表示**する
5. 目次の項目にはセクション番号（§1, §2, …）を付け、本文の見出し番号と一致させる
6. キーボードフォーカスが見えるようにする（`:focus-visible`）

## 実装テンプレート

レイアウトは2カラムグリッド（目次 232px ＋ 本文）。以下をそのまま使ってよい。

```html
<div class="wrap">
  <header class="doc-head">…（grid-column: 1 / -1）…</header>
  <nav class="toc" aria-label="目次">
    <p class="toc-title">Contents</p>
    <ol>
      <li><a href="#s1"><span class="toc-num">§1</span>セクション名</a></li>
      <!-- セクション分だけ繰り返す -->
    </ol>
  </nav>
  <main>
    <section id="s1">…</section>
  </main>
</div>
```

```css
.wrap { display: grid; grid-template-columns: 232px minmax(0,1fr); gap: 48px;
        max-width: 1120px; margin: 0 auto; }
nav.toc { position: sticky; top: 32px; align-self: start; font-size: 13px; }
nav.toc ol { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--line); }
nav.toc a { display: block; color: var(--muted); text-decoration: none;
            padding: 5px 0 5px 14px; border-left: 2px solid transparent; margin-left: -1px; }
nav.toc a:hover, nav.toc a:focus-visible { color: var(--accent); border-left-color: var(--accent); }
nav.toc a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* 狭い画面: 隠さず、本文上部のボックスにする（display:none 禁止） */
@media (max-width: 860px) {
  .wrap { grid-template-columns: minmax(0,1fr); }
  nav.toc { position: static; margin: 0 0 36px; padding: 16px 18px;
            background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
}
```

## デザイン: デジタル庁デザインシステムを参考にする

ページのデザイン（タイポグラフィ・余白・カラー・アクセシビリティ）は
**デジタル庁デザインシステム**を参考にする。具体的な値と原則は
`references/degcy-design.md` を読むこと（Artifact作成時のみ読めばよい）。

最低限の要点: 本文16px以上・行間1.7／8pxグリッドの余白／コントラスト比4.5:1以上／
色だけで意味を伝えない／フォーカス可視化／装飾は最小限。

## Markdown の Artifact の場合

HTMLでなくMarkdownページを公開する場合も、冒頭に見出しへのアンカーリンクの箇条書きで目次を置く。

## 確認チェック（公開前）

- [ ] 目次がある
- [ ] ウィンドウ幅を狭めても目次が見える（`display: none` を使っていない）
- [ ] 目次のリンクを踏むと該当セクションへ飛ぶ
- [ ] 目次の番号と本文の見出し番号が一致している

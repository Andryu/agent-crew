# Ollama ベンチマーク実行ガイド

## 事前準備

```bash
ollama pull gemma4:12b
ollama pull qwen2.5:14b
ollama pull llama3.1:8b
ollama pull mistral-nemo:12b
```

## ベンチマーク実行

### シナリオ1: 日本語要約(家計簿)
```bash
bash scripts/ollama-benchmark.sh \
  "次の家計簿メモを3行で要約してください。重要なポイントを箇条書きで: 今月の支出内訳は食費38,000円(予算35,000円)、光熱費12,000円(予算10,000円)、交通費8,500円、娯楽費15,000円、医療費3,200円。合計76,700円で予算70,000円をオーバーした。外食が週3回あり食費を押し上げている。光熱費は気温が下がったためエアコン稼働増加が原因。"
```

### シナリオ2: 日本語QA(知識問答)
```bash
bash scripts/ollama-benchmark.sh \
  "iDeCoとNISAの違いを、会社員の視点から3点に絞って教えてください。具体的な金額の例も含めてください。"
```

### シナリオ3: コード生成(Python)
```bash
bash scripts/ollama-benchmark.sh \
  "Pythonで、CSVファイルを読み込んで月別の合計金額を集計し、棒グラフで表示する関数を書いてください。pandasとmatplotlibを使ってください。"
```

### シナリオ4: 英語タスク(翻訳+要約)
```bash
bash scripts/ollama-benchmark.sh \
  "Summarize the following in 2 Japanese sentences: Large language models (LLMs) are AI systems trained on vast amounts of text data that can generate human-like text, translate languages, write code, and answer questions. They use transformer architecture and are fine-tuned with human feedback to align with user intentions."
```

### シナリオ5: 論理推論
```bash
bash scripts/ollama-benchmark.sh \
  "太郎は花子より背が高い。花子は次郎より背が高い。次郎は三郎より背が高い。では、太郎と三郎の身長を比べるとどちらが高いですか？理由も説明してください。"
```

## 結果の確認

実行後、`docs/benchmarks/ollama-benchmark-*.md` に結果が保存されます。
結果ファイルの内容をClaude Codeに貼り付けると、モデル比較の分析をしてもらえます。

## モデルを絞って比較する場合

```bash
MODELS="gemma4:12b qwen2.5:14b" bash scripts/ollama-benchmark.sh "プロンプト"
```

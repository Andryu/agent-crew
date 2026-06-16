#!/bin/bash
# scripts/ollama-benchmark.sh
# 複数のOllamaモデルに同じプロンプトを投げて、応答速度とメモリ使用量を比較する。
# Mac mini上で `ollama serve` が起動している状態で実行する。
#
# 使い方:
#   bash scripts/ollama-benchmark.sh
#   bash scripts/ollama-benchmark.sh "比較したいプロンプト"
#   MODELS="gemma4:12b qwen2.5:14b" bash scripts/ollama-benchmark.sh

set -euo pipefail

MODELS="${MODELS:-gemma4:12b qwen2.5:14b llama3.1:8b mistral-nemo:12b}"
PROMPT="${1:-次の家計簿メモを3行で要約してください: 今月は食費が予算を1万円超えた。外食を減らして来月は調整したい。}"

OUT_DIR="$(dirname "$0")/../docs/benchmarks"
mkdir -p "$OUT_DIR"
RESULT_FILE="$OUT_DIR/ollama-benchmark-$(date +%Y%m%d-%H%M%S).md"

echo "# Ollama モデル比較結果" > "$RESULT_FILE"
echo "" >> "$RESULT_FILE"
echo "プロンプト: \`$PROMPT\`" >> "$RESULT_FILE"
echo "" >> "$RESULT_FILE"

for MODEL in $MODELS; do
  echo "=== $MODEL ==="

  if ! ollama list | awk '{print $1}' | grep -qx "$MODEL"; then
    echo "  スキップ: モデル未取得 (ollama pull $MODEL を先に実行してください)"
    echo "## $MODEL" >> "$RESULT_FILE"
    echo "" >> "$RESULT_FILE"
    echo "未取得のためスキップ" >> "$RESULT_FILE"
    echo "" >> "$RESULT_FILE"
    continue
  fi

  START=$(date +%s.%N)
  RESPONSE=$(ollama run "$MODEL" "$PROMPT" 2>/dev/null)
  END=$(date +%s.%N)
  ELAPSED=$(echo "$END - $START" | bc)

  echo "  所要時間: ${ELAPSED}秒"

  {
    echo "## $MODEL"
    echo ""
    echo "- 所要時間: ${ELAPSED}秒"
    echo "- 応答:"
    echo '```'
    echo "$RESPONSE"
    echo '```'
    echo ""
  } >> "$RESULT_FILE"
done

echo ""
echo "結果を保存しました: $RESULT_FILE"

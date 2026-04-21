#!/bin/bash
# 全エージェント一括テスト
for agent in Yuki Alex Mina Riku Sora Hana Kai Tomo Ren; do
  icon=""
  display=""
  case "$agent" in
    Yuki) icon="📋"; display="Yuki (PM)" ;;
    Alex) icon="🏗️"; display="Alex (Architect)" ;;
    Mina) icon="🎨"; display="Mina (UX)" ;;
    Riku) icon="🔨"; display="Riku (Dev)" ;;
    Sora) icon="🔍"; display="Sora (QA)" ;;
    Hana) icon="📝"; display="Hana (Review)" ;;
    Kai)  icon="🛡️"; display="Kai (Security)" ;;
    Tomo) icon="🚀"; display="Tomo (DevOps)" ;;
    Ren)  icon="📊"; display="Ren (Data)" ;;
  esac
  text="${icon} *${display}*: テスト: ${agent} からの通知です"
  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    -d "$(jq -n --arg t "$text" '{text: $t}')"
  sleep 1
done

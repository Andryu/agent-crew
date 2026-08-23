#!/bin/bash
# 解答者向けの簡易確認（holdout とは別物）:
#   workflow が YAML として読め、Pages のアップロード対象が _site になっているか。
# 使い方: リポジトリ直下で bash visible_test/smoke.sh
set -euo pipefail

WORK="${BENCH_WORK_DIR:-$PWD}"
F="$WORK/.github/workflows/deploy-pages.yml"
[[ -f "$F" ]] || { echo "NG: $F が無い" >&2; exit 1; }

PY=python3
if ! $PY -c 'import yaml' >/dev/null 2>&1; then
  UV="${BENCH_UV:-$HOME/.local/bin/uv}"
  [[ -x "$UV" ]] || UV=$(command -v uv)
  PY="$UV run --no-project --with pyyaml python"
fi

$PY - "$F" <<'EOF'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
steps = [s for j in (doc.get("jobs") or {}).values() for s in (j.get("steps") or [])]
ups = [s for s in steps if "upload-pages-artifact" in str(s.get("uses", ""))]
assert ups, "NG: upload-pages-artifact のステップが無い"
p = str((ups[0].get("with") or {}).get("path", "")).strip().rstrip("/")
assert p in ("_site", "./_site"), "NG: アップロード対象が _site でない: %r" % p
print("visible smoke: OK")
EOF

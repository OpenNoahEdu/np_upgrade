#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

models=(NP1100 NP1200 NP1300 NP1300真情版 NP1380 NP1500 'NP1500/I新春版' NP2150 NP2300 'NP2300+')

cat > upgrade.md <<'EOF'
# NP-upgrade

诺亚舟NP系列学习机升级包下载地址整理

EOF

for model in "${models[@]}"; do
  printf '\n## %s\n\n' "$model" >> upgrade.md
  output_file="$(mktemp)"

  if python3 scripts/noah-get.py "$model" --catalog 系统升级 --filter 升级程序 2>/dev/null | python3 scripts/noah-md.py --compact > "$output_file" 2>/dev/null \
    || python3 scripts/noah-get.py "$model" --catalog 升级程序 --filter 升级程序 2>/dev/null | python3 scripts/noah-md.py --compact > "$output_file" 2>/dev/null \
    || python3 scripts/noah-get.py "$model" --catalog 系统工具 --filter 升级程序 2>/dev/null | python3 scripts/noah-md.py --compact > "$output_file" 2>/dev/null \
    || python3 scripts/noah-get.py "$model" --catalog 工具 --filter 升级程序 2>/dev/null | python3 scripts/noah-md.py --compact > "$output_file" 2>/dev/null; then
    cat "$output_file" >> upgrade.md
  else
    echo "No upgrade catalog found for $model" >&2
    rm -f "$output_file"
    exit 1
  fi

  rm -f "$output_file"
done

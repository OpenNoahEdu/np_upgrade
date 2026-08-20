#!/usr/bin/env bash

cd "$(dirname "$0")/.."

set -euo pipefail

models=(NP1100 NP1200 NP1300 NP1300真情版 NP1380 NP1500 'NP1500/I新春版' NP2150 NP2300 'NP2300+')

for model in "${models[@]}"; do
  # 处理机型名中的特殊字符（比如 / 替换为 _ ），防止生成文件时路径报错
  filename="${model//\//_}"
  
  echo ">>> Processing $model..."
  python3 scripts/noah-get.py "$model" > "$filename.yml"
  python3 scripts/noah-md.py "$filename.yml" --compact > "$filename.md"
  python3 scripts/noah-sync.py "$filename.yml" --verify-md5 --verbose
done

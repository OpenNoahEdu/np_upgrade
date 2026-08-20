#!/usr/bin/env bash

cd "$(dirname "$0")/.."

set -euo pipefail

DO_UPDATE=0
DO_SYNC=1

for arg in "$@"; do
  case $arg in
    --update)
      DO_UPDATE=1
      DO_SYNC=1
      shift
      ;;
    --just-update)
      DO_UPDATE=1
      DO_SYNC=0
      shift
      ;;
    *)
      shift
      ;;
  esac
done

models=(NP1100 NP1200 NP1300 NP1300真情版 NP1380 NP1500 'NP1500/I新春版' NP2150 NP2300 'NP2300+')

for model in "${models[@]}"; do
  # 处理机型名中的特殊字符（比如 / 替换为 _ ），防止生成文件时路径报错
  filename="${model//\//_}"
  
  echo ">>> Processing $model..."
  
  if [ "$DO_UPDATE" -eq 1 ]; then
    echo "  -> Updating YAML and Markdown..."
    python3 scripts/noah-get.py "$model" > "$filename.yml"
    python3 scripts/noah-md.py "$filename.yml" --compact > "$filename.md"
  fi
  
  if [ "$DO_SYNC" -eq 1 ]; then
    if [ ! -f "$filename.yml" ]; then
      echo "  -> Error: $filename.yml not found. Please run with --update first."
      exit 1
    fi
    echo "  -> Syncing resources..."
    python3 scripts/noah-sync.py "$filename.yml" --verify-md5 --verbose
  fi
done

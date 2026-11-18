#!/usr/bin/env bash
# 以 git sparse checkout 取得「北科課程好朋友」爬蟲資料（gh-pages 分支）。
# 用法：scripts/fetch_data.sh 115 1 114 2 114 1   （學年 學期 成對）
set -euo pipefail
cd "$(dirname "$0")/.."
RAW=data/raw
if [ ! -d "$RAW/.git" ]; then
  git clone --depth 1 --branch gh-pages --filter=blob:none --no-checkout \
    https://github.com/gnehs/ntut-course-crawler-node "$RAW"
  git -C "$RAW" sparse-checkout init --no-cone
  git -C "$RAW" sparse-checkout set '/main.json' '/standards.json' '/calendar.json' '/analytics/'
fi
while [ $# -ge 2 ]; do
  git -C "$RAW" sparse-checkout add "/$1/$2/*.json" "/$1/standard.json"
  shift 2
done
git -C "$RAW" checkout

#!/usr/bin/env bash
# 建置靜態版並推送到 gh-pages 分支（GitHub Pages）。
# 先執行：python -m scripts.export_static   （更新 frontend/public/data/）
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_NAME="$(basename -s .git "$(git config --get remote.origin.url)")"
(cd frontend && VITE_STATIC=1 VITE_BASE="/${REPO_NAME}/" npx vite build --outDir ../site --emptyOutDir)
touch site/.nojekyll
cp site/index.html site/404.html
SRC_SHA="$(git rev-parse --short HEAD)"
TMP="$(mktemp -d)"
cp -r site/. "$TMP"/
cd "$TMP"
git init -q -b gh-pages
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-deploy}" -c user.email="${GIT_AUTHOR_EMAIL:-deploy@localhost}" \
  commit -qm "Deploy static site from ${SRC_SHA}"
git push -f "$(git -C "$OLDPWD" config --get remote.origin.url)" gh-pages
echo "已部署：https://$(git -C "$OLDPWD" config --get remote.origin.url | sed -E 's#.*github.com[:/]([^/]+)/([^/.]+).*#\1.github.io/\2#')/"

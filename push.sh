#!/usr/bin/env bash
# push.sh — 将本地仓库强制推送到 GitHub（覆盖远端 main）
# 用法:
#   bash push.sh                 # 自动提交所有改动并强推
#   bash push.sh "提交信息"       # 自定义提交信息
# 说明:
#   - 自动 git add -A 提交本地改动；无改动则直接推当前 HEAD
#   - 安全护栏: 远端为「公开」且本地跟踪了 config.toml(含密钥) 时立即中止
#   - 需要本机已登录 GitHub（Git Credential Manager / SSH），否则推送会失败
set -uo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$REPO_DIR" || { echo "❌ 无法进入 $REPO_DIR"; exit 1; }

REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
OWNER_REPO="${OWNER_REPO:-wowoduang/aivideo}"
MSG="${1:-auto: sync local $(date '+%Y-%m-%d %H:%M:%S')}"

echo "📁 仓库: $REPO_DIR"
echo "🌐 远端: $OWNER_REPO  ($REMOTE -> $BRANCH)"

# ---------- 安全护栏：公开仓库不得推送 config.toml ----------
vis="unknown"
if command -v curl >/dev/null 2>&1; then
  _tmp="$(mktemp 2>/dev/null || echo "/tmp/_repovis.$$")"
  _code=$(curl -s -o "$_tmp" -w "%{http_code}" "https://api.github.com/repos/$OWNER_REPO" 2>/dev/null || echo "000")
  if [ "$_code" = "200" ]; then
    if grep -q '"private":true' "$_tmp"; then vis="true"; else vis="false"; fi
  elif [ "$_code" = "404" ]; then
    vis="true"      # 私有仓库匿名不可见 → 视为私有
  fi
  rm -f "$_tmp" 2>/dev/null
fi

if [ "$vis" = "false" ]; then
  if git ls-files --error-unmatch config.toml >/dev/null 2>&1; then
    echo "❌ 中止：仓库为【公开】，而本地跟踪了 config.toml（含密钥）。"
    echo "   请先在 GitHub → 仓库 Settings → Danger Zone → Change visibility 设为 Private。"
    if [ "${ALLOW_SECRETS_ON_PUBLIC:-0}" = "1" ]; then
      echo "⚠️  已检测到 ALLOW_SECRETS_ON_PUBLIC=1，忽略护栏继续（风险自负）……"
    else
      exit 2
    fi
  fi
  echo "🌐 远端为公开仓库。"
elif [ "$vis" = "unknown" ]; then
  echo "⚠️  无法确认仓库可见性（可能触发 GitHub API 限流），按私有继续；请自行确认远端确为私有。"
else
  echo "🔒 远端为私有，安全。"
fi

# ---------- 提交本地改动 ----------
git add -A
if git diff --cached --quiet; then
  echo "ℹ️  没有需要提交的改动，直接推送当前 HEAD。"
else
  if git commit -m "$MSG"; then
    echo "✅ 已提交: $(git rev-parse --short HEAD)"
  else
    echo "❌ 提交失败。"; exit 3
  fi
fi

# ---------- 强制推送 ----------
echo "🚀 git push --force $REMOTE HEAD:$BRANCH ..."
if git push --force "$REMOTE" "HEAD:$BRANCH"; then
  echo "✅ 推送成功: $(git rev-parse --short HEAD) -> $REMOTE/$BRANCH"
else
  echo "❌ 推送失败（多为缺少 GitHub 写权限凭证）。"
  echo "   · 在「本机终端」运行一次并完成浏览器登录；或"
  echo "   · 提供带 repo 权限的 token: git push --force https://<TOKEN>@github.com/$OWNER_REPO HEAD:$BRANCH"
  exit 4
fi

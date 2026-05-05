#!/usr/bin/env bash
set -e

cd /AIVideo || exit 1

WORKSPACE_ROOT="${AIVIDEO_WORKSPACE_ROOT:-/AIVideo-workspace}"
APP_PORT="${APP_PORT:-8866}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

workspace_path() {
  local sub_dir="$1"
  if [ -n "$sub_dir" ]; then
    printf '%s/%s' "$WORKSPACE_ROOT" "$sub_dir"
  else
    printf '%s' "$WORKSPACE_ROOT"
  fi
}

install_runtime_dependencies() {
  if [ "${AIVIDEO_INSTALL_AT_STARTUP:-0}" != "1" ]; then
    log "跳过容器启动时依赖安装（镜像已内置依赖，可设置 AIVIDEO_INSTALL_AT_STARTUP=1 强制开启）"
    return 0
  fi

  log "检查并安装运行时依赖..."

  local requirements_file="requirements.txt"
  local installed_packages_file
  installed_packages_file="$(workspace_path 'runtime/.requirements_installed')"

  mkdir -p "$(workspace_path 'runtime')"

  if [ -f "$requirements_file" ]; then
    if [ ! -f "$installed_packages_file" ] || [ "$requirements_file" -nt "$installed_packages_file" ]; then
      log "发现新的依赖需求，开始安装..."

      INSTALL_RESULT=0

      if command -v sudo >/dev/null 2>&1; then
        log "尝试使用sudo安装依赖..."
        sudo pip install --no-cache-dir -r "$requirements_file" 2>&1 | while read -r line; do
          log "pip: $line"
        done
        INSTALL_RESULT=${PIPESTATUS[0]}
      else
        INSTALL_RESULT=1
      fi

      if [ $INSTALL_RESULT -ne 0 ]; then
        log "尝试用户级安装依赖..."
        pip install --user --no-cache-dir -r "$requirements_file" 2>&1 | while read -r line; do
          log "pip: $line"
        done
        export PATH="$HOME/.local/bin:$PATH"
      fi

      log "确保腾讯云SDK已安装..."
      if ! pip list | grep -q "tencentcloud-sdk-python"; then
        log "安装腾讯云SDK..."
        pip install --user "tencentcloud-sdk-python>=3.0.1200"
      else
        log "腾讯云SDK已安装"
      fi

      touch "$installed_packages_file"
      log "依赖安装完成"
    else
      log "依赖已是最新版本，跳过安装"
    fi
  else
    log "未找到 requirements.txt 文件"
  fi
}

check_requirements() {
  log "检查应用环境..."
  log "工作区根目录: ${WORKSPACE_ROOT}"

  if [ ! -f "config.toml" ]; then
    if [ -f "config.example.toml" ]; then
      log "复制示例配置文件..."
      cp config.example.toml config.toml
    else
      log "警告: 未找到配置文件"
    fi
  fi

  for dir in \
    "temp" \
    "cache" \
    "runtime" \
    "state" \
    "tasks" \
    "models" \
    "videos" \
    "subtitles" \
    "scripts" \
    "fonts" \
    "songs" \
    "analysis" \
    "analysis/json" \
    "analysis/narration_scripts" \
    "analysis/drama_analysis"; do
    local target_dir
    target_dir="$(workspace_path "$dir")"
    if [ ! -d "$target_dir" ]; then
      log "创建目录: $target_dir"
      mkdir -p "$target_dir"
    fi
  done

  install_runtime_dependencies
  log "环境检查完成"
}

start_api() {
  log "启动 AIVideo API + 前端静态资源..."

  if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ":${APP_PORT} "; then
      log "警告: 端口 ${APP_PORT} 已被占用"
    fi
  fi

  export AIVIDEO_API_HOST="0.0.0.0"
  export AIVIDEO_API_PORT="${APP_PORT}"

  exec uvicorn app.api.main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT}" \
    --workers 1 \
    --no-access-log
}

log "AIVideo Docker 容器启动中..."

check_requirements

case "$1" in
  "api"|"")
    start_api
    ;;
  "bash"|"sh")
    log "启动交互式 shell..."
    exec /bin/bash
    ;;
  "health")
    log "执行健康检查..."
    if curl -f "http://localhost:${APP_PORT}/api/v1/health" >/dev/null 2>&1; then
      log "健康检查通过"
      exit 0
    else
      log "健康检查失败"
      exit 1
    fi
    ;;
  *)
    log "执行自定义命令: $*"
    exec "$@"
    ;;
esac

#!/usr/bin/env bash
# 重新打包桌面应用：output/viz 的内容在编译时嵌入程序，数据或前端改动后需重跑本脚本。
# 产物：src-tauri/target/release/math2-map（可直接运行）以及 bundle/ 下的 deb、rpm、AppImage。
set -euo pipefail
cd "$(dirname "$0")"
[ -d node_modules ] || npm install --no-fund --no-audit
# NO_STRIP：linuxdeploy 自带的 strip 处理不了较新的系统库，Arch 系上打 AppImage 需要跳过
NO_STRIP=true npx tauri build "$@"

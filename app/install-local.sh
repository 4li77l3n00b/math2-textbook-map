#!/usr/bin/env bash
# 把已构建的程序安装到当前用户（~/.local），在应用菜单中出现“数二考点地图”。
# 卸载：./install-local.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"
BIN=~/.local/bin/math2-map
DESK=~/.local/share/applications/math2-map.desktop
ICON=~/.local/share/icons/hicolor/256x256/apps/math2-map.png
if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$BIN" "$DESK" "$ICON"
  update-desktop-database ~/.local/share/applications 2>/dev/null || true
  echo "已卸载"; exit 0
fi
[ -x src-tauri/target/release/math2-map ] || { echo "先运行 ./build.sh"; exit 1; }
install -Dm755 src-tauri/target/release/math2-map "$BIN"
install -Dm644 src-tauri/icons/128x128@2x.png "$ICON"
mkdir -p "$(dirname "$DESK")"
cat > "$DESK" <<DESKTOP
[Desktop Entry]
Type=Application
Name=数二考点地图
Comment=考研数学二真题与教材知识点映射
Exec=$BIN
Icon=math2-map
Categories=Education;
Terminal=false
StartupWMClass=math2-map
DESKTOP
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "已安装：$BIN（应用菜单：数二考点地图）"

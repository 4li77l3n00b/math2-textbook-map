#!/usr/bin/env bash
# 把已构建的程序安装到当前用户（~/.local），在应用菜单中出现“数二考点地图”。
# 卸载：./install-local.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"
BIN=~/.local/bin/math2-map
DESK=~/.local/share/applications/math2-map.desktop
ICONS=~/.local/share/icons/hicolor
SIZES="16 24 32 48 64 128 256 512"
if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$BIN" "$DESK"
  for s in $SIZES; do rm -f "$ICONS/${s}x${s}/apps/math2-map.png"; done
  kbuildsycoca6 >/dev/null 2>&1 || true
  update-desktop-database ~/.local/share/applications 2>/dev/null || true
  echo "已卸载"; exit 0
fi
[ -x src-tauri/target/release/math2-map ] || { echo "先运行 ./build.sh"; exit 1; }
install -Dm755 src-tauri/target/release/math2-map "$BIN"
# the window/taskbar icon comes from the .desktop entry whose name matches the Wayland app_id (math2-map),
# so install the icon in every common size and refresh the desktop caches (KDE reads its sycoca cache)
for s in $SIZES; do
  mkdir -p "$ICONS/${s}x${s}/apps"
  python3 -c "from PIL import Image; Image.open('app-icon.png').resize(($s, $s), Image.LANCZOS).save('$ICONS/${s}x${s}/apps/math2-map.png')"
done
touch "$ICONS"
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
kbuildsycoca6 >/dev/null 2>&1 || true
echo "已安装：$BIN（应用菜单：数二考点地图）"

#!/usr/bin/env bash
# 把已构建的程序安装到当前用户（~/.local），在应用菜单中出现“数二考点地图”。
# 卸载：./install-local.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"
# one name for the binary, the Wayland app_id, the .desktop file and the icon. It has no dash on purpose:
# KDE tries dash-shortened names inside each theme before moving on, so "math2-map" matched breeze's "math2" symbol
NAME=math2map
BIN=~/.local/bin/$NAME
DESK=~/.local/share/applications/$NAME.desktop
ICONS=~/.local/share/icons/hicolor
SIZES="16 24 32 48 64 128 256 512"
remove() {  # $1 = name; also clears what earlier versions installed as math2-map
  rm -f ~/.local/bin/"$1" ~/.local/share/applications/"$1".desktop
  for s in $SIZES; do rm -f "$ICONS/${s}x${s}/apps/$1.png"; done
}
refresh() {
  touch "$ICONS"
  update-desktop-database ~/.local/share/applications 2>/dev/null || true
  kbuildsycoca6 >/dev/null 2>&1 || true
}
remove math2-map
if [ "${1:-}" = "--uninstall" ]; then
  remove "$NAME"; refresh
  echo "已卸载"; exit 0
fi
[ -x "src-tauri/target/release/$NAME" ] || { echo "先运行 ./build.sh"; exit 1; }
install -Dm755 "src-tauri/target/release/$NAME" "$BIN"
# the window/taskbar icon comes from the .desktop entry whose name matches the Wayland app_id (the binary name),
# so install the icon in every common size and refresh the desktop caches (KDE reads its sycoca cache)
for s in $SIZES; do
  mkdir -p "$ICONS/${s}x${s}/apps"
  python3 -c "from PIL import Image; Image.open('app-icon.png').resize(($s, $s), Image.LANCZOS).save('$ICONS/${s}x${s}/apps/$NAME.png')"
done
mkdir -p "$(dirname "$DESK")"
cat > "$DESK" <<DESKTOP
[Desktop Entry]
Type=Application
Name=数二考点地图
Comment=考研数学二真题与教材知识点映射
Exec=$BIN
Icon=$NAME
Categories=Education;
Terminal=false
StartupWMClass=$NAME
DESKTOP
refresh
echo "已安装：$BIN（应用菜单：数二考点地图）"

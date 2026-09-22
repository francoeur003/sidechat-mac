#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${SIDECHAT_BUILD_PYTHON:-$ROOT/build/distribution-venv/bin/python}"
VERSION="$("$PY" -c 'import runpy; print(runpy.run_path("src/sidechat_brand.py")["VERSION"])')"
[[ "$(uname -m)" == arm64 ]] || { echo '本构建脚本只制作 Apple Silicon 版本'; exit 1; }
mkdir -p build/SideChat.iconset
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" assets/sidechat-logo.png --out "build/SideChat.iconset/icon_${size}x${size}.png" >/dev/null
  twice=$((size*2))
  sips -z "$twice" "$twice" assets/sidechat-logo.png --out "build/SideChat.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns build/SideChat.iconset -o assets/SideChat.icns
PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache" "$PY" -m PyInstaller --noconfirm --clean packaging/sidechat.spec
codesign --force --deep --sign - dist/SideChat.app
codesign --verify --deep --strict dist/SideChat.app
mkdir -p dist/dmg-content
# Copy only the bundle and public install note. No source working directory or user data.
ditto dist/SideChat.app dist/dmg-content/SideChat.app
cp docs/安装说明.txt dist/dmg-content/
ln -sfn /Applications dist/dmg-content/Applications
hdiutil create -volname 'SideChat' -srcfolder dist/dmg-content -ov -format UDZO "dist/SideChat-$VERSION-macOS-arm64.dmg"
ditto -c -k --sequesterRsrc --keepParent dist/SideChat.app "dist/SideChat-$VERSION-macOS-arm64.zip"
(cd dist && shasum -a 256 "SideChat-$VERSION-macOS-arm64.dmg" "SideChat-$VERSION-macOS-arm64.zip" > SHA256SUMS.txt)

#!/usr/bin/env bash
# Reproduziert die Analyse des Hexagon App Launchers nach ./work (gitignored).
# Benötigt: 7z (brew install p7zip / sevenzip), python3, JDK (jimage), optional CFR-Decompiler.
#   tools/extract_applauncher.sh ~/Downloads/applauncher.exe
set -euo pipefail
EXE="${1:?Pfad zur applauncher.exe}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$ROOT/work"
TOOLS="$ROOT/tools"
mkdir -p "$W"/{overlay,carved,cab,modules,classes}

shasum -a 256 "$EXE"
7z e -y -o"$W/overlay" "$EXE" '[0]' >/dev/null
python3 -I "$TOOLS/carve_ai_sfx.py" "$W/overlay/[0]" "$W/carved"
7z x -y -o"$W/cab" "$W/carved/AppLauncher1.cab" >/dev/null
jimage extract --include 'regex:/com\.hexagon.*' --dir "$W/modules" "$W/cab/modules"
for m in "$W"/modules/com.hexagon.*; do cp -R "$m/com" "$W/classes/"; done
(cd "$W/classes" && zip -qr "$W/applauncher-classes.jar" com)
find "$W/modules" -name MANIFEST.MF -path '*core*' -exec cat {} \;

CFR="${CFR_JAR:-$W/cfr.jar}"
if [[ ! -f "$CFR" ]]; then
  curl -fsSL -o "$CFR" https://github.com/leibnitz27/cfr/releases/download/0.152/cfr-0.152.jar || true
fi
if [[ -f "$CFR" ]]; then
  java -jar "$CFR" "$W/applauncher-classes.jar" --outputdir "$W/src" >/dev/null
  echo "Dekompiliert nach $W/src (NICHT committen)"
fi

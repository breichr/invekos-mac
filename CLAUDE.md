# CLAUDE.md – invekos-gis-mac

## Ziel
INVEKOS-GIS (AMA, Flächendigitalisierung im Mehrfachantrag) auf macOS starten,
ohne Windows-VM. Die AMA unterstützt offiziell nur Windows 10+ x64 über den
„Hexagon App Launcher" (`applauncher.exe`). Dieses Repo baut den Launcher als
plattformunabhängiges Python-Skript nach.

## Stand (2026-10-13)
- `applauncher.exe` analysiert (Hexagon App Launcher **1.17.2.0**, Advanced Installer 16.3).
  Ergebnis in `docs/launcher-analysis.md`.
- `src/hexagon_launcher.py` implementiert den Ablauf (Descriptor laden → Ressourcen laden → Java starten).
  Gegen einen Fake-Server getestet (`tests/`), **noch nicht gegen den echten AMA-Server**.
- Echter Descriptor geholt (`--inspect`, 2026-10-13) – Ergebnis unten, „Echter AMA-Descriptor".
- Offen: erster echter Start → siehe „Nächste Schritte".

## Echter AMA-Descriptor (anonymisiert)
- `appName` GeoMedia Smart Client, `version` 1.17.2.0, `mainClass` `com.intergraph.web.SmartClient`,
  `codebase` `https://gsc.services.ama.at:443/GMSC/api/v1/hnlp/smartclient/downloads`,
  hrefs relativ als `?resource=jars%2f<name>.jar&type=jar`.
- `jvmArgs`: `-Djava.locale.providers=COMPAT,CLDR -Xmx1024m` (COMPAT gibt es bis JDK 22 → JDK 21 ok).
- `appArgs`: `codebase=…/GMSC/`, `site=GMSC`, `directory.default.root=%LOCALAPPDATA%/Intergraph/SmartClient`,
  `directory.default.cache=…/cache`, `sessionid=<UUID, geheim>`, `requesttype=hnlp`.
  → Launcher ersetzt `%LOCALAPPDATA%`/`%APPDATA%` (macOS: `~/Library/Application Support`).
- JRE im Original: `java-runtime-image-18.0.1.12-windows-x64` → wir nutzen Liberica JDK 21 Full.
- ~150 JARs ohne os/arch, darunter `javafx-*-17.0.0.1-win.jar` (Windows-JavaFX; bei JDK mit
  eingebautem JavaFX gewinnen dessen Module, die Klassen auf dem Classpath werden ignoriert)
  und `bridj-0.7.0-windows-only.jar`.
- `nativelib`: `ecwjp2-jni` (ECW/JPEG2000-Rasterformat) für linux/amd64, **mac os x/x86_64**,
  windows/amd64, windows/x86; `gmsc-jni-geolocator` nur windows/amd64 (Standortbestimmung).
  Auf Apple Silicon (arm64-JDK, `os.arch=aarch64`) passt keine → ECW-Raster evtl. nicht lesbar.
  Ausweg falls nötig: x86_64-JDK unter Rosetta (Launcher filtert nach `os.arch` des gestarteten Java).

## Kernerkenntnisse (Kurzfassung)
- Der Launcher ist selbst Java (JavaFX), per jlink in `modules` eingebettet; Module
  `com.hexagon.applauncher.core` / `.common`. Main: `com.hexagon.applauncher.core.AppLauncher`.
- Browser öffnet `hnlps://…` → Launcher ersetzt `hnlps:`→`https:` (`hnlp:`→`http:`) = Descriptor-URL.
- Descriptor (JSON): `codebase, version, appName, appIcon, appSplashImage, localization,
  mainClass, jvmArgs[], appArgs[], offlineAllowed, createShortcut, resources[]`.
- `resources[]`: `{type: jre|jar|nativelib|image|setup, href, os?, osVersion?, arch?, hash?}`.
  Filter wie Java: `os.name.startsWith(os)`, `os.version == osVersion`, `os.arch == arch` (lowercase).
- Start im Original: `<cache>/<jre>/bin/java.exe <jvmArgs> -cp <jars;> -Djava.library.path=<natives;>
  -Djavafx.cachedir=… <proxy -D…> <mainClass> <appArgs>`.
- JARs werden im Original signaturgeprüft (`JarVerifier`, Nutzer muss Signer bestätigen).
  Unser Skript prüft beim Download mit `jarsigner -verify` (ungültig, unsigniert oder
  unsignierte Einträge → Abbruch), Signer per `keytool -printcert -jarfile` (SHA-256),
  bestätigte Signer in `~/.hexagon-applauncher-mac/trusted_signers.json`.
  Im Cache liegen nur geprüfte JARs (`--no-verify` → separate `unverified_*`-Dateien).

## Leitplanken
- **Keine dekompilierten Hexagon-Quellen, Binaries oder die .exe committen** (Urheberrecht).
  Nur eigene Beschreibung in `docs/`. Zum Nachvollziehen: `tools/extract_applauncher.sh`
  schreibt nach `work/` (gitignored).
- **Keine echten hnlps-URLs / Descriptoren mit Token committen** – das sind Session-Zugangsdaten.
  Echte Descriptoren nur anonymisiert als Fixture ablegen.
- Kommunikation mit dem AMA-Server nicht verändern: nur *wie* der Client gestartet wird.
  Keine Requests fälschen, keine Daten manipulieren.
- Java auf dem Mac ausschließlich über Homebrew (siehe `Brewfile`).
- Python: nur Standardbibliothek, läuft mit macOS-System-Python 3.9+.
- Sprache für Doku/Ausgaben: Deutsch.

## Nächste Schritte
1. ~~Descriptor holen und auswerten~~ (erledigt, siehe oben).
2. `brew bundle` (JDK 21 Full), dann Start mit `--jdk 21` (frische hnlps-URL, Session läuft ab).
3. Fehler/Stacktraces analysieren (JavaFX-Konflikt mit `-win`-JARs, fehlende Natives, Pfade).
   Prüfen, ob Orthofotos ohne `ecwjp2`-Natives angezeigt werden (vermutlich per WMS/WMTS → ja).
4. Beim ersten echten Start: angezeigten Signer (Hexagon-Zertifikat?) prüfen und bestätigen.
5. Optional: `hnlps://`-URL-Handler als kleine macOS-App (z. B. AppleScript/Platypus oder
   Swift-Stub), damit der Button in eAMA direkt startet.
6. Optional: Brew-Formel/Cask im eigenen Tap.

## Befehle
- Tests: `python3 -m unittest discover -s tests -v` (braucht `javac`/`java`)
- Launcher-Analyse reproduzieren (Linux/macOS mit 7z, Python, JDK): `tools/extract_applauncher.sh path/to/applauncher.exe`

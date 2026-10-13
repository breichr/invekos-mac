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
- Offen: echten Descriptor holen (`--inspect`) und auswerten → siehe „Nächste Schritte".

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
1. Am Mac: hnlps-URL abgreifen (Chrome DevTools-Konsole: „Failed to launch 'hnlps://…'")
   und `python3 src/hexagon_launcher.py --inspect '<url>'` laufen lassen.
2. Descriptor auswerten: JRE-Version → passendes `liberica-jdk<N>-full` installieren;
   gibt es `nativelib` nur für `windows`? Wenn ja: Inhalt der ZIPs prüfen (welche DLLs, wofür).
3. Starten mit `--jdk <N>`; Fehler/Stacktraces analysieren (fehlende natives, JavaFX, Pfad-Trenner,
   Windows-spezifische Pfade in jvmArgs/appArgs).
4. Beim ersten echten Start: angezeigten Signer (Hexagon-Zertifikat?) prüfen und bestätigen.
5. Optional: `hnlps://`-URL-Handler als kleine macOS-App (z. B. AppleScript/Platypus oder
   Swift-Stub), damit der Button in eAMA direkt startet.
6. Optional: Brew-Formel/Cask im eigenen Tap.

## Befehle
- Tests: `python3 -m unittest discover -s tests -v` (braucht `javac`/`java`)
- Launcher-Analyse reproduzieren (Linux/macOS mit 7z, Python, JDK): `tools/extract_applauncher.sh path/to/applauncher.exe`

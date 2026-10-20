# Analyse: Hexagon App Launcher (AMA `applauncher.exe`)

Analysiert am 2026-10-13. Datei von ama.at, Größe 40.285.280 Bytes,
SHA-256 `dbc52a18cec6c4531b04b38a9aa884ad26dc7c5ee0e87c26168c4f1ebafce58c`.
Zweck: Interoperabilität (Start unter macOS). Beschreibung in eigenen Worten,
kein Hexagon-Code in diesem Repo.

## 1. Verpackung
- PE32-Stub von **Advanced Installer 16.3** („ADVINSTSFX"-Overlay).
- Overlay enthält eine Dateitabelle am Ende: `AppLauncher.aiui`, `AppLauncher.msi`,
  `AppLauncher1.cab`, `AppLauncher.ini`.
- Die ersten 0x200 Bytes jeder eingebetteten Datei sind mit `0xFF` XOR-verschleiert.
  Danach normale MSI- bzw. CAB-Datei (CAB: 176 Dateien, ~34 MB).
- Installiert nach `%APPDATA%\Hexagon\App Launcher` (`[AppDataFolder][Manufacturer]\[ProductName]`).
- Inhalt: jlink-Java-Runtime für Windows (java.base, java.desktop, java.net.http, java.xml,
  java.prefs, java.logging, jdk.crypto.*, javafx.base/controls/graphics …) mit den
  Launcher-Modulen im `lib/modules`-Image.
- MSI-CustomActions zeigen die Startzeile:
  `"[APPDIR]bin\javaw.exe" --module-path "[APPDIR]jars" -m com.hexagon.applauncher.core/com.hexagon.applauncher.core.AppLauncher --url=[RESTARTURL]`

## 2. Launcher (Java, Version 1.17.2.0)
Module: `com.hexagon.applauncher.core`, `com.hexagon.applauncher.common`.

### Kommandozeilen-Argumente (`--name=wert`)
| Argument | Werte |
|---|---|
| `url` | Descriptor-URL (`hnlp(s)://` oder `http(s)://`) |
| `show-console` | true/false |
| `log-level` | OFF…ALL (java.util.logging) |
| `cleanup` | apps / uninstall |
| `create-shortcuts` | true/false (Default true, Windows-VBS) |
| `auto-update` | true/false |
| `base-directory` | Basisverzeichnis |
| `debug` | JDWP-Port |

### Ablauf
1. `hnlp:`→`http:`, `hnlps:`→`https:`.
2. Basisverzeichnis: Windows `%LOCALAPPDATA%` (Fallback `%APPDATA%`), sonst `user.home`.
   Darin `applauncher.conf` (serialisierte UserData: Cache-Zuordnung, erlaubte Signer),
   `cache/`, `apps/<host><port><pfad mit _>/descriptor.json`.
3. Descriptor per GET (Timeout 30 s, Redirects folgen). Offline-Fallback auf gespeicherte Kopie,
   wenn `offlineAllowed`.
4. App-Icon, Splash (`name@<scale>x.ext`, Fallback ohne Scale), Lokalisierung
   (`<localization>?language=<de>`).
5. Versionscheck: Launcher-Version ≥ `descriptor.version`, sonst Ressource `setup`
   (Exe) laden und `<exe> /passive RESTARTURL=<hnlps-url>` ausführen.
6. Ressourcen laden (nur die, deren `os/osVersion/arch` passen). `hash` dient als Cache-Schlüssel.
   JARs werden mit `JarVerifier` geprüft; unbekannte Signer → Dialog.
   Nicht-JAR-Ressourcen (jre, nativelib) sind ZIPs und werden entpackt (ohne META-INF).
7. Start (Arbeitsverzeichnis = `<jre>/bin`):
   ```
   <jre>/bin/java.exe <jvmArgs…> -cp ../../../cache/<jar>;… \
     -Djava.library.path=../../../cache/<native>;… \
     -Djavafx.cachedir=<cache>/openjfx/<appdir> <Proxy-Properties als -D…> \
     <mainClass> <appArgs…>
   ```
   Hinweis: Trenner `;` ist im Original hartcodiert (Windows).

### Descriptor-Schema (abgeleitet)
```json
{
  "codebase": "https://…/",          // Basis für relative hrefs
  "version": "1.0.0",                 // Mindestversion des Launchers
  "appName": "…",
  "appIcon": "…png", "appShortcutIcon": "…ico", "appSplashImage": "…png",
  "localization": "…",
  "mainClass": "…",
  "offlineAllowed": false, "createShortcut": false,
  "jvmArgs": ["…"], "appArgs": ["…", "site=…"],
  "resources": [
    {"type": "jre|jar|nativelib|image|setup", "href": "…",
     "os": "windows", "osVersion": null, "arch": "amd64", "hash": "…"}
  ]
}
```

## 3. Folgerungen für macOS
- JARs sind plattformunabhängig → mit eigenem JDK (Homebrew) startbar.
- Risiko: `nativelib` nur für Windows. Ob und wofür, zeigt erst der echte Descriptor.
- `jre` (Windows) wird ignoriert; Version daraus ableiten und Liberica Full / ZuluFX nutzen.
- Self-Update (`setup`) wird ignoriert.

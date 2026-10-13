# invekos-gis-mac

Inoffizieller Starter für das **INVEKOS-GIS** der AMA (GeoMedia Smart Client) auf macOS.
Baut den Windows-only „Hexagon App Launcher" als Python-Skript nach und startet die
Java-Anwendung mit einem per Homebrew installierten JDK.

> Inoffiziell, nicht von AMA oder Hexagon unterstützt. Nach dem Bearbeiten
> im eAMA-Browser prüfen, ob die Flächen korrekt übernommen wurden.

## Installation
```sh
brew bundle            # Liberica JDK 17 Full (mit JavaFX), p7zip
```

## Nutzung
1. In Chrome eAMA → Flächen → INVEKOS-GIS öffnen, DevTools-Konsole (⌥⌘J) offen lassen,
   „INVEKOS-GIS aufrufen" klicken. Die Konsole zeigt `Failed to launch 'hnlps://…'` → URL kopieren.
2. Descriptor ansehen:
   ```sh
   python3 src/hexagon_launcher.py --inspect 'hnlps://…'
   ```
3. Starten (Java-Version laut Descriptor):
   ```sh
   python3 src/hexagon_launcher.py --jdk 17 'hnlps://…'
   ```

Der Link ist ein Zugangsschlüssel zur Session – nicht weitergeben oder committen.

## Aufbau
| Pfad | Inhalt |
|---|---|
| `src/hexagon_launcher.py` | Launcher (nur Python-Standardbibliothek) |
| `docs/launcher-analysis.md` | Wie der Original-Launcher funktioniert |
| `tools/` | Analyse reproduzieren (`extract_applauncher.sh`, `carve_ai_sfx.py`) |
| `tests/` | E2E-Test gegen Fake-Server: `python3 -m unittest discover -s tests -v` |

## Rechtliches
Analyse zum Zweck der Interoperabilität (§ 40e UrhG). Das Repo enthält keinen Code
und keine Binaries von Hexagon/AMA.

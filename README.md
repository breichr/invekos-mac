# invekos-gis-mac

Inoffizieller Starter für das **INVEKOS-GIS** der AMA (GeoMedia Smart Client) auf macOS.
Baut den Windows-only „Hexagon App Launcher" als Python-Skript nach und startet die
Java-Anwendung mit einem per Homebrew installierten JDK.

> Inoffiziell, nicht von AMA oder Hexagon unterstützt. Nach dem Bearbeiten
> im eAMA-Browser prüfen, ob die Flächen korrekt übernommen wurden.

## Installation
```sh
brew trust bell-sw/liberica   # offizieller Tap von BellSoft; neuere Homebrew-Versionen verlangen das
brew bundle                   # Liberica JDK 21 Full (mit JavaFX), p7zip
```

## Nutzung
1. In Chrome eAMA → Flächen → INVEKOS-GIS öffnen, DevTools-Konsole (⌥⌘J) offen lassen,
   „INVEKOS-GIS aufrufen" klicken. Die Konsole zeigt `Failed to launch 'hnlps://…'` → URL kopieren.
2. Descriptor ansehen:
   ```sh
   python3 src/hexagon_launcher.py --inspect 'hnlps://…'
   ```
3. Starten (AMA-Descriptor verlangt Java 18 → JDK 21 verwenden):
   ```sh
   python3 src/hexagon_launcher.py --jdk 21 'hnlps://…'
   ```

Beim ersten Download prüft der Launcher die JAR-Signaturen (`jarsigner`) und fragt,
ob man dem Herausgeber (Zertifikat, SHA-256-Fingerabdruck) vertraut. Die Antwort wird in
`~/.hexagon-applauncher-mac/trusted_signers.json` gespeichert. Ohne Terminal-Rückfrage:
`--trust-signer <SHA-256>`. Prüfung abschalten (nicht empfohlen): `--no-verify`.

Der Link ist ein Zugangsschlüssel zur Session – nicht weitergeben oder committen.

## Apple Silicon: Kartenhintergrund (ECW)
Den Orthofoto-Hintergrund liest der Smart Client im ECW-Format über eine native Bibliothek,
die es für macOS nur als Intel-Version (`x86_64`) gibt. Mit dem Apple-Silicon-Java startet der
Client, die Karte bleibt aber ohne Hintergrund. Abhilfe: ein Intel-Java 17 unter Rosetta,
installiert über ein zweites Homebrew für Intel unter `/usr/local`. Der Smart Client ist für
Java 10 gebaut, Java 17 reicht. Das Apple-Silicon-Java 21 bleibt daneben bestehen.
```sh
softwareupdate --install-rosetta --agree-to-license
arch -x86_64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
arch -x86_64 /usr/local/bin/brew tap bell-sw/liberica
arch -x86_64 /usr/local/bin/brew trust bell-sw/liberica
arch -x86_64 /usr/local/bin/brew install --cask liberica-jdk17-full
python3 src/hexagon_launcher.py --jdk 17 'hnlps://…'
```
In der Ausgabe muss `Plattform : os=mac os x arch=x86_64` stehen.

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

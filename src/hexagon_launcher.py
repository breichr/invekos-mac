#!/usr/bin/env python3
"""
Minimaler Nachbau des Hexagon App Launchers (v1.17.2) für macOS/Linux.

Das Original (Windows) macht:
  1. hnlps://...  ->  https://...   (Descriptor-URL)
  2. descriptor.json laden (codebase, mainClass, jvmArgs, appArgs, resources)
  3. Ressourcen laden: JAR, NATIVELIB (ZIP), JRE (ZIP, Windows), IMAGE, SETUP (.exe)
  4. java -cp <jars> -Djava.library.path=<natives> <jvmArgs> <mainClass> <appArgs>

Dieses Skript macht dasselbe, nutzt aber das lokal installierte Java
(empfohlen: JDK *mit JavaFX*), per Homebrew:
  brew install --cask zulufx                                  # neueste Version
  brew tap bell-sw/liberica && brew install --cask liberica-jdk17-full   # z. B. Java 17

Nutzung:
  python3 hexagon_launcher.py --inspect 'hnlps://…'   # nur Descriptor anzeigen
  python3 hexagon_launcher.py 'hnlps://…'             # herunterladen + starten
  python3 hexagon_launcher.py --jdk 17 'hnlps://…'    # bestimmte Java-Version

JAR-Signaturen werden beim Download mit jarsigner geprüft (wie JarVerifier im Original).
Unbekannte Herausgeber muss man einmal bestätigen (Abfrage oder --trust-signer <SHA-256>);
sie werden in ~/.hexagon-applauncher-mac/trusted_signers.json gespeichert.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE = Path.home() / ".hexagon-applauncher-mac"
TRUST_FILE = BASE / "trusted_signers.json"
UA = "Java-http-client/17"  # wie der Original-Launcher (java.net.http)


class VerifyError(Exception):
    pass


def to_http(url: str) -> str:
    return url.replace("hnlps:", "https:", 1).replace("hnlp:", "http:", 1)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def resolve(codebase: str, href: str) -> str:
    return href if "://" in href else codebase + href


def java_platform(java: str) -> tuple:
    """(os.name, os.arch) des Java, das gestartet wird – lowercase, wie im Original.
    Entscheidend für native Bibliotheken: ein x86_64-JDK unter Rosetta braucht
    x86_64-Natives, auch wenn Python selbst arm64 ist."""
    try:
        r = subprocess.run([java, "-XshowSettings:properties", "-version"],
                           capture_output=True, text=True, timeout=30)
        props = dict(re.findall(r"^\s*(os\.name|os\.arch) = (.*?)\s*$", r.stderr, re.M))
        if "os.name" in props and "os.arch" in props:
            return props["os.name"].lower(), props["os.arch"].lower()
    except OSError:
        pass
    # Fallback ohne Java: aus Python ableiten (Java-Schreibweise)
    osname = platform.system().lower()
    osname = "mac os x" if osname == "darwin" else osname
    arch = platform.machine().lower()
    return osname, {"arm64": "aarch64", "x86_64": "amd64" if osname == "linux" else "x86_64"}.get(arch, arch)


def platform_matches(res: dict, plat: tuple) -> bool:
    """Gleiche Logik wie AppResource.checkPlatform(): os.name.startsWith(os), os.arch == arch."""
    osname, arch = plat
    if res.get("os") and not osname.startswith(res["os"].lower()):
        return False
    if res.get("arch") and res["arch"].lower() != arch:
        return False
    return True


def expand_vars(arg: str) -> str:
    """Windows-Variablen wie %LOCALAPPDATA% in jvmArgs/appArgs ersetzen (Java tut das nicht).
    LOCALAPPDATA/APPDATA -> Programmdaten-Ordner des Systems, sonst Umgebungsvariable."""
    if sys.platform == "darwin":
        appdata = str(Path.home() / "Library" / "Application Support")
    else:
        appdata = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    defaults = {"LOCALAPPDATA": appdata, "APPDATA": appdata}

    def sub(m):
        name = m.group(1)
        return os.environ.get(name) or defaults.get(name.upper(), m.group(0))
    return re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", sub, arg)


def summarize(d: dict, plat: tuple) -> None:
    print(f"appName   : {d.get('appName')}")
    print(f"version   : {d.get('version')}")
    print(f"codebase  : {d.get('codebase')}")
    print(f"mainClass : {d.get('mainClass')}")
    print(f"jvmArgs   : {d.get('jvmArgs')}")
    print(f"appArgs   : {d.get('appArgs')}")
    print(f"Plattform : os={plat[0]} arch={plat[1]} (laut Java)")
    print("resources :")
    for r in d.get("resources", []):
        tag = "OK " if platform_matches(r, plat) else "-- "
        print(f"  {tag}{r.get('type'):9} os={r.get('os')!s:8} arch={r.get('arch')!s:7} {r.get('href')}")
    print("\n(OK = passt laut os/arch-Filter zu diesem Mac, -- = für anderes System)")


def safe_name(href: str, res_hash: str = None) -> str:
    """Cache-Dateiname. Wie im Original ist `hash` der Cache-Schlüssel: neuer Hash
    (neue Version unter gleicher URL) -> neue Datei. Ohne Hash: Schlüssel = URL."""
    url = urllib.parse.urlsplit(href)
    # AMA: …/downloads?resource=jars%2fgmsc-16.7.19.1.jar&type=jar -> Name aus `resource`
    name = urllib.parse.parse_qs(url.query).get("resource", [url.path])[0]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name.rstrip("/").split("/")[-1]) or "res"
    key = f"{href}#{res_hash}" if res_hash else href
    return hashlib.sha1(key.encode()).hexdigest()[:10] + "_" + name


NATIVE_SUFFIXES = (".dylib", ".jnilib", ".so", ".dll")


def native_dirs(root: Path) -> list:
    """Alle Ordner im entpackten Natives-ZIP, die native Bibliotheken enthalten
    (java.library.path sucht nicht rekursiv)."""
    dirs = sorted({str(f.parent) for f in root.rglob("*")
                   if f.is_file() and f.name.lower().endswith(NATIVE_SUFFIXES)})
    return dirs or [str(root)]


def jdk_tool(java: str, name: str) -> str:
    """jarsigner/keytool aus demselben JDK wie `java`, sonst aus PATH."""
    p = Path(shutil.which(java) or java).resolve().parent / name
    if p.exists():
        return str(p)
    tool = shutil.which(name)
    if not tool:
        raise VerifyError(f"{name} nicht gefunden (JDK statt JRE installieren oder --no-verify)")
    return tool


def run_tool(tool: str, *args: str):
    # Ausgabe ist lokalisiert -> Englisch erzwingen, damit sie auswertbar ist
    r = subprocess.run([tool, "-J-Duser.language=en", *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def jar_signers(java: str, jar: Path) -> dict:
    """Prüft die Signatur eines JARs, liefert {SHA-256-Fingerabdruck: Owner} der Signer."""
    rc, out = run_tool(jdk_tool(java, "jarsigner"), "-verify", str(jar))
    if rc != 0:
        raise VerifyError("Signatur ungültig:\n" + out.strip())
    if "jar is unsigned" in out:
        raise VerifyError("JAR ist nicht signiert")
    if "unsigned entries" in out:
        raise VerifyError("JAR enthält nicht signierte Einträge")
    if "jar verified" not in out:
        raise VerifyError("unerwartete jarsigner-Ausgabe:\n" + out.strip())
    rc, out = run_tool(jdk_tool(java, "keytool"), "-printcert", "-jarfile", str(jar))
    signers = {}
    for block in out.split("Signer #")[1:]:  # erstes Zertifikat je Signer = Signer-Zertifikat
        fp = re.search(r"^\s*SHA256: ([0-9A-F:]+)\s*$", block, re.M)
        owner = re.search(r"^\s*Owner: (.*)$", block, re.M)
        if fp:
            signers[fp.group(1)] = owner.group(1).strip() if owner else "?"
    if rc != 0 or not signers:
        raise VerifyError("Signer nicht ermittelbar:\n" + out.strip())
    return signers


def normalize_fp(fp: str) -> str:
    h = re.sub(r"[^0-9A-Fa-f]", "", fp).upper()
    if len(h) != 64:
        sys.exit(f"Ungültiger SHA-256-Fingerabdruck: {fp}")
    return ":".join(h[i:i + 2] for i in range(0, 64, 2))


def load_trusted() -> dict:
    try:
        return json.loads(TRUST_FILE.read_text())
    except FileNotFoundError:
        return {}


def save_trusted(trusted: dict) -> None:
    TRUST_FILE.write_text(json.dumps(trusted, indent=2, ensure_ascii=False))


def check_trust(signers: dict, trusted: dict, name: str) -> None:
    """Wie im Original: unbekannte Signer muss der Nutzer bestätigen."""
    if any(fp in trusted for fp in signers):
        return
    print(f"\n{name} ist von einem unbekannten Herausgeber signiert:")
    for fp, owner in signers.items():
        print(f"  {owner}\n  SHA-256: {fp}")
    if not sys.stdin.isatty():
        raise VerifyError("Herausgeber nicht bestätigt – mit --trust-signer <SHA-256> erlauben")
    if input("Diesem Herausgeber vertrauen? [j/N] ").strip().lower() not in ("j", "ja", "y", "yes"):
        raise VerifyError("Herausgeber abgelehnt")
    trusted.update(signers)
    save_trusted(trusted)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="hnlps://… bzw. https://… Descriptor-URL")
    ap.add_argument("--inspect", action="store_true", help="nur Descriptor speichern + anzeigen")
    ap.add_argument("--java", default=shutil.which("java") or "java")
    ap.add_argument("--dry-run", action="store_true", help="laden, aber Java nicht starten")
    ap.add_argument("--jdk", help="Java-Version wählen, z. B. 17 (via /usr/libexec/java_home)")
    ap.add_argument("--trust-signer", action="append", default=[], metavar="SHA256",
                    help="JAR-Herausgeber (Zertifikat-Fingerabdruck) dauerhaft vertrauen")
    ap.add_argument("--no-verify", action="store_true", help="JAR-Signaturen NICHT prüfen")
    a = ap.parse_args()
    if a.jdk:
        home = subprocess.check_output(["/usr/libexec/java_home", "-v", a.jdk], text=True).strip()
        a.java = str(Path(home) / "bin" / "java")

    url = to_http(a.url)
    BASE.mkdir(parents=True, exist_ok=True)
    trusted = load_trusted()
    if a.trust_signer:
        for fp in a.trust_signer:
            trusted[normalize_fp(fp)] = "per --trust-signer"
        save_trusted(trusted)
    raw = fetch(url)
    (BASE / "descriptor.json").write_bytes(raw)
    d = json.loads(raw)
    plat = java_platform(a.java)
    summarize(d, plat)
    print(f"\nDescriptor gespeichert: {BASE / 'descriptor.json'}")
    if a.inspect:
        return 0

    codebase = d["codebase"]
    cache = BASE / "cache"
    cache.mkdir(exist_ok=True)
    jars, natives, skipped_native = [], [], []
    if a.no_verify:
        print("\n⚠ JAR-Signaturen werden nicht geprüft (--no-verify)")

    for r in d.get("resources", []):
        typ = r["type"].upper()
        href = resolve(codebase, r["href"])
        if typ in ("JRE", "SETUP", "IMAGE"):
            continue  # eigenes Java statt Windows-JRE, kein Self-Update
        if typ == "NATIVELIB" and not platform_matches(r, plat):
            skipped_native.append(r["href"])
            continue
        # JARs sind plattformunabhängig – Filter nur, wenn eine Mac-Variante existiert
        target = cache / safe_name(href, r.get("hash"))
        if typ == "JAR" and a.no_verify:
            target = target.with_name("unverified_" + target.name)  # nie als geprüft weiterverwenden
        if not target.exists():
            print(f"lade {r['href']}")
            part = target.with_name(target.name + ".part")
            part.write_bytes(fetch(href))
            if typ == "JAR" and not a.no_verify:
                try:
                    check_trust(jar_signers(a.java, part), trusted, r["href"])
                except VerifyError as e:
                    part.unlink()
                    print(f"\n✗ {r['href']}: {e}", file=sys.stderr)
                    return 1
            part.replace(target)  # im Cache liegen nur geprüfte JARs
        if typ == "JAR":
            jars.append(str(target))
        elif typ == "NATIVELIB":
            out = cache / (target.name + ".d")
            if not out.exists():
                with zipfile.ZipFile(target) as z:
                    z.extractall(out)
            natives += native_dirs(out)

    if skipped_native:
        print("\n⚠ Native Bibliotheken nur für andere Systeme vorhanden (evtl. Funktionen fehlen):")
        for s in skipped_native:
            print("   ", s)

    extra = []
    if plat[0].startswith("mac"):
        # Smart Client nutzt com.apple.eawt (Vollbild-Button), seit Java 9 nicht mehr exportiert
        extra += ["--add-opens", "java.desktop/com.apple.eawt=ALL-UNNAMED"]
    cmd = [a.java, *map(expand_vars, d.get("jvmArgs", [])), *extra,
           "-cp", os.pathsep.join(jars),
           f"-Djava.library.path={os.pathsep.join(natives)}",
           d["mainClass"], *map(expand_vars, d.get("appArgs", []))]
    print("\nStart:", " ".join(cmd))
    if a.dry_run:
        return 0
    return subprocess.call(cmd, cwd=BASE)


if __name__ == "__main__":
    sys.exit(main())

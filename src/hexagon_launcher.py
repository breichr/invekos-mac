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
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = Path.home() / ".hexagon-applauncher-mac"
UA = "Java-http-client/17"  # wie der Original-Launcher (java.net.http)


def to_http(url: str) -> str:
    return url.replace("hnlps:", "https:", 1).replace("hnlp:", "http:", 1)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def resolve(codebase: str, href: str) -> str:
    return href if "://" in href else codebase + href


def platform_matches(res: dict) -> bool:
    """Gleiche Logik wie AppResource.checkPlatform() – aber für dieses System."""
    osname = platform.system().lower()            # 'darwin' / 'linux'
    osname = "mac os x" if osname == "darwin" else osname  # Java: os.name
    arch = platform.machine().lower()             # 'arm64' / 'x86_64'
    java_arch = {"arm64": "aarch64", "x86_64": "x86_64", "amd64": "amd64"}.get(arch, arch)
    if res.get("os") and not osname.startswith(res["os"].lower()):
        return False
    if res.get("arch") and res["arch"].lower() not in (java_arch, arch):
        return False
    return True


def summarize(d: dict) -> None:
    print(f"appName   : {d.get('appName')}")
    print(f"version   : {d.get('version')}")
    print(f"codebase  : {d.get('codebase')}")
    print(f"mainClass : {d.get('mainClass')}")
    print(f"jvmArgs   : {d.get('jvmArgs')}")
    print(f"appArgs   : {d.get('appArgs')}")
    print("resources :")
    for r in d.get("resources", []):
        tag = "OK " if platform_matches(r) else "-- "
        print(f"  {tag}{r.get('type'):9} os={r.get('os')!s:8} arch={r.get('arch')!s:7} {r.get('href')}")
    print("\n(OK = passt laut os/arch-Filter zu diesem Mac, -- = für anderes System)")


def safe_name(href: str) -> str:
    name = href.split("?")[0].rstrip("/").split("/")[-1] or "res"
    return hashlib.sha1(href.encode()).hexdigest()[:10] + "_" + name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="hnlps://… bzw. https://… Descriptor-URL")
    ap.add_argument("--inspect", action="store_true", help="nur Descriptor speichern + anzeigen")
    ap.add_argument("--java", default=shutil.which("java") or "java")
    ap.add_argument("--dry-run", action="store_true", help="laden, aber Java nicht starten")
    ap.add_argument("--jdk", help="Java-Version wählen, z. B. 17 (via /usr/libexec/java_home)")
    a = ap.parse_args()
    if a.jdk:
        home = subprocess.check_output(["/usr/libexec/java_home", "-v", a.jdk], text=True).strip()
        a.java = str(Path(home) / "bin" / "java")

    url = to_http(a.url)
    BASE.mkdir(parents=True, exist_ok=True)
    raw = fetch(url)
    (BASE / "descriptor.json").write_bytes(raw)
    d = json.loads(raw)
    summarize(d)
    print(f"\nDescriptor gespeichert: {BASE / 'descriptor.json'}")
    if a.inspect:
        return 0

    codebase = d["codebase"]
    cache = BASE / "cache"
    cache.mkdir(exist_ok=True)
    jars, natives, skipped_native = [], [], []

    for r in d.get("resources", []):
        typ = r["type"].upper()
        href = resolve(codebase, r["href"])
        if typ in ("JRE", "SETUP", "IMAGE"):
            continue  # eigenes Java statt Windows-JRE, kein Self-Update
        if typ == "NATIVELIB" and not platform_matches(r):
            skipped_native.append(r["href"])
            continue
        # JARs sind plattformunabhängig – Filter nur, wenn eine Mac-Variante existiert
        target = cache / safe_name(href)
        if not target.exists():
            print(f"lade {r['href']}")
            target.write_bytes(fetch(href))
        if typ == "JAR":
            jars.append(str(target))
        elif typ == "NATIVELIB":
            out = cache / (target.name + ".d")
            if not out.exists():
                with zipfile.ZipFile(target) as z:
                    z.extractall(out)
            natives.append(str(out))

    if skipped_native:
        print("\n⚠ Native Bibliotheken nur für andere Systeme vorhanden (evtl. Funktionen fehlen):")
        for s in skipped_native:
            print("   ", s)

    cmd = [a.java, *d.get("jvmArgs", []),
           "-cp", os.pathsep.join(jars),
           f"-Djava.library.path={os.pathsep.join(natives)}",
           d["mainClass"], *d.get("appArgs", [])]
    print("\nStart:", " ".join(cmd))
    if a.dry_run:
        return 0
    return subprocess.call(cmd, cwd=BASE)


if __name__ == "__main__":
    sys.exit(main())

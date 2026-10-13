"""End-to-end-Test gegen einen lokalen Fake-Server (nur Standardbibliothek + JDK)."""
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "src" / "hexagon_launcher.py"
FIXTURE = ROOT / "tests" / "fixtures" / "descriptor.json"
HELLO = 'public class Hello { public static void main(String[] a){ System.out.println("%s args=" + String.join(",", a) + " x=" + System.getProperty("x")); } }'


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(all(map(shutil.which, ["javac", "java", "keytool", "jarsigner"])), "JDK fehlt")
class LauncherE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keydir = Path(tempfile.mkdtemp())
        cls.ks = ["-keystore", str(cls.keydir / "ks"), "-storepass", "secret"]
        subprocess.run(["keytool", "-genkeypair", *cls.ks, "-keypass", "secret", "-alias", "t",
                        "-dname", "CN=Test Signer", "-keyalg", "EC", "-validity", "3650"],
                       check=True, capture_output=True)
        der = subprocess.run(["keytool", "-exportcert", *cls.ks, "-alias", "t"],
                             check=True, capture_output=True).stdout
        h = hashlib.sha256(der).hexdigest().upper()
        cls.fp = ":".join(h[i:i + 2] for i in range(0, 64, 2))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.keydir, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.srv = srv = self.tmp / "srv"
        (srv / "c").mkdir(parents=True)
        self.build_jar("HELLO")
        with zipfile.ZipFile(srv / "win.zip", "w") as z:
            z.writestr("dummy.dll", "x")
        handler = functools.partial(QuietHandler, directory=str(srv))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = self.httpd.server_address[1]
        self.descriptor = json.loads(FIXTURE.read_text().replace("{PORT}", str(port)))
        self.write_descriptor()
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"hnlp://127.0.0.1:{port}/d.json"

    def compile_hello(self, greeting):
        srv = self.srv
        (srv / "Hello.java").write_text(HELLO % greeting)
        subprocess.check_call(["javac", "-d", str(srv / "c"), str(srv / "Hello.java")])
        return (srv / "c" / "Hello.class").read_bytes()

    def build_jar(self, greeting, sign=True):
        with zipfile.ZipFile(self.srv / "app.jar", "w") as z:
            z.writestr("Hello.class", self.compile_hello(greeting))
        if sign:
            subprocess.run(["jarsigner", *self.ks, str(self.srv / "app.jar"), "t"],
                           check=True, capture_output=True)

    def rewrite_jar(self, replace=None, add=None):
        """Signiertes app.jar nachträglich verändern (Einträge ersetzen/hinzufügen)."""
        jar = self.srv / "app.jar"
        with zipfile.ZipFile(jar) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        entries.update(replace or {})
        entries.update(add or {})
        with zipfile.ZipFile(jar, "w") as z:
            for n, data in entries.items():
                z.writestr(n, data)

    def cached_jars(self):
        return sorted(p.name for p in (self.tmp / ".hexagon-applauncher-mac" / "cache").glob("*app.jar*"))

    def write_descriptor(self):
        (self.srv / "d.json").write_text(json.dumps(self.descriptor))

    def set_jar_hash(self, value):
        for r in self.descriptor["resources"]:
            if r["type"] == "jar":
                r["hash"] = value
        self.write_descriptor()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_launcher(self, *args, trust=True):
        env = dict(os.environ, HOME=str(self.tmp), no_proxy="127.0.0.1", NO_PROXY="127.0.0.1")
        for var in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME"):
            env.pop(var, None)
        if trust:
            args = ("--trust-signer", self.fp, *args)
        return subprocess.run([sys.executable, str(LAUNCHER), *args, self.url],
                              env=env, capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)  # keine interaktive Rückfrage

    def test_inspect(self):
        r = self.run_launcher("--inspect")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mainClass : Hello", r.stdout)
        self.assertTrue((self.tmp / ".hexagon-applauncher-mac" / "descriptor.json").exists())

    def test_run(self):
        r = self.run_launcher()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("HELLO args=site=demo x=1", r.stdout)
        self.assertIn("win.zip", r.stdout)  # Warnung: Windows-native übersprungen
        self.assertEqual(len(self.cached_jars()), 1)
        self.assertFalse(self.cached_jars()[0].startswith("unverified_"))

    def test_platform_natives_and_vars(self):
        out = subprocess.run(["java", "-XshowSettings:properties", "-version"],
                             capture_output=True, text=True).stderr
        props = dict(re.findall(r"^\s*(os\.name|os\.arch) = (.*?)\s*$", out, re.M))
        with zipfile.ZipFile(self.srv / "own.jar", "w") as z:
            z.writestr("libown.so", "x")
        self.descriptor["resources"] += [
            {"type": "nativelib", "href": "own.jar", "os": props["os.name"], "arch": props["os.arch"]},
            {"type": "nativelib", "href": "other.jar", "os": props["os.name"], "arch": "sparc"},
        ]
        self.descriptor["appArgs"] = ["dir=%LOCALAPPDATA%/X", "keep=%UNBEKANNT%"]
        self.write_descriptor()
        r = self.run_launcher()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"os={props['os.name'].lower()} arch={props['os.arch'].lower()}", r.stdout)
        natives = list((self.tmp / ".hexagon-applauncher-mac" / "cache").glob("*own.jar.d"))
        self.assertEqual(len(natives), 1)
        self.assertIn(f"-Djava.library.path={natives[0]} ", r.stdout)
        self.assertIn("other.jar", r.stdout)  # andere Architektur -> übersprungen
        appdata = self.tmp / ("Library/Application Support" if sys.platform == "darwin" else ".local/share")
        self.assertIn(f"HELLO args=dir={appdata}/X,keep=%UNBEKANNT%", r.stdout)

    def test_untrusted_signer(self):
        r = self.run_launcher(trust=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn(self.fp, r.stdout)
        self.assertIn("CN=Test Signer", r.stdout)
        self.assertIn("--trust-signer", r.stderr)
        self.assertEqual(self.cached_jars(), [])  # nichts Ungeprüftes im Cache
        self.assertEqual(self.run_launcher().returncode, 0)
        self.set_jar_hash("v2")  # erneuter Download, Vertrauen ist gespeichert
        r = self.run_launcher(trust=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("lade app.jar", r.stdout)

    def test_tampered_jar(self):
        self.rewrite_jar(replace={"Hello.class": self.compile_hello("BOESE")})
        r = self.run_launcher()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Signatur ungültig", r.stderr)
        self.assertNotIn("BOESE", r.stdout)
        self.assertEqual(self.cached_jars(), [])

    def test_unsigned_entry(self):
        self.rewrite_jar(add={"Extra.class": b"x"})
        r = self.run_launcher()
        self.assertEqual(r.returncode, 1)
        self.assertIn("nicht signierte Einträge", r.stderr)

    def test_unsigned_jar(self):
        self.build_jar("HELLO", sign=False)
        r = self.run_launcher()
        self.assertEqual(r.returncode, 1)
        self.assertIn("nicht signiert", r.stderr)
        r = self.run_launcher("--no-verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("HELLO args=", r.stdout)
        self.assertTrue(self.cached_jars()[0].startswith("unverified_"))
        r = self.run_launcher()  # ungeprüfte Kopie wird ohne --no-verify nicht verwendet
        self.assertEqual(r.returncode, 1)

    def test_hash_cache(self):
        self.set_jar_hash("v1")
        self.assertIn("HELLO args=", self.run_launcher().stdout)
        self.build_jar("NEU")  # neue Version unter gleicher URL
        r = self.run_launcher()
        self.assertIn("HELLO args=", r.stdout)  # gleicher Hash -> Cache
        self.assertNotIn("lade app.jar", r.stdout)
        self.set_jar_hash("v2")
        r = self.run_launcher()
        self.assertIn("lade app.jar", r.stdout)
        self.assertIn("NEU args=", r.stdout)


if __name__ == "__main__":
    unittest.main()

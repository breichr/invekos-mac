"""End-to-end-Test gegen einen lokalen Fake-Server (nur Standardbibliothek + JDK)."""
import functools
import http.server
import json
import os
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


@unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "JDK fehlt")
class LauncherE2E(unittest.TestCase):
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

    def build_jar(self, greeting):
        srv = self.srv
        (srv / "Hello.java").write_text(HELLO % greeting)
        subprocess.check_call(["javac", "-d", str(srv / "c"), str(srv / "Hello.java")])
        with zipfile.ZipFile(srv / "app.jar", "w") as z:
            z.write(srv / "c" / "Hello.class", "Hello.class")

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

    def run_launcher(self, *args):
        env = dict(os.environ, HOME=str(self.tmp), no_proxy="127.0.0.1", NO_PROXY="127.0.0.1")
        return subprocess.run([sys.executable, str(LAUNCHER), *args, self.url],
                              env=env, capture_output=True, text=True, timeout=120)

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

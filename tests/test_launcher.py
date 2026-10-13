"""End-to-end-Test gegen einen lokalen Fake-Server (nur Standardbibliothek + JDK)."""
import functools
import http.server
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
HELLO = 'public class Hello { public static void main(String[] a){ System.out.println("HELLO args=" + String.join(",", a) + " x=" + System.getProperty("x")); } }'


@unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "JDK fehlt")
class LauncherE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        srv = self.tmp / "srv"
        (srv / "c").mkdir(parents=True)
        (srv / "Hello.java").write_text(HELLO)
        subprocess.check_call(["javac", "-d", str(srv / "c"), str(srv / "Hello.java")])
        with zipfile.ZipFile(srv / "app.jar", "w") as z:
            z.write(srv / "c" / "Hello.class", "Hello.class")
        with zipfile.ZipFile(srv / "win.zip", "w") as z:
            z.writestr("dummy.dll", "x")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(srv))
        handler.log_message = lambda *a, **k: None
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = self.httpd.server_address[1]
        (srv / "d.json").write_text(FIXTURE.read_text().replace("{PORT}", str(port)))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"hnlp://127.0.0.1:{port}/d.json"

    def tearDown(self):
        self.httpd.shutdown()
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


if __name__ == "__main__":
    unittest.main()

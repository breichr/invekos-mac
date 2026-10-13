#!/usr/bin/env python3
"""Extrahiert MSI und CAB aus einem Advanced-Installer-SFX (z. B. AMA applauncher.exe).

Advanced Installer verschleiert die ersten 0x200 Bytes jeder eingebetteten Datei
mit XOR 0xFF. Wir suchen die verschleierten Header von MSI (OLE) und CAB.

  python3 -I carve_ai_sfx.py applauncher.exe ausgabe_ordner/
"""
import struct
import sys
from pathlib import Path

MSI = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
CAB = b"MSCF\0\0\0\0"
XLEN = 0x200


def unxor(b: bytes) -> bytes:
    b = bytearray(b)
    for i in range(min(XLEN, len(b))):
        b[i] ^= 0xFF
    return bytes(b)


def main(src: str, out: str) -> None:
    d = Path(src).read_bytes()
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    xm = d.find(bytes(x ^ 0xFF for x in MSI))
    xc = d.find(bytes(x ^ 0xFF for x in CAB))
    if xc < 0:
        sys.exit("CAB nicht gefunden – anderes Installer-Format?")
    cab_head = unxor(d[xc:xc + XLEN])
    cab_size = struct.unpack_from("<I", cab_head, 8)[0]  # cbCabinet
    (o / "AppLauncher1.cab").write_bytes(unxor(d[xc:xc + cab_size]))
    print(f"CAB  @ {xc}  {cab_size} Bytes")
    if 0 <= xm < xc:
        (o / "AppLauncher.msi").write_bytes(unxor(d[xm:xc]))
        print(f"MSI  @ {xm}  {xc - xm} Bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

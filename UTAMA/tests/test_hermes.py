"""
Uji ekstraksi string dari Hermes bytecode.

Membangun berkas Hermes minimal yang valid dengan string diketahui, lalu
memastikan:
  1. extract_hermes_strings() memotong tiap string tepat pada batasnya.
  2. analyze_artifact() mengekstrak URL secara BERSIH dari bundle Hermes —
     tidak tercampur string tetangga yang berjejalan di sebelahnya.

Kasus uji dirancang meniru masalah nyata: pada Hermes, string disimpan
berjejalan tanpa pemisah, sehingga pemindaian byte mentah akan menangkap
"https://api.example.com/v1/login" beserta ekor string berikutnya. Dengan
pembacaan tabel string, batas itu terjaga.

Jalankan:
    python3 tests/test_hermes.py
"""

import struct
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import apk_analyzer  # noqa: E402

# String uji, sengaja disimpan bersebelahan tanpa pemisah pada storage.
STRINGS = [
    "https://api.example.com/v1/login",
    "GARBAGE_TOKEN_shouldNotBleedIntoUrl",
    "wss://ws.example.com/live",
    "/apimobile/tagihan/checkout",
    "AKIAIOSFODNN7EXAMPLE",
    "https://reactnavigation.org/docs/getting-started",
]


def build_min_hermes(strings) -> bytes:
    """Bangun berkas Hermes bytecode minimal (functionCount=0, tanpa overflow)."""
    encoded = [s.encode("utf-8") for s in strings]
    storage = b"".join(encoded)

    # Tabel string kecil: tiap entri u32 = isUTF16(1) | offset(23) | length(8).
    small_table = b""
    cursor = 0
    for b in encoded:
        assert len(b) < 0xFF, "string uji harus < 255 byte (tanpa jalur overflow)"
        entry = (cursor << 1) | (len(b) << 24)
        small_table += struct.pack("<I", entry)
        cursor += len(b)

    header = bytearray(apk_analyzer.HERMES_HEADER_SIZE)
    struct.pack_into("<Q", header, 0, apk_analyzer.HERMES_MAGIC)
    struct.pack_into("<I", header, 8, 96)          # version
    struct.pack_into("<I", header, 40, 0)          # functionCount
    struct.pack_into("<I", header, 44, 0)          # stringKindCount
    struct.pack_into("<I", header, 48, 0)          # identifierCount
    struct.pack_into("<I", header, 52, len(encoded))  # stringCount
    struct.pack_into("<I", header, 56, 0)          # overflowStringCount
    struct.pack_into("<I", header, 60, len(storage))  # stringStorageSize

    file_length = apk_analyzer.HERMES_HEADER_SIZE + len(small_table) + len(storage)
    struct.pack_into("<I", header, 32, file_length)  # fileLength (informatif)
    return bytes(header) + small_table + storage


def analyze_bytes(data: bytes) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="hermes_")) / "index.android.bundle"
    tmp.write_bytes(data)
    result = apk_analyzer.analyze_artifact(tmp)
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    return result


def main() -> int:
    print("=" * 68)
    print("UJI EKSTRAKSI STRING HERMES BYTECODE")
    print("=" * 68)

    lulus = True

    def cek(nama: str, syarat: bool, detail: str = "") -> None:
        nonlocal lulus
        if not syarat:
            lulus = False
        print(f"    [{'OK ' if syarat else 'GAGAL'}] {nama}{(': ' + detail) if detail else ''}")

    blob = build_min_hermes(STRINGS)

    print("\n1. extract_hermes_strings memotong tepat pada batas")
    extracted = apk_analyzer.extract_hermes_strings(blob)
    cek("dikenali sebagai Hermes", extracted is not None)
    cek("jumlah string sesuai", extracted == STRINGS, f"{extracted}")

    print("\n2. bukan Hermes -> None (fallback ke byte mentah)")
    cek("berkas biasa ditolak", apk_analyzer.extract_hermes_strings(b"bukan hermes sama sekali") is None)

    print("\n3. analyze_artifact mengekstrak URL BERSIH dari bundle Hermes")
    result = analyze_bytes(blob)
    cek("terdeteksi Hermes", result["is_hermes"])
    cek("URL bersih ada", "https://api.example.com/v1/login" in result["urls"],
        str(result["urls"]))
    bleed = any("GARBAGE" in u for u in result["urls"])
    cek("URL tidak tercampur string tetangga", not bleed)
    cek("websocket bersih", "wss://ws.example.com/live" in result["websockets"])
    cek("endpoint /apimobile terdeteksi", "/apimobile/tagihan/checkout" in result["api_paths"])
    cek("kredensial AWS tetap terdeteksi",
        any("AWS" in t for t in result["api_keys_and_tokens"]))

    print("\n4. app_endpoints memisahkan API aplikasi dari URL dokumentasi library")
    cek("endpoint aplikasi masuk app_endpoints",
        "https://api.example.com/v1/login" in result["app_endpoints"])
    cek("URL dokumentasi library dikecualikan",
        "https://reactnavigation.org/docs/getting-started" not in result["app_endpoints"])

    print()
    if lulus:
        print("[+] LULUS: parsing Hermes memotong string dengan benar.")
        return 0
    print("[!] GAGAL.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

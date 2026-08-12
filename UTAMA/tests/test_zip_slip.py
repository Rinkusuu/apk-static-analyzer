"""
Uji keamanan: kerentanan Zip Slip (path traversal) pada extract_apk().

Berkas APK adalah arsip ZIP. Setiap entri di dalamnya memiliki nama jalur, dan
nama jalur itu boleh mengandung "../" yang berarti naik satu direktori. Sebuah
APK jahat dapat memuat entri seperti "../../berkas" sehingga, ketika diekstrak
tanpa pemeriksaan, berkasnya tertulis DI LUAR direktori tujuan — menimpa berkas
lain di sistem. Inilah kerentanan Zip Slip.

Uji ini:
  1. Membuat APK jahat berisi satu entri dengan jalur "../".
  2. Menjalankan extract_apk() ke sebuah direktori tujuan.
  3. Memeriksa apakah berkas berhasil menyelinap keluar dari direktori tujuan.

Seluruh proses berlangsung di dalam direktori sementara, sehingga tidak ada
berkas asli mana pun yang berisiko tertimpa.

Perilaku yang benar setelah perbaikan: extract_apk() menolak APK semacam ini
dengan memunculkan galat, dan tidak ada berkas yang tertulis di luar tujuan.

Jalankan:
    python3 tests/test_zip_slip.py
"""

import sys
import tempfile
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import apk_analyzer  # noqa: E402

# Nama entri jahat: naik dua tingkat lalu tulis berkas penanda.
PAYLOAD_NAME = "../../DISUSUPI.txt"
PAYLOAD_BODY = b"berkas ini seharusnya tidak pernah tertulis di sini"


def build_malicious_apk(apk_path: Path) -> None:
    """Membuat APK berisi satu entri normal dan satu entri jahat ber-'../'."""
    with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as apk:
        # Entri wajar, agar arsip tampak seperti APK biasa.
        apk.writestr("AndroidManifest.xml", b"<manifest/>")
        # Entri jahat. writestr menulis nama apa adanya, termasuk '../'.
        apk.writestr(PAYLOAD_NAME, PAYLOAD_BODY)


def main() -> int:
    tmp_root = Path(tempfile.mkdtemp(prefix="zipslip_"))
    apk_path = tmp_root / "jahat.apk"
    # Direktori tujuan diletakkan beberapa tingkat di dalam, agar '../../'
    # mengarah ke suatu tempat yang masih di dalam tmp_root (aman), namun tetap
    # DI LUAR direktori tujuan ekstraksi.
    dest_dir = tmp_root / "area" / "ekstraksi" / "tujuan"
    escaped_marker = tmp_root / "area" / "DISUSUPI.txt"

    build_malicious_apk(apk_path)

    print("=" * 68)
    print("UJI KEAMANAN: KERENTANAN ZIP SLIP PADA extract_apk()")
    print("=" * 68)
    print(f"\nEntri jahat di dalam APK : {PAYLOAD_NAME}")
    print(f"Direktori tujuan         : {dest_dir}")
    print(f"Sasaran penyelinapan     : {escaped_marker}")

    blocked_by_error = False
    try:
        apk_analyzer.extract_apk(apk_path, dest_dir)
    except Exception as exc:  # noqa: BLE001
        blocked_by_error = True
        print(f"\n[i] extract_apk menolak dengan galat: {type(exc).__name__}: {exc}")

    escaped = escaped_marker.exists()

    print("\nHasil:")
    if escaped:
        print("    [!] RENTAN — berkas berhasil menyelinap keluar direktori tujuan.")
        print("        Sebuah APK jahat dapat menimpa berkas di luar area ekstraksi.")
        verdict = 1
    elif blocked_by_error:
        print("    [+] AMAN — ekstraksi ditolak, tidak ada berkas yang menyelinap keluar.")
        verdict = 0
    else:
        print("    [+] AMAN — tidak ada berkas yang menyelinap keluar direktori tujuan.")
        verdict = 0

    # Bersihkan direktori sementara.
    import shutil

    shutil.rmtree(tmp_root, ignore_errors=True)

    print()
    return verdict


if __name__ == "__main__":
    sys.exit(main())

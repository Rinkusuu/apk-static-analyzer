"""
Uji model skoring risiko: severity + breadth.

Menguji tiga cacat model lama sekaligus membuktikan model baru menanganinya.
Setiap skenario dibuat sebagai artefak kecil, lalu dijalankan lewat
analyze_artifact() yang sesungguhnya.

Model baru:
    severity = bobot temuan paling berbahaya (0-100)
    breadth  = min(jumlah_temuan_unik - 1, 5) * 4   (bonus terbatas, maks +20)
    skor     = severity + breadth
    Ambang: >=90 CRITICAL, >=70 HIGH, >=50 MEDIUM, selain itu LOW

Jalankan:
    python3 tests/test_scoring.py
"""

import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import apk_analyzer  # noqa: E402


def score(content: bytes) -> dict:
    """Tulis konten ke berkas sementara, jalankan analyzer, kembalikan hasilnya."""
    tmp = Path(tempfile.mkdtemp(prefix="skor_")) / "artifact.bundle"
    tmp.write_bytes(content)
    result = apk_analyzer.analyze_artifact(tmp)
    import shutil

    shutil.rmtree(tmp.parent, ignore_errors=True)
    return result


AWS = b'"AKIAIOSFODNN7EXAMPLE"'
JWT = (
    b'"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
    b".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkRlbW8ifQ"
    b'.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXkw"'
)
# Blok sertifikat: bobot 50 (severity rendah). Empat berkas berbeda.
CERTS = b"\n".join(
    b"-----BEGIN CERTIFICATE-----\nMIIB" + str(i).encode() + b"fake\n-----END CERTIFICATE-----"
    for i in range(4)
)


def main() -> int:
    print("=" * 68)
    print("UJI MODEL SKORING RISIKO (severity + breadth)")
    print("=" * 68)

    lulus = True

    def cek(nama: str, syarat: bool, detail: str) -> None:
        nonlocal lulus
        status = "OK " if syarat else "GAGAL"
        if not syarat:
            lulus = False
        print(f"    [{status}] {nama}: {detail}")

    # ── Cacat 1: duplikat menggelembungkan skor ────────────────────────────
    print("\n1. Duplikat tidak boleh menggelembungkan skor")
    satu = score(AWS)
    banyak = score(b"\n".join([AWS] * 50))  # kunci AWS SAMA, 50 kali
    print(f"    1x kunci AWS  -> skor {satu['risk_score']}, temuan {satu['summary']['total_tokens_found']}")
    print(f"    50x kunci AWS -> skor {banyak['risk_score']}, temuan {banyak['summary']['total_tokens_found']}")
    cek("skor identik", satu["risk_score"] == banyak["risk_score"],
        f"{satu['risk_score']} == {banyak['risk_score']}")
    cek("temuan unik = 1", banyak["summary"]["total_tokens_found"] == 1,
        f"{banyak['summary']['total_tokens_found']}")

    # ── Cacat 2 & 3: satu kunci AWS lebih gawat dari empat sertifikat ───────
    print("\n2. Satu kunci berat > banyak temuan ringan")
    aws = score(AWS)
    empat_cert = score(CERTS)
    print(f"    1 kunci AWS    -> skor {aws['risk_score']}, level {aws['risk_level']}")
    print(f"    4 sertifikat   -> skor {empat_cert['risk_score']}, level {empat_cert['risk_level']}")
    cek("AWS = CRITICAL", aws["risk_level"] == "CRITICAL", aws["risk_level"])
    cek("4 sertifikat bukan CRITICAL", empat_cert["risk_level"] != "CRITICAL",
        empat_cert["risk_level"])
    cek("AWS lebih tinggi dari 4 sertifikat", aws["risk_score"] > empat_cert["risk_score"],
        f"{aws['risk_score']} > {empat_cert['risk_score']}")

    # ── Batas atas: skor tidak boleh lari liar ─────────────────────────────
    print("\n3. Skor terikat (breadth bonus terbatas)")
    campur = score(b"\n".join([AWS, JWT, CERTS]))
    print(f"    campuran banyak jenis -> skor {campur['risk_score']}")
    cek("skor <= 120", campur["risk_score"] <= 120, f"{campur['risk_score']}")

    # ── Tidak ada temuan -> LOW ────────────────────────────────────────────
    print("\n4. Artefak bersih -> LOW")
    bersih = score(b'{"greeting":"halo dunia","count":42}')
    print(f"    artefak tanpa kredensial -> skor {bersih['risk_score']}, level {bersih['risk_level']}")
    cek("level LOW", bersih["risk_level"] == "LOW", bersih["risk_level"])

    print()
    if lulus:
        print("[+] LULUS: model skoring berperilaku sesuai rancangan.")
        return 0
    print("[!] GAGAL: ada perilaku skoring yang tidak sesuai.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

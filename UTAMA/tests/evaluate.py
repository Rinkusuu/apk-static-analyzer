"""
Harness pengujian apk_analyzer terhadap APK sampel dengan ground truth diketahui.

Menjalankan pipeline analyzer yang sesungguhnya (extract -> find_artifacts ->
analyze_artifact) pada tests/sample.apk, lalu membandingkan hasilnya dengan
tests/expected.json untuk menghitung:

  - True Positive  : rahasia yang ditanam dan berhasil ditemukan
  - False Negative : rahasia yang ditanam tetapi terlewat
  - False Positive : nilai yang dilaporkan sebagai kredensial padahal bukan
  - Precision / Recall

Hasilnya dicetak ke layar dan disimpan ke tests/hasil_terkini.json.

Berkas tests/baseline_report.json memuat pengukuran kondisi awal proyek dan
sengaja dibekukan — berkas itu tidak pernah ditimpa, sebab ia menjadi angka
pembanding tetap untuk seluruh perbaikan berikutnya.

Jalankan:
    python3 tests/make_sample_apk.py     # sekali, untuk membuat sampel
    python3 tests/evaluate.py
"""

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

import apk_analyzer  # noqa: E402

APK_PATH = BASE_DIR / "sample.apk"
EXPECTED_PATH = BASE_DIR / "expected.json"
BASELINE_PATH = BASE_DIR / "baseline_report.json"
REPORT_PATH = BASE_DIR / "hasil_terkini.json"

# Kategori hasil yang diperlakukan sebagai "klaim kredensial" oleh analyzer.
# Hanya kategori inilah yang dihitung false positive-nya, sebab kategori lain
# (urls, keywords, dsb.) memang bersifat inventarisasi, bukan tuduhan.
CREDENTIAL_CATEGORIES = ("api_keys_and_tokens", "db_connections")


# ==============================================================================
# 1. MENJALANKAN ANALYZER
# ==============================================================================
def run_analyzer(apk_path: Path) -> dict:
    """Jalankan pipeline analyzer, gabungkan temuan seluruh artefak."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="apk_test_"))
    try:
        extract_dir = tmp_dir / "extracted"
        apk_analyzer.extract_apk(apk_path, extract_dir)
        artifacts = apk_analyzer.find_artifacts(extract_dir)

        merged: dict = {}
        per_artifact = []
        total_risk = 0
        for artifact in artifacts:
            result = apk_analyzer.analyze_artifact(artifact)
            if "error" in result:
                continue
            per_artifact.append(
                {
                    "file": str(artifact.relative_to(extract_dir)),
                    "risk_level": result["risk_level"],
                    "risk_score": result["risk_score"],
                }
            )
            total_risk += result["risk_score"]
            for key, value in result.items():
                if isinstance(value, list):
                    merged.setdefault(key, set()).update(value)

        return {
            "artifact_count": len(artifacts),
            "per_artifact": per_artifact,
            "total_risk_score": total_risk,
            "findings": {k: sorted(v) for k, v in merged.items()},
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==============================================================================
# 2. BOBOT RISIKO (dibaca langsung dari sumber analyzer agar tidak melenceng)
# ==============================================================================
def load_detector_weights() -> dict:
    """Ambil pasangan nama-detektor -> bobot dari token_patterns di analyzer."""
    source = (PROJECT_DIR / "apk_analyzer.py").read_text(encoding="utf-8")
    # Entri detektor boleh ditulis satu baris maupun terpecah beberapa baris,
    # karena itu pencocokan dilakukan lintas baris (re.S).
    return {
        name: int(weight)
        for name, weight in re.findall(
            r'"([^"]+)":\s*\(\s*rb.*?,\s*(\d+),?\s*\)', source, re.S
        )
    }


def split_detector_entry(entry: str) -> tuple:
    """Pecah '[Nama Detektor] nilai' menjadi (nama, nilai)."""
    match = re.match(r"^\[([^\]]+)\]\s(.*)$", entry, re.S)
    return (match.group(1), match.group(2)) if match else (None, entry)


# ==============================================================================
# 3. EVALUASI
# ==============================================================================
def evaluate(run: dict, expected: dict) -> dict:
    findings = run["findings"]
    weights = load_detector_weights()

    # ---- True positive / false negative -------------------------------------
    detected, missed = [], []
    for item in expected["planted"]:
        category = item["category"]
        found_values = findings.get(category, [])
        hit = any(item["value"] in found for found in found_values)
        (detected if hit else missed).append(item)

    planted_values = {item["value"] for item in expected["planted"]}

    # ---- False positive -----------------------------------------------------
    false_positives = []
    for category in CREDENTIAL_CATEGORIES:
        for entry in findings.get(category, []):
            detector, value = split_detector_entry(entry)
            if any(planted in value for planted in planted_values):
                continue
            false_positives.append(
                {
                    "detector": detector,
                    "value": value[:120],
                    "risk_weight": weights.get(detector, 0),
                }
            )

    fp_by_detector: dict = {}
    for fp in false_positives:
        bucket = fp_by_detector.setdefault(
            fp["detector"], {"count": 0, "risk_weight": fp["risk_weight"], "risk_contributed": 0}
        )
        bucket["count"] += 1
        bucket["risk_contributed"] += fp["risk_weight"]

    tp, fn, fp_count = len(detected), len(missed), len(false_positives)
    precision = tp / (tp + fp_count) if (tp + fp_count) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    fp_risk = sum(b["risk_contributed"] for b in fp_by_detector.values())
    total_risk = run["total_risk_score"]

    return {
        "true_positive": tp,
        "false_negative": fn,
        "false_positive": fp_count,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "missed": missed,
        "false_positive_by_detector": fp_by_detector,
        "false_positive_examples": false_positives[:5],
        "risk": {
            "total_risk_score": total_risk,
            "risk_from_false_positives": fp_risk,
            "false_positive_share": round(fp_risk / total_risk, 4) if total_risk else 0.0,
            "per_artifact": run["per_artifact"],
        },
        "inventory": {
            key: len(findings.get(key, []))
            for key in ("urls", "websockets", "ip_addresses", "api_paths", "android_components")
        },
    }


# ==============================================================================
# 4. PELAPORAN
# ==============================================================================
def print_report(report: dict) -> None:
    line = "=" * 68
    print(line)
    print("HASIL PENGUJIAN APK_ANALYZER TERHADAP SAMPEL BER-GROUND-TRUTH")
    print(line)

    print(f"\nTrue Positive  : {report['true_positive']}")
    print(f"False Negative : {report['false_negative']}")
    print(f"False Positive : {report['false_positive']}")
    print(f"Precision      : {report['precision']:.2%}")
    print(f"Recall         : {report['recall']:.2%}")

    if report["missed"]:
        print("\n[!] Rahasia yang TERLEWAT (false negative):")
        for item in report["missed"]:
            label = item["detector"] or item["category"]
            print(f"    - {label}: {item['value'][:70]}")

    if report["false_positive_by_detector"]:
        print("\n[!] Sumber false positive:")
        print(f"    {'Detektor':<24}{'Jumlah':>8}{'Bobot':>8}{'Kontribusi Risiko':>20}")
        for detector, data in sorted(
            report["false_positive_by_detector"].items(),
            key=lambda x: x[1]["risk_contributed"],
            reverse=True,
        ):
            print(
                f"    {str(detector):<24}{data['count']:>8}"
                f"{data['risk_weight']:>8}{data['risk_contributed']:>20}"
            )

    risk = report["risk"]
    print("\nSkor risiko:")
    print(f"    Total                      : {risk['total_risk_score']}")
    print(f"    Berasal dari false positive: {risk['risk_from_false_positives']}"
          f" ({risk['false_positive_share']:.1%})")
    for artifact in risk["per_artifact"]:
        print(f"    - {artifact['file']:<40}{artifact['risk_level']:>10}"
              f"{artifact['risk_score']:>8}")

    print("\nInventarisasi (bukan tuduhan, tidak dihitung sebagai FP):")
    for key, count in report["inventory"].items():
        print(f"    {key:<22}{count:>6}")
    print()


def print_comparison(report: dict) -> None:
    """Bandingkan hasil sekarang dengan kondisi awal proyek."""
    if not BASELINE_PATH.exists():
        return
    base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    # Hanya metrik yang definisinya sama lintas versi yang layak dibandingkan
    # langsung. Precision dan recall memenuhi syarat itu. Skor risiko TIDAK,
    # sebab skalanya berubah saat model skoring diperbarui (lama: tak terbatas;
    # baru: terikat 0-120), sehingga ditampilkan terpisah tanpa selisih.
    baris = [
        ("True Positive", base["true_positive"], report["true_positive"], "{:d}"),
        ("False Negative", base["false_negative"], report["false_negative"], "{:d}"),
        ("False Positive", base["false_positive"], report["false_positive"], "{:d}"),
        ("Precision", base["precision"], report["precision"], "{:.2%}"),
        ("Recall", base["recall"], report["recall"], "{:.2%}"),
    ]

    print("Perbandingan terhadap kondisi awal proyek:")
    print(f"    {'Metrik':<18}{'Awal':>12}{'Sekarang':>12}{'Perubahan':>14}")
    for nama, awal, kini, fmt in baris:
        if awal == kini:
            delta = "tetap"
        elif isinstance(awal, float):
            delta = f"{(kini - awal) * 100:+.2f} poin"
        else:
            delta = f"{kini - awal:+d}"
        print(f"    {nama:<18}{fmt.format(awal):>12}{fmt.format(kini):>12}{delta:>14}")

    skor_awal = base["risk"]["total_risk_score"]
    skor_kini = report["risk"]["total_risk_score"]
    print(f"\n    Skor risiko (skala berbeda, tidak dibandingkan langsung):")
    print(f"        kondisi awal (model lama, tak terbatas) : {skor_awal}")
    print(f"        sekarang    (model baru, terikat 0-120) : {skor_kini}")
    print()


def main() -> int:
    if not APK_PATH.exists() or not EXPECTED_PATH.exists():
        print("[!] Sampel belum dibuat. Jalankan dulu:")
        print("    python3 tests/make_sample_apk.py")
        return 2

    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    run = run_analyzer(APK_PATH)
    report = evaluate(run, expected)

    print_report(report)
    print_comparison(report)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Hasil disimpan di: {REPORT_PATH}")

    # Gagal hanya bila ada rahasia yang terlewat. Precision buruk sengaja
    # dibiarkan lolos agar terekam sebagai angka baseline "sebelum perbaikan".
    if report["false_negative"]:
        print("[!] GAGAL: masih ada rahasia yang tidak terdeteksi.")
        return 1
    print("[+] LULUS: seluruh rahasia yang ditanam berhasil terdeteksi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
============================================================================
 SALINAN BERANOTASI — apk_cli.py
============================================================================

Antarmuka baris perintah BERMENU untuk apk_analyzer. Kode produksinya
(`UTAMA/apk_cli.py`) bersih tanpa komentar; berkas ini rujukan beranotasi.

Menjalankan: python3 apk_cli.py   (mode interaktif bermenu)
Bandingkan  : python3 apk_analyzer.py <target.apk>   (mode langsung sekali jalan)

  ISTILAH — CLI (Command Line Interface) : antarmuka berbasis teks di terminal.
  ISTILAH — ANSI escape code : urutan seperti "\033[38;5;37m" yang memberi
     warna/format pada teks terminal. "\033[0m" mengembalikan ke normal.
  ISTILAH — isatty : True bila keluaran mengarah ke terminal sungguhan (bukan
     pipa/berkas). Dipakai agar warna hanya dinyalakan saat relevan; saat
     keluaran dialihkan ke berkas, warna dimatikan agar tidak mengotori teks.

Struktur: apk_cli hanya LAPISAN TAMPILAN. Seluruh analisis tetap dikerjakan
fungsi publik apk_analyzer — terutama analyze_apk(), satu pipeline yang sama
yang juga dipakai mode baris perintah, sehingga alur analisis tidak ditulis
dua kali.
============================================================================
"""

import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import apk_analyzer

BASE_DIR = Path(__file__).resolve().parent

# Nyalakan warna HANYA bila keluaran ke terminal dan variabel NO_COLOR tak diset.
# (NO_COLOR adalah konvensi lintas-perkakas untuk mematikan warna.)
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str) -> str:
    # Kembalikan kode warna hanya bila warna aktif; jika tidak, string kosong.
    return code if USE_COLOR else ""


# Palet ANSI 256-warna, senada dengan tema laporan (teal + semantik risiko).
RESET = _c("\033[0m")
BOLD = _c("\033[1m")
DIM = _c("\033[2m")
TEAL = _c("\033[38;5;37m")
TEAL_D = _c("\033[38;5;30m")
GREY = _c("\033[38;5;245m")
GREEN = _c("\033[38;5;71m")
YELLOW = _c("\033[38;5;179m")
ORANGE = _c("\033[38;5;173m")
RED = _c("\033[38;5;167m")

# Warna badge sesuai level risiko.
RISK_COLOR = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": ORANGE, "CRITICAL": RED}


def clear() -> None:
    # Bersihkan layar (hanya bila terminal). \033[2J hapus layar, \033[H ke pojok.
    if USE_COLOR:
        print("\033[2J\033[H", end="")


def banner() -> None:
    # Header hias memakai karakter box-drawing (═ ║ ╔ ╗ ╚ ╝).
    line = "═" * 54
    print(f"{TEAL}╔{line}╗{RESET}")
    print(f"{TEAL}║{RESET}{BOLD}   APK STATIC ANALYZER{RESET}{' ' * 32}{TEAL}║{RESET}")
    print(f"{TEAL}║{RESET}{GREY}   Analisis statis · endpoint & kredensial{RESET}{' ' * 12}{TEAL}║{RESET}")
    print(f"{TEAL}╚{line}╝{RESET}")


def rule(label: str = "") -> None:
    # Garis pemisah seksi, dengan label opsional di kiri.
    if label:
        pad = "─" * max(2, 52 - len(label))
        print(f"{TEAL_D}── {RESET}{BOLD}{label}{RESET} {TEAL_D}{pad}{RESET}")
    else:
        print(f"{TEAL_D}{'─' * 56}{RESET}")


def badge(level: str) -> str:
    # Label risiko berwarna, mis. [ CRITICAL ] merah.
    color = RISK_COLOR.get(level, GREY)
    return f"{color}{BOLD} {level:^8} {RESET}"


def ask(prompt: str) -> Optional[str]:
    # Baca input. EOF (Ctrl-D atau pipa habis) dikembalikan sebagai None, BUKAN
    # sebagai "0". Dahulu EOF dipalsukan menjadi "0" agar menu utama langsung
    # keluar, tetapi fungsi ini juga dipakai pada prompt lain — di prompt path
    # APK, "0" bukan nomor yang sah sehingga dianggap nama berkas dan muncul
    # pesan "Berkas tidak ditemukan: .../0". Dengan None, tiap pemanggil
    # memutuskan sendiri arti "tidak ada masukan".
    try:
        return input(f"{TEAL}▸{RESET} {prompt}").strip()
    except EOFError:
        print()
        return None


def pause() -> None:
    try:
        input(f"\n{DIM}  tekan Enter untuk kembali…{RESET}")
    except EOFError:
        pass


def menu() -> Optional[str]:
    # Tampilkan menu dan kembalikan pilihan pengguna.
    print()
    rule("MENU")
    print(f"  {BOLD}{TEAL}1{RESET}  Analisis sebuah APK")
    print(f"  {BOLD}{TEAL}2{RESET}  Riwayat hasil analisis")
    print(f"  {BOLD}{TEAL}3{RESET}  Jalankan pengujian")
    print(f"  {BOLD}{TEAL}0{RESET}  Keluar")
    print()
    return ask("Pilih menu: ")


def render_summary(final_result: dict, output_json: Path) -> None:
    # Tabel ringkas per artefak (risiko, jumlah endpoint aplikasi, jumlah token),
    # lalu daftar endpoint aplikasi teratas.
    artifacts = final_result["artifacts"]
    print()
    rule("HASIL")
    print(f"  Target   : {BOLD}{final_result['metadata']['target_apk']}{RESET}")
    print(f"  Artefak  : {len(artifacts)}")
    print(f"  Tersimpan: {DIM}{output_json}{RESET}")
    print()
    print(f"  {GREY}{'ARTEFAK':<34}{'RISIKO':^10}{'ENDPOINT':>9}{'TOKEN':>7}{RESET}")
    for name, data in artifacts.items():
        if "error" in data:
            continue
        s = data["summary"]
        short = name if len(name) <= 33 else "…" + name[-32:]
        print(f"  {short:<34}{badge(data['risk_level'])}"
              f"{s.get('total_app_endpoints', 0):>9}{s['total_tokens_found']:>7}")

    # Baris total menjawab pertanyaan yang tidak terjawab oleh tabel per
    # artefak: berapa banyak endpoint dan kredensial pada SELURUH APK. Baris
    # keterangan di bawahnya menjelaskan mengapa risiko bisa LOW meski daftar
    # endpoint panjang — skor menilai kebocoran kredensial, sedangkan endpoint
    # bersifat inventarisasi dan sengaja tidak menaikkan skor.
    scanned = [data for data in artifacts.values() if "error" not in data]
    total_endpoints = sum(d["summary"].get("total_app_endpoints", 0) for d in scanned)
    total_tokens = sum(d["summary"]["total_tokens_found"] for d in scanned)
    print()
    print(f"  {BOLD}Total{RESET}    : {total_endpoints} endpoint aplikasi"
          f" · {total_tokens} kredensial")
    print(f"  {DIM}Skor risiko menilai kebocoran kredensial; daftar endpoint"
          f" bersifat inventaris{RESET}")
    print(f"  {DIM}dan tidak menaikkan skor.{RESET}")

    # Seluruh artefak yang memuat endpoint ditampilkan, terbanyak lebih dulu —
    # bukan hanya satu artefak teratas, agar tidak ada endpoint yang hanya
    # terlihat di berkas JSON. Tiap artefak tetap dipangkas 8 baris agar layar
    # tidak tenggelam.
    with_endpoints = sorted(
        ((name, data) for name, data in artifacts.items() if data.get("app_endpoints")),
        key=lambda item: len(item[1]["app_endpoints"]),
        reverse=True,
    )
    if with_endpoints:
        print()
        rule("ENDPOINT APLIKASI")
        for name, data in with_endpoints:
            endpoints = data["app_endpoints"]
            print(f"  {DIM}dari {name} ({len(endpoints)}){RESET}")
            for ep in endpoints[:8]:
                print(f"  {TEAL}·{RESET} {ep}")
            extra = len(endpoints) - 8
            if extra > 0:
                print(f"  {DIM}  … dan {extra} lainnya (lihat berkas JSON){RESET}")


def find_apk_candidates() -> list:
    # Cari berkas .apk di beberapa folder relevan agar pengguna bisa memilih
    # lewat nomor, tanpa mengetik path panjang. Termasuk PENDUKUNG/apk_input
    # (tempat APK nyata diletakkan) yang berada di luar UTAMA.
    dirs = [
        Path.cwd(),
        BASE_DIR,
        BASE_DIR.parent / "PENDUKUNG" / "apk_input",
        Path.cwd() / "apk",
    ]
    found = []
    for directory in dirs:
        if directory.is_dir():
            for apk in sorted(directory.glob("*.apk")):
                resolved = apk.resolve()
                if resolved not in found:
                    found.append(resolved)
    return found


def action_analyze() -> None:
    # Menu 1: tampilkan daftar APK yang ditemukan (pilih nomor) atau ketik path,
    # lalu orkestrasi pipeline apk_analyzer dan tampilkan hasil.
    rule("ANALISIS APK")
    candidates = find_apk_candidates()
    if candidates:
        print(f"  {GREY}APK ditemukan:{RESET}")
        for i, apk in enumerate(candidates, 1):
            try:
                shown = apk.relative_to(BASE_DIR.parent)
            except ValueError:
                shown = apk
            size = apk.stat().st_size / (1024 * 1024)
            print(f"  {BOLD}{TEAL}{i:>2}{RESET}  {shown}  {DIM}({size:.1f} MB){RESET}")
        print()
        answer = ask("Nomor, atau ketik path .apk lain: ")
    else:
        answer = ask("Path berkas .apk: ")
    # None (Ctrl-D) maupun string kosong (Enter) sama-sama berarti batal.
    if not answer:
        return
    # Kutip dilepas SESUDAH pemeriksaan, sebab drag-and-drop terminal kerap
    # menyertakan tanda kutip pada path.
    answer = answer.strip('"').strip("'")
    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        apk_path = candidates[int(answer) - 1]
    else:
        apk_path = Path(answer).expanduser().resolve()
    if not apk_path.is_file():
        print(f"  {RED}Berkas tidak ditemukan:{RESET} {apk_path}")
        pause()
        return

    print(f"\n  {DIM}mengekstrak & memindai…{RESET}")
    try:
        # Seluruh pekerjaan analisis — ekstraksi, pemilihan artefak, pemindaian,
        # pengurutan, penulisan JSON — dikerjakan analyze_apk(). Di sini hanya
        # ditambahkan callback agar nama artefak muncul di layar saat dipindai.
        outcome = apk_analyzer.analyze_apk(
            apk_path,
            on_start=lambda rel, size_kb: print(f"  {DIM}· {rel} ({size_kb:.1f} KB){RESET}"),
        )
        if outcome is None:
            print(f"  {YELLOW}Tidak ada artefak untuk dianalisis.{RESET}")
            pause()
            return
        final_result, output_json = outcome
        render_summary(final_result, output_json)
    except Exception as exc:
        print(f"  {RED}Gagal:{RESET} {exc}")
    pause()


def action_history() -> None:
    # Menu 2: cari berkas hasil analisis di direktori kerja, biar pengguna buka.
    rule("RIWAYAT ANALISIS")
    reports = sorted(glob.glob("*_analysis_*/reverse_results.json"), reverse=True)
    if not reports:
        print(f"  {DIM}Belum ada hasil analisis di direktori ini.{RESET}")
        pause()
        return
    for i, r in enumerate(reports[:20], 1):
        print(f"  {BOLD}{TEAL}{i:>2}{RESET}  {r}")
    choice = ask("Nomor untuk dibuka (Enter=batal): ")
    if not choice or not choice.isdigit() or not (1 <= int(choice) <= len(reports)):
        return
    path = Path(reports[int(choice) - 1])
    data = json.loads(path.read_text(encoding="utf-8"))
    render_summary(data, path)
    pause()


def action_tests() -> None:
    # Menu 3: jalankan tiap berkas uji sebagai subprocess, tampilkan lulus/gagal.
    rule("PENGUJIAN")
    tests = ["test_zip_slip", "test_scoring", "test_hermes"]
    for name in tests:
        script = BASE_DIR / "tests" / f"{name}.py"
        if not script.is_file():
            print(f"  {DIM}{name:<16}{RESET}{YELLOW}tidak ditemukan{RESET}")
            continue
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, cwd=str(BASE_DIR)
        )
        mark = f"{GREEN}✓ LULUS{RESET}" if result.returncode == 0 else f"{RED}✗ GAGAL{RESET}"
        print(f"  {name:<16}{mark}")
    pause()


def main() -> None:
    # Perulangan utama: gambar banner + menu, jalankan aksi terpilih, ulangi.
    actions = {"1": action_analyze, "2": action_history, "3": action_tests}
    while True:
        clear()
        banner()
        choice = menu()
        # None = Ctrl-D, diperlakukan sama dengan memilih 0 (keluar).
        if choice is None or choice == "0":
            print(f"{DIM}  Selesai.{RESET}")
            return
        action = actions.get(choice)
        if action:
            clear()
            banner()
            action()
        else:
            print(f"  {YELLOW}Pilihan tidak dikenali.{RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ctrl-C keluar rapi tanpa traceback.
        print(f"\n{DIM}  Dibatalkan.{RESET}")

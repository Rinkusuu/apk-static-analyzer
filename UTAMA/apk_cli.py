import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import apk_analyzer

BASE_DIR = Path(__file__).resolve().parent
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str) -> str:
    return code if USE_COLOR else ""


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

RISK_COLOR = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": ORANGE, "CRITICAL": RED}


def clear() -> None:
    if USE_COLOR:
        print("\033[2J\033[H", end="")


def banner() -> None:
    line = "═" * 54
    print(f"{TEAL}╔{line}╗{RESET}")
    print(f"{TEAL}║{RESET}{BOLD}   APK STATIC ANALYZER{RESET}{' ' * 32}{TEAL}║{RESET}")
    print(f"{TEAL}║{RESET}{GREY}   Analisis statis · endpoint & kredensial{RESET}{' ' * 12}{TEAL}║{RESET}")
    print(f"{TEAL}╚{line}╝{RESET}")


def rule(label: str = "") -> None:
    if label:
        pad = "─" * max(2, 52 - len(label))
        print(f"{TEAL_D}── {RESET}{BOLD}{label}{RESET} {TEAL_D}{pad}{RESET}")
    else:
        print(f"{TEAL_D}{'─' * 56}{RESET}")


def badge(level: str) -> str:
    color = RISK_COLOR.get(level, GREY)
    return f"{color}{BOLD} {level:^8} {RESET}"


def ask(prompt: str) -> Optional[str]:
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
    print()
    rule("MENU")
    print(f"  {BOLD}{TEAL}1{RESET}  Analisis sebuah APK")
    print(f"  {BOLD}{TEAL}2{RESET}  Riwayat hasil analisis")
    print(f"  {BOLD}{TEAL}3{RESET}  Jalankan pengujian")
    print(f"  {BOLD}{TEAL}0{RESET}  Keluar")
    print()
    return ask("Pilih menu: ")


def render_summary(final_result: dict, output_json: Path) -> None:
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

    scanned = [data for data in artifacts.values() if "error" not in data]
    total_endpoints = sum(d["summary"].get("total_app_endpoints", 0) for d in scanned)
    total_tokens = sum(d["summary"]["total_tokens_found"] for d in scanned)
    print()
    print(f"  {BOLD}Total{RESET}    : {total_endpoints} endpoint aplikasi"
          f" · {total_tokens} kredensial")
    print(f"  {DIM}Skor risiko menilai kebocoran kredensial; daftar endpoint"
          f" bersifat inventaris{RESET}")
    print(f"  {DIM}dan tidak menaikkan skor.{RESET}")

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
    if not answer:
        return
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
    actions = {"1": action_analyze, "2": action_history, "3": action_tests}
    while True:
        clear()
        banner()
        choice = menu()
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
        print(f"\n{DIM}  Dibatalkan.{RESET}")

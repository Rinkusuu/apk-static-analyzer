import argparse
import base64
import datetime
import json
import math
import re
import traceback
import zipfile
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


def calculate_shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counter = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counter.values())


def extract_apk(apk_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.resolve()
    with zipfile.ZipFile(apk_path, "r") as apk:
        for member in apk.namelist():
            target = (output_root / member).resolve()
            if target != output_root and output_root not in target.parents:
                raise ValueError(
                    f"Entri APK menulis di luar direktori tujuan (Zip Slip): {member!r}"
                )
        apk.extractall(output_dir)


HERMES_MAGIC = 0x1F1903C103BC1FC6
HERMES_HEADER_SIZE = 128


def extract_hermes_strings(raw: bytes) -> Optional[List[str]]:
    """Ekstrak string bersih dari bundle Hermes bytecode.

    Bundle React Native modern adalah Hermes bytecode: seluruh string disimpan
    berjejalan pada satu blok tanpa pemisah. Regex byte mentah karena itu
    menangkap string dengan ekor string berikutnya menempel. Fungsi ini membaca
    tabel string Hermes (pasangan offset+panjang) untuk memotong tiap string
    tepat pada batas aslinya.

    Mengembalikan daftar string bila berkas adalah Hermes yang dapat diurai,
    atau None agar pemanggil kembali ke pemindaian byte mentah biasa.
    """
    if len(raw) < HERMES_HEADER_SIZE or struct.unpack_from("<Q", raw, 0)[0] != HERMES_MAGIC:
        return None
    try:
        u32 = lambda o: struct.unpack_from("<I", raw, o)[0]
        function_count, string_kind_count, identifier_count = u32(40), u32(44), u32(48)
        string_count, overflow_count, storage_size = u32(52), u32(56), u32(60)

        align4 = lambda x: (x + 3) & ~3
        off = align4(HERMES_HEADER_SIZE + function_count * 16)
        off = align4(off + string_kind_count * 4)
        off = align4(off + identifier_count * 4)
        small_tbl = off
        off = align4(off + string_count * 4)
        overflow_tbl = off
        off = align4(off + overflow_count * 8)
        storage = off

        if storage + storage_size > len(raw):
            return None

        strings = []
        for i in range(string_count):
            entry = u32(small_tbl + i * 4)
            is_utf16 = entry & 1
            s_off = (entry >> 1) & 0x7FFFFF
            s_len = (entry >> 24) & 0xFF
            if s_len == 0xFF:
                s_len = u32(overflow_tbl + s_off * 8 + 4)
                s_off = u32(overflow_tbl + s_off * 8)
            start = storage + s_off
            if is_utf16:
                strings.append(raw[start:start + s_len * 2].decode("utf-16-le", "ignore"))
            else:
                strings.append(raw[start:start + s_len].decode("utf-8", "ignore"))
        return strings
    except (struct.error, IndexError):
        return None


def find_artifacts(root_dir: Path) -> List[Path]:
    artifacts: List[Path] = []
    artifacts.extend(root_dir.rglob("*.bundle"))
    artifacts.extend(root_dir.rglob("*.jsbundle"))
    artifacts.extend(root_dir.rglob("*.dex"))
    artifacts.extend(root_dir.rglob("libflutter.so"))
    artifacts.extend(root_dir.rglob("libapp.so"))
    artifacts.extend(root_dir.rglob("*_blob.bin"))
    artifacts.extend(root_dir.rglob("*.dart"))
    artifacts.extend(root_dir.rglob("AndroidManifest.xml"))
    if not artifacts:
        all_files = [f for f in root_dir.rglob("*") if f.is_file()]
        all_files.sort(key=lambda x: x.stat().st_size, reverse=True)
        artifacts = all_files[:5]
    return sorted(set(artifacts))


TOKEN_PATTERNS = {
    "AWS Access Key": (rb"(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}", 100),
    "Google API Key": (rb"AIza[0-9A-Za-z\-_]{35}", 90),
    "GitHub Token": (rb"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}", 95),
    "GitLab Token": (rb"glpat-[A-Za-z0-9\-_]{20,}", 95),
    "Telegram Bot Token": (rb"[0-9]{8,10}:AA[0-9A-Za-z\-_]{33}", 85),
    "Slack Token": (rb"xox[baprs]-[0-9a-zA-Z\-]{10,}", 80),
    "Slack Webhook": (rb"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]{8}/B[a-zA-Z0-9_]{8}/[a-zA-Z0-9_]{24}", 80),
    "Discord Webhook": (rb"https://discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9\-_]{60,}", 80),
    "Firebase URL": (rb"https://[a-z0-9\-]+\.firebaseio\.com", 70),
    "JWT Token": (rb"eyJ[A-Za-z0-9\-_=]{10,}\.[A-Za-z0-9\-_=]{10,}\.[A-Za-z0-9\-_.+/=]{10,}", 85),
    "Stripe Key": (rb"(?:pk|sk)_(?:live|test)_[0-9a-zA-Z]{24,}", 95),
    "Alibaba Cloud Key": (rb"LTAI[A-Za-z0-9]{20}", 90),
    "Twilio API Key": (rb"SK[0-9a-fA-F]{32}", 85),
    "Mailgun API Key": (rb"key-[0-9a-f]{32}\b", 80),
    "SendGrid API Key": (rb"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}", 85),
    "Heroku API Key": (
        rb"(?i)heroku[a-z0-9_\-]{0,20}[\"']?\s*[:=]\s*[\"']?"
        rb"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        60,
    ),
    "Generic API Key": (rb"(?i)(?:api_key|apikey|api_secret|secret_key|access_token|auth_token|client_secret)\s*[:=]\s*[\"']([A-Za-z0-9_\-]{16,})[\"']", 75),
    "Private Key Block": (rb"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", 100),
    "Certificate Block": (rb"-----BEGIN CERTIFICATE-----", 50),
}

RISK_THRESHOLDS = ((90, "CRITICAL"), (70, "HIGH"), (50, "MEDIUM"))
MAX_BASE64_DECODES = 50
MAX_FILE_SIZE = 300 * 1024 * 1024

# Magic byte awal berkas biner umum (gambar, arsip, executable). Dipakai untuk
# menolak aset yang salah tuduh sebagai rahasia hasil dekode Base64.
BINARY_MAGIC = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",        # JPEG
    b"GIF87a", b"GIF89a",   # GIF
    b"RIFF",                # WEBP / WAV / AVI
    b"\x1f\x8b",            # gzip
    b"PK\x03\x04",          # zip / jar / apk
    b"BZh",                 # bzip2
    b"%PDF",                # PDF
    b"\x7fELF",             # ELF
    b"OggS",                # OGG
)


def analyze_artifact(artifact_path: Path) -> Dict[str, Any]:
    file_size = artifact_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return {"file": artifact_path.name, "error": "File >300MB, dilewati."}

    raw_bytes = artifact_path.read_bytes()

    # Bundle Hermes: ganti korpus dengan string bersih dari tabel string, dipisah
    # newline agar regex tidak menyeberang batas antar-string. Bila bukan Hermes
    # (atau gagal diurai), pemindaian tetap memakai byte mentah seperti biasa.
    hermes_strings = extract_hermes_strings(raw_bytes)
    is_hermes = hermes_strings is not None
    if is_hermes:
        raw_bytes = "\n".join(hermes_strings).encode("utf-8", "ignore")

    results: Dict[str, set] = {
        "urls": set(),
        "websockets": set(),
        "ip_addresses": set(),
        "api_paths": set(),
        "action_endpoints": set(),
        "api_keys_and_tokens": set(),
        "sensitive_headers": set(),
        "env_variables": set(),
        "storage_keys": set(),
        "db_connections": set(),
        "flutter_ipc": set(),
        "android_components": set(),
        "decoded_secrets": set(),
        "keywords_found": set(),
    }
    # Bobot per temuan unik; skor akhir dihitung dari kumpulan ini (bagian N).
    finding_weights: Dict[str, int] = {}

    # A. URL & websocket
    for url in re.findall(rb"https?://[^\s\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        cleaned = url.decode("utf-8", errors="ignore").rstrip(".,);:]")
        if len(cleaned) > 10:
            results["urls"].add(cleaned)
    for ws in re.findall(rb"wss?://[^\s\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        results["websockets"].add(ws.decode("utf-8", errors="ignore").rstrip(".,);:]"))

    # B. IP address
    for ip in re.findall(
        rb"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        raw_bytes,
    ):
        ip_str = ip.decode("utf-8", errors="ignore")
        if not ip_str.startswith(("127.", "0.0.0.0", "255.255.255.", "10.0.2.")):
            results["ip_addresses"].add(ip_str)

    # C. API paths. Batas kiri/kanan menerima tanda kutip ATAU batas string
    # (awal/akhir baris) agar path standalone pada bundle Hermes ikut tertangkap,
    # bukan hanya literal berkutip pada JS biasa.
    for path in re.findall(
        rb"(?:[\"']|^|\n)(/(?:api|apimobile|v[0-9]+|graphql|rest|auth|user|admin|wp-json|oauth|token|session|upload|download|payment|checkout)[a-zA-Z0-9._/\-]*)(?:[\"']|$|\n)",
        raw_bytes,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        results["api_paths"].add(path.decode("utf-8", errors="ignore").rstrip("/"))

    # D. Action endpoints
    action_patterns = [
        rb"[\"']((?:get|post|put|delete|check|fetch|update|create|remove|detail|user|auth|list|verify|validate|reset|confirm|send|receive)[a-zA-Z0-9_-]{3,50})[\"']",
        rb"\b(?:[a-zA-Z0-9_-]{0,20}(?:checkout|checkin|detail|user|profile|dashboard|settings|notification)[a-zA-Z0-9_-]{0,20})\b",
    ]
    skip_words = {"undefined", "function", "object", "string", "number", "boolean", "return", "import", "export"}
    for pattern in action_patterns:
        for act in re.findall(pattern, raw_bytes, flags=re.IGNORECASE):
            act_str = act.decode("utf-8", errors="ignore")
            if len(act_str) > 4 and act_str.lower() not in skip_words:
                results["action_endpoints"].add(act_str)
    for kv in re.findall(
        rb"[\"']?(?:action|endpoint|route|path|method|name|url|uri)[\"']?\s*[:=]\s*[\"']([a-zA-Z0-9_\-/.]{3,60})[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        kv_str = kv.decode("utf-8", errors="ignore")
        if kv_str.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH", "JSON", "TRUE", "FALSE", "NULL"}:
            results["action_endpoints"].add(kv_str)

    # E. Token & kredensial
    for name, (pattern, weight) in TOKEN_PATTERNS.items():
        for match in re.findall(pattern, raw_bytes):
            if isinstance(match, tuple):
                match = match[0]
            if name == "Generic API Key" and calculate_shannon_entropy(match) < 3.8:
                continue
            finding_key = f"[{name}] {match.decode('utf-8', errors='ignore')}"
            results["api_keys_and_tokens"].add(finding_key)
            finding_weights[finding_key] = weight

    # F. Sensitive headers
    for h in re.findall(
        rb"[\"'](Authorization|X-API-Key|X-Auth-Token|X-Access-Token|X-Forwarded-For|X-Real-IP|Bearer\s+[A-Za-z0-9\-._~+/]+=*)[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        results["sensitive_headers"].add(h.decode("utf-8", errors="ignore"))

    # G. Environment variables
    for env in re.findall(rb"\b(?:REACT_APP_|EXPO_PUBLIC_|NEXT_PUBLIC_|APP_|FLUTTER_|VITE_|NUXT_)[A-Z0-9_]{3,}\b", raw_bytes):
        results["env_variables"].add(env.decode("utf-8", errors="ignore"))

    # H. Storage keys
    for key in re.findall(rb"[\"'](@[a-zA-Z0-9_:/.\-]+)[\"']", raw_bytes):
        results["storage_keys"].add(key.decode("utf-8", errors="ignore"))
    for key in re.findall(rb"[\"']((?:shared_preferences_|flutter\.secure_storage|AsyncStorage_)[a-zA-Z0-9_]+)[\"']", raw_bytes):
        results["storage_keys"].add(key.decode("utf-8", errors="ignore"))

    # I. Database connection strings
    for db in re.findall(rb"(?i)(?:jdbc:(?:mysql|postgresql|oracle|sqlserver)://[^\s\"']{10,}|mongodb(?:\+srv)?://[^\s\"']{10,}|redis://[^\s\"']{10,}|amqp://[^\s\"']{10,})", raw_bytes):
        db_str = db.decode("utf-8", errors="ignore")
        results["db_connections"].add(db_str)
        finding_weights[f"[db] {db_str}"] = 95

    # J. Flutter IPC
    for ch in re.findall(rb"[\"']((?:MethodChannel|EventChannel|BasicMessageChannel)\([\"'][^\"']+[\"']\))[\"']", raw_bytes):
        results["flutter_ipc"].add(ch.decode("utf-8", errors="ignore"))
    for inv in re.findall(rb"[\"']([a-zA-Z_]+(?:Channel|Plugin|Handler))[\"']", raw_bytes):
        inv_str = inv.decode("utf-8", errors="ignore")
        if len(inv_str) > 6:
            results["flutter_ipc"].add(inv_str)

    # K. Android components
    for comp in re.findall(rb"[\"']((?:com|org|net|io)\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_.]+(?:Activity|Service|Receiver|Provider|Fragment))[\"']", raw_bytes):
        results["android_components"].add(comp.decode("utf-8", errors="ignore"))
    for perm in re.findall(rb"[\"'](android\.permission\.[A-Z_]+)[\"']", raw_bytes):
        results["android_components"].add(perm.decode("utf-8", errors="ignore"))

    # L. Base64 decode pass (anti-obfuskasi)
    sensitive_indicators = ("http", "api", "key", "token", "secret", "pass", "auth", "admin", "login", "bearer", "jdbc", "mongodb")
    decoded_count = 0
    for candidate in re.findall(rb"(?:[A-Za-z0-9+/]{4}){8,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?", raw_bytes):
        if decoded_count >= MAX_BASE64_DECODES:
            break
        try:
            decoded_bytes = base64.b64decode(candidate, validate=True)
        except Exception:
            continue
        if len(decoded_bytes) < 8 or calculate_shannon_entropy(decoded_bytes) < 3.5:
            continue
        # Tolak aset biner (gambar, arsip): magic byte-nya menandai berkas, bukan
        # rahasia. Tanpa ini, gambar tertanam kerap salah tuduh sebagai secret.
        if decoded_bytes.startswith(BINARY_MAGIC):
            continue
        decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
        if any(ind in decoded_str.lower() for ind in sensitive_indicators):
            secret_str = decoded_str[:200]
            results["decoded_secrets"].add(secret_str)
            finding_weights[f"[decoded] {secret_str}"] = 70
            decoded_count += 1

    # M. Keywords
    keywords = [
        b"login", b"logout", b"register", b"auth", b"user", b"profile",
        b"upload", b"download", b"payment", b"admin", b"graphql", b"websocket",
        b"password", b"secret", b"token", b"private_key", b"staging", b"debug",
        b"flutter", b"dart", b"obfuscate", b"proguard", b"keystore", b"jks",
        b"encrypt", b"decrypt", b"certificate", b"ssl", b"tls", b"oauth",
        b"session", b"cookie", b"csrf", b"xss", b"injection", b"root",
        b"su ", b"magisk", b"frida", b"xposed",
    ]
    for kw in keywords:
        if re.search(rb"\b" + kw + rb"\b", raw_bytes, re.IGNORECASE):
            results["keywords_found"].add(kw.decode("utf-8", errors="ignore").strip())

    # N. Risk classification: severity (temuan terparah) + breadth (bonus terbatas)
    severity = max(finding_weights.values(), default=0)
    breadth_bonus = min(max(len(finding_weights) - 1, 0), 5) * 4
    risk_score = severity + breadth_bonus
    risk_level = "LOW"
    for threshold, level in RISK_THRESHOLDS:
        if risk_score >= threshold:
            risk_level = level
            break

    return {
        "file": artifact_path.name,
        "size_kb": round(file_size / 1024, 2),
        "is_hermes": is_hermes,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "summary": {
            "total_urls": len(results["urls"]),
            "total_api_paths": len(results["api_paths"]),
            "total_tokens_found": len(results["api_keys_and_tokens"]),
            "total_db_connections": len(results["db_connections"]),
            "total_decoded_secrets": len(results["decoded_secrets"]),
            "total_keywords": len(results["keywords_found"]),
        },
        **{key: sorted(value) for key, value in results.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-framework APK static analyzer")
    parser.add_argument("apk_path", type=Path, help="Path ke file .apk target")
    args = parser.parse_args()

    apk_path = args.apk_path.resolve()
    if not apk_path.is_file():
        print(f"[!] Error: File '{apk_path}' tidak ditemukan.")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"{apk_path.stem}_analysis_{timestamp}")
    extract_dir = output_dir / "extracted_files"

    print(f"[*] Target: {apk_path.name}")
    print(f"[*] Output: {output_dir.resolve()}")

    try:
        print("[*] Mengekstrak APK...")
        extract_apk(apk_path, extract_dir)

        print("[*] Memindai artefak (RN / Kotlin / Flutter)...")
        artifacts = find_artifacts(extract_dir)
        if not artifacts:
            print("[!] Tidak ditemukan artefak untuk dianalisis.")
            return
        print(f"[*] Ditemukan {len(artifacts)} artefak.\n")

        final_result = {
            "metadata": {
                "target_apk": apk_path.name,
                "analysis_timestamp": timestamp,
                "total_artifacts_found": len(artifacts),
            },
            "artifacts": {},
        }
        for artifact in artifacts:
            relative_path = str(artifact.relative_to(extract_dir))
            print(f"[*] Menganalisis: {relative_path} ({artifact.stat().st_size / 1024:.1f} KB)")
            result = analyze_artifact(artifact)
            final_result["artifacts"][relative_path] = result
            print(f"    -> Risiko: {result['risk_level']} | Token: {result['summary']['total_tokens_found']} | URL: {result['summary']['total_urls']}")

        final_result["artifacts"] = dict(
            sorted(final_result["artifacts"].items(), key=lambda x: x[1].get("risk_score", 0), reverse=True)
        )

        output_json = output_dir / "reverse_results.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=4, ensure_ascii=False)

        print(f"\n[+] Analisis selesai.")
        print(f"[+] Hasil tersimpan di: {output_json.resolve()}")

    except Exception as e:
        print(f"[!] Fatal Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()

import argparse
import json
import re
import zipfile
import datetime
import math
import base64
from pathlib import Path
from collections import Counter
from typing import Dict, List, Any


# ==============================================================================
# 1. UTILITAS
# ==============================================================================
def calculate_shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counter = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counter.values())


def extract_apk(apk_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk_path, "r") as apk:
        apk.extractall(output_dir)


def find_artifacts(root_dir: Path) -> List[Path]:
    artifacts = []
    # React Native
    artifacts.extend(root_dir.rglob("*.bundle"))
    artifacts.extend(root_dir.rglob("*.jsbundle"))
    # Kotlin / Java
    artifacts.extend(root_dir.rglob("*.dex"))
    # Flutter
    artifacts.extend(root_dir.rglob("libflutter.so"))
    artifacts.extend(root_dir.rglob("libapp.so"))
    artifacts.extend(root_dir.rglob("*_blob.bin"))
    artifacts.extend(root_dir.rglob("*.dart"))
    # Android Manifest (binary XML, tapi masih mengandung string)
    artifacts.extend(root_dir.rglob("AndroidManifest.xml"))
    # Fallback: jika tidak ada yang ditemukan, cari file terbesar
    if not artifacts:
        all_files = [f for f in root_dir.rglob("*") if f.is_file()]
        if all_files:
            all_files.sort(key=lambda x: x.stat().st_size, reverse=True)
            artifacts = all_files[:5]
    return sorted(list(set(artifacts)))


# ==============================================================================
# 2. MESIN ANALISIS (MEKANISME VERSI ASLI: re.findall + read_bytes)
# ==============================================================================
def analyze_artifact(artifact_path: Path) -> Dict[str, Any]:
    file_size = artifact_path.stat().st_size
    if file_size > 300 * 1024 * 1024:
        return {"file": artifact_path.name, "error": "File >300MB, dilewati."}

    raw_bytes = artifact_path.read_bytes()

    results = {
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
    risk_score = 0

    # ──────────────────────────────────────────────
    # A. URL & WEBSOCKET
    # ──────────────────────────────────────────────
    for url in re.findall(rb"https?://[^\s\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        cleaned = url.decode("utf-8", errors="ignore").rstrip(".,);:]")
        if len(cleaned) > 10:
            results["urls"].add(cleaned)

    for ws in re.findall(rb"wss?://[^\s\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        cleaned = ws.decode("utf-8", errors="ignore").rstrip(".,);:]")
        results["websockets"].add(cleaned)

    # ──────────────────────────────────────────────
    # B. IP ADDRESS
    # ──────────────────────────────────────────────
    for ip in re.findall(
        rb"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        raw_bytes,
    ):
        ip_str = ip.decode("utf-8", errors="ignore")
        if not ip_str.startswith(("127.", "0.0.0.0", "255.255.255.", "10.0.2.")):
            results["ip_addresses"].add(ip_str)

    # ──────────────────────────────────────────────
    # C. API PATHS
    # ──────────────────────────────────────────────
    for path in re.findall(
        rb"[\"'](/(?:api|apimobile|v[0-9]+|graphql|rest|auth|user|admin|wp-json|oauth|token|session|upload|download|payment|checkout)[a-zA-Z0-9._/\-]*)[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        results["api_paths"].add(path.decode("utf-8", errors="ignore"))

    # ──────────────────────────────────────────────
    # D. ACTION ENDPOINTS
    # ──────────────────────────────────────────────
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

    # Key-Value endpoint extraction
    for kv in re.findall(
        rb"[\"']?(?:action|endpoint|route|path|method|name|url|uri)[\"']?\s*[:=]\s*[\"']([a-zA-Z0-9_\-/.]{3,60})[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        kv_str = kv.decode("utf-8", errors="ignore")
        if kv_str.upper() not in {"GET", "POST", "PUT", "DELETE", "PATCH", "JSON", "TRUE", "FALSE", "NULL"}:
            results["action_endpoints"].add(kv_str)

    # ──────────────────────────────────────────────
    # E. TOKEN & CREDENTIALS (MEKANISME ASLI: re.findall)
    # ──────────────────────────────────────────────
    token_patterns = {
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
        "Mailgun API Key": (rb"key-[0-9a-zA-Z]{32}", 80),
        "SendGrid API Key": (rb"SG\.[A-Za-z0-9\-_]{22}\.[A-Za-z0-9\-_]{43}", 85),
        # Deteksi berbasis konteks, bukan bentuk. Kunci Heroku berbentuk UUID
        # biasa tanpa awalan khas seperti AKIA atau ghp_, sehingga secara bentuk
        # mustahil dibedakan dari request-id maupun trace-id yang lazim ada
        # ratusan di dalam satu APK. Karena itu UUID hanya dianggap kredensial
        # apabila didahului label yang menyebut "heroku".
        "Heroku API Key": (
            rb"(?i)heroku[a-z0-9_\-]{0,20}[\"']?\s*[:=]\s*[\"']?"
            rb"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            60,
        ),
        "Generic API Key": (rb"(?i)(?:api_key|apikey|api_secret|secret_key|access_token|auth_token|client_secret)\s*[:=]\s*[\"']([A-Za-z0-9_\-]{16,})[\"']", 75),
        "Private Key Block": (rb"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----", 100),
        "Certificate Block": (rb"-----BEGIN CERTIFICATE-----", 50),
    }

    for name, (pattern, weight) in token_patterns.items():
        matches = re.findall(pattern, raw_bytes)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            token_str = match.decode("utf-8", errors="ignore")

            # Filter entropi HANYA untuk Generic API Key
            if name == "Generic API Key":
                if calculate_shannon_entropy(match) < 3.8:
                    continue

            results["api_keys_and_tokens"].add(f"[{name}] {token_str}")
            risk_score += weight

    # ──────────────────────────────────────────────
    # F. SENSITIVE HEADERS
    # ──────────────────────────────────────────────
    for h in re.findall(
        rb"[\"'](Authorization|X-API-Key|X-Auth-Token|X-Access-Token|X-Forwarded-For|X-Real-IP|Bearer\s+[A-Za-z0-9\-._~+/]+=*)[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        results["sensitive_headers"].add(h.decode("utf-8", errors="ignore"))

    # ──────────────────────────────────────────────
    # G. ENVIRONMENT VARIABLES
    # ──────────────────────────────────────────────
    for env in re.findall(rb"\b(?:REACT_APP_|EXPO_PUBLIC_|NEXT_PUBLIC_|APP_|FLUTTER_|VITE_|NUXT_)[A-Z0-9_]{3,}\b", raw_bytes):
        results["env_variables"].add(env.decode("utf-8", errors="ignore"))

    # ──────────────────────────────────────────────
    # H. STORAGE KEYS
    # ──────────────────────────────────────────────
    for key in re.findall(rb"[\"'](@[a-zA-Z0-9_:/.\-]+)[\"']", raw_bytes):
        results["storage_keys"].add(key.decode("utf-8", errors="ignore"))
    for key in re.findall(rb"[\"']((?:shared_preferences_|flutter\.secure_storage|AsyncStorage_)[a-zA-Z0-9_]+)[\"']", raw_bytes):
        results["storage_keys"].add(key.decode("utf-8", errors="ignore"))

    # ──────────────────────────────────────────────
    # I. DATABASE CONNECTION STRINGS
    # ──────────────────────────────────────────────
    for db in re.findall(rb"(?i)(?:jdbc:(?:mysql|postgresql|oracle|sqlserver)://[^\s\"']{10,}|mongodb(?:\+srv)?://[^\s\"']{10,}|redis://[^\s\"']{10,}|amqp://[^\s\"']{10,})", raw_bytes):
        results["db_connections"].add(db.decode("utf-8", errors="ignore"))
        risk_score += 95

    # ──────────────────────────────────────────────
    # J. FLUTTER IPC
    # ──────────────────────────────────────────────
    for ch in re.findall(rb"[\"']((?:MethodChannel|EventChannel|BasicMessageChannel)\([\"'][^\"']+[\"']\))[\"']", raw_bytes):
        results["flutter_ipc"].add(ch.decode("utf-8", errors="ignore"))
    for inv in re.findall(rb"[\"']([a-zA-Z_]+(?:Channel|Plugin|Handler))[\"']", raw_bytes):
        inv_str = inv.decode("utf-8", errors="ignore")
        if len(inv_str) > 6:
            results["flutter_ipc"].add(inv_str)

    # ──────────────────────────────────────────────
    # K. ANDROID COMPONENTS (dari binary XML & string pool)
    # ──────────────────────────────────────────────
    for comp in re.findall(rb"[\"']((?:com|org|net|io)\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_.]+(?:Activity|Service|Receiver|Provider|Fragment))[\"']", raw_bytes):
        results["android_components"].add(comp.decode("utf-8", errors="ignore"))
    for perm in re.findall(rb"[\"'](android\.permission\.[A-Z_]+)[\"']", raw_bytes):
        results["android_components"].add(perm.decode("utf-8", errors="ignore"))

    # ──────────────────────────────────────────────
    # L. ANTI-OBFUSCATION: BASE64 DECODE PASS
    # ──────────────────────────────────────────────
    b64_candidates = re.findall(rb"(?:[A-Za-z0-9+/]{4}){8,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?", raw_bytes)
    decoded_count = 0
    for candidate in b64_candidates:
        if decoded_count >= 50:  # Batasi untuk performa
            break
        try:
            decoded_bytes = base64.b64decode(candidate, validate=True)
            if len(decoded_bytes) < 8:
                continue
            entropy = calculate_shannon_entropy(decoded_bytes)
            if entropy < 3.5:
                continue
            decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
            # Cek apakah mengandung indikator sensitif
            sensitive_indicators = ["http", "api", "key", "token", "secret", "pass", "auth", "admin", "login", "Bearer", "jdbc", "mongodb"]
            if any(ind.lower() in decoded_str.lower() for ind in sensitive_indicators):
                results["decoded_secrets"].add(decoded_str[:200])
                risk_score += 70
                decoded_count += 1
        except Exception:
            continue

    # ──────────────────────────────────────────────
    # M. KEYWORDS
    # ──────────────────────────────────────────────
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

    # ──────────────────────────────────────────────
    # N. RISK CLASSIFICATION
    # ──────────────────────────────────────────────
    if risk_score >= 200:
        risk_level = "CRITICAL"
    elif risk_score >= 100:
        risk_level = "HIGH"
    elif risk_score >= 50:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "file": artifact_path.name,
        "size_kb": round(file_size / 1024, 2),
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
        "urls": sorted(results["urls"]),
        "websockets": sorted(results["websockets"]),
        "ip_addresses": sorted(results["ip_addresses"]),
        "api_paths": sorted(results["api_paths"]),
        "action_endpoints": sorted(results["action_endpoints"]),
        "api_keys_and_tokens": sorted(results["api_keys_and_tokens"]),
        "sensitive_headers": sorted(results["sensitive_headers"]),
        "env_variables": sorted(results["env_variables"]),
        "storage_keys": sorted(results["storage_keys"]),
        "db_connections": sorted(results["db_connections"]),
        "flutter_ipc": sorted(results["flutter_ipc"]),
        "android_components": sorted(results["android_components"]),
        "decoded_secrets": sorted(results["decoded_secrets"]),
        "keywords_found": sorted(results["keywords_found"]),
    }


# ==============================================================================
# 3. MAIN PIPELINE (SEQUENTIAL - STABIL DI WINDOWS)
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Multi-Framework APK Static Analyzer (Stable)")
    parser.add_argument("apk_path", type=Path, help="Path ke file .apk target")
    args = parser.parse_args()

    apk_path = args.apk_path.resolve()
    if not apk_path.exists() or not apk_path.is_file():
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
            size_kb = artifact.stat().st_size / 1024
            print(f"[*] Menganalisis: {relative_path} ({size_kb:.1f} KB)")
            result = analyze_artifact(artifact)
            final_result["artifacts"][relative_path] = result
            print(f"    -> Risiko: {result['risk_level']} | Token: {result['summary']['total_tokens_found']} | URL: {result['summary']['total_urls']}")

        # Urutkan berdasarkan risk_score descending
        final_result["artifacts"] = dict(
            sorted(final_result["artifacts"].items(), key=lambda x: x[1].get("risk_score", 0), reverse=True)
        )

        # Tulis JSON
        output_json = output_dir / "reverse_results.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=4, ensure_ascii=False)

        print(f"\n[+] Analisis selesai.")
        print(f"[+] Hasil tersimpan di: {output_json.resolve()}")

    except Exception as e:
        print(f"[!] Fatal Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
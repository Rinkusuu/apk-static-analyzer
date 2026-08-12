"""
Generator APK sintetis untuk pengujian apk_analyzer.

Menghasilkan dua berkas:
  - sample.apk      : APK palsu (zip valid) berisi artefak RN / Kotlin / Manifest
  - expected.json   : ground truth, yaitu daftar seluruh rahasia yang ditanam
                      beserta status apakah ia WAJIB terdeteksi atau justru
                      merupakan umpan (decoy) yang TIDAK boleh terdeteksi.

expected.json dibangkitkan dari struktur data yang sama dengan isi APK, sehingga
ground truth tidak mungkin melenceng dari berkas yang diuji.

Semua kredensial di bawah ini adalah nilai palsu yang sengaja dibuat agar cocok
dengan pola regex analyzer. Tidak ada satu pun yang merupakan kredensial asli.
"""

import json
import random
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APK_PATH = BASE_DIR / "sample.apk"
EXPECTED_PATH = BASE_DIR / "expected.json"


# ==============================================================================
# 1. RAHASIA YANG DITANAM (harus terdeteksi)
# ==============================================================================
# Format: (kategori_hasil, label_detektor, nilai_yang_diharapkan_muncul)
PLANTED_SECRETS = [
    ("api_keys_and_tokens", "AWS Access Key", "AKIAIOSFODNN7EXAMPLE"),
    ("api_keys_and_tokens", "Google API Key", "AIzaSyA01234567890123456789012345678901"),
    ("api_keys_and_tokens", "GitHub Token", "ghp_0123456789abcdefghijklmnopqrstuvwxyz"),
    ("api_keys_and_tokens", "GitLab Token", "glpat-abcdefghij0123456789"),
    ("api_keys_and_tokens", "Stripe Key", "sk_test_0123456789abcdefghij0123"),
    ("api_keys_and_tokens", "Slack Token", "xoxb-1234567890-ABCDEFGHIJ"),
    ("api_keys_and_tokens", "Telegram Bot Token", "123456789:AAabcdefghijklmnopqrstuvwxyz0123456"),
    ("api_keys_and_tokens", "Alibaba Cloud Key", "LTAI0123456789abcdefghij"),
    ("api_keys_and_tokens", "Twilio API Key", "SK0123456789abcdef0123456789abcdef"),
    (
        "api_keys_and_tokens",
        "SendGrid API Key",
        "SG.abcdefghijklmnopqrstuv.abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    ),
    (
        "api_keys_and_tokens",
        "JWT Token",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkRlbW8ifQ"
        ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXkw",
    ),
    ("api_keys_and_tokens", "Private Key Block", "-----BEGIN RSA PRIVATE KEY-----"),
    ("api_keys_and_tokens", "Generic API Key", "s3cr3tV4lue_Ab12Cd34Ef56"),
    ("db_connections", None, "mongodb://appuser:P4ssw0rd@db.internal.example.com:27017/prod"),
    ("db_connections", None, "jdbc:mysql://db.internal.example.com:3306/prod"),
    ("urls", None, "https://api.example-corp.com/v1/login"),
    ("urls", None, "https://staging-api.example-corp.com/v2/payment"),
    ("websockets", None, "wss://ws.example-corp.com/socket"),
    ("ip_addresses", None, "203.0.113.45"),
]

# ==============================================================================
# 2. UMPAN / DECOY (TIDAK boleh terdeteksi sebagai kredensial)
# ==============================================================================
# UUID biasa. Nilai seperti ini lazim muncul ratusan kali di APK nyata sebagai
# request-id, trace-id, atau resource-id, dan sama sekali bukan kredensial.
random.seed(20260731)  # deterministik agar sampel dapat direproduksi


def _fake_uuid() -> str:
    h = "0123456789abcdef"
    part = lambda n: "".join(random.choice(h) for _ in range(n))
    return f"{part(8)}-{part(4)}-{part(4)}-{part(4)}-{part(12)}"


DECOY_UUIDS = [_fake_uuid() for _ in range(40)]

# Nilai entropi rendah pada kunci bernama "api_key" — jelas placeholder,
# bukan kredensial sungguhan.
DECOY_LOW_ENTROPY = "aaaaaaaaaaaaaaaaaaaa"

DECOYS = [(u, "UUID biasa (request-id), bukan kredensial") for u in DECOY_UUIDS]
DECOYS.append((DECOY_LOW_ENTROPY, "placeholder entropi rendah pada key 'api_key'"))


# ==============================================================================
# 3. ISI ARTEFAK
# ==============================================================================
def build_js_bundle() -> bytes:
    """Meniru index.android.bundle milik aplikasi React Native."""
    uuid_lines = ",\n".join(f'    "{u}"' for u in DECOY_UUIDS)
    return f"""\
var __BUNDLE__=(function(){{
  var CONFIG = {{
    apiBase: "https://api.example-corp.com/v1/login",
    stagingBase: "https://staging-api.example-corp.com/v2/payment",
    socket: "wss://ws.example-corp.com/socket",
    fallbackHost: "203.0.113.45",
    awsKey: "AKIAIOSFODNN7EXAMPLE",
    googleKey: "AIzaSyA01234567890123456789012345678901",
    stripe: "sk_test_0123456789abcdefghij0123",
    sendgrid: "SG.abcdefghijklmnopqrstuv.abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    client_secret: "s3cr3tV4lue_Ab12Cd34Ef56",
    api_key: "{DECOY_LOW_ENTROPY}",
    sessionToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkRlbW8ifQ.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXkw"
  }};
  var ROUTES = {{
    endpoint: "/api/v1/user/profile",
    action: "getUserProfile",
    checkout: "/payment/checkout"
  }};
  var TRACE_IDS = [
{uuid_lines}
  ];
  var HEADERS = {{ "Authorization": "Bearer <redacted>", "X-API-Key": "" }};
  var STORE = {{ "@app:auth_token": null, "@app:user_profile": null }};
  var ENV = {{ base: "REACT_APP_API_BASE", flag: "EXPO_PUBLIC_DEBUG_MODE" }};
  return {{ CONFIG: CONFIG, ROUTES: ROUTES, TRACE_IDS: TRACE_IDS }};
}})();
""".encode("utf-8")


def build_dex() -> bytes:
    """Meniru classes.dex: header dex + string pool berisi literal."""
    header = b"dex\n035\x00" + b"\x00" * 24
    strings = f"""\
"mongodb://appuser:P4ssw0rd@db.internal.example.com:27017/prod"
"jdbc:mysql://db.internal.example.com:3306/prod"
"ghp_0123456789abcdefghijklmnopqrstuvwxyz"
"glpat-abcdefghij0123456789"
"xoxb-1234567890-ABCDEFGHIJ"
"123456789:AAabcdefghijklmnopqrstuvwxyz0123456"
"LTAI0123456789abcdefghij"
"SK0123456789abcdef0123456789abcdef"
"com.example.corp.ui.MainActivity"
"com.example.corp.sync.BackgroundService"
"AuthChannel"
"PaymentHandler"
-----BEGIN RSA PRIVATE KEY-----
MIIBOgIBAAJBAK7Rn8XoQ1Bq2vZ0dummykeymaterialforanalyzertestingonly==
-----END RSA PRIVATE KEY-----
""".encode("utf-8")
    return header + strings


def build_manifest() -> bytes:
    """Manifest berformat teks.

    Catatan keterbatasan: APK nyata menyimpan AndroidManifest.xml sebagai binary
    XML (AXML) tanpa tanda kutip, sehingga pola regex analyzer saat ini hanya
    bekerja pada manifest berformat teks seperti ini.
    """
    return b"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.corp">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <application android:debuggable="true">
        <activity android:name="com.example.corp.ui.MainActivity" />
        <service android:name="com.example.corp.sync.BackgroundService" />
    </application>
</manifest>
"""


# ==============================================================================
# 4. PEMBANGUNAN APK + GROUND TRUTH
# ==============================================================================
def build_apk() -> None:
    with zipfile.ZipFile(APK_PATH, "w", zipfile.ZIP_DEFLATED) as apk:
        apk.writestr("AndroidManifest.xml", build_manifest())
        apk.writestr("classes.dex", build_dex())
        apk.writestr("assets/index.android.bundle", build_js_bundle())
        apk.writestr("resources.arsc", b"\x02\x00\x0c\x00" + b"\x00" * 64)
        apk.writestr("META-INF/CERT.SF", b"Signature-Version: 1.0\n")


def build_expected() -> dict:
    return {
        "description": (
            "Ground truth untuk sample.apk. must_detect=true berarti analyzer WAJIB "
            "menemukan nilai tersebut (jika tidak = false negative). must_detect=false "
            "berarti nilai tersebut adalah umpan dan TIDAK boleh dilaporkan sebagai "
            "kredensial (jika dilaporkan = false positive)."
        ),
        "apk": APK_PATH.name,
        "expected_risk_level": "HIGH",
        "expected_risk_level_note": (
            "Sampel memang memuat 13 kredensial palsu dan 2 connection string, "
            "sehingga level risiko tinggi adalah benar. Yang diuji bukan sekadar "
            "levelnya, melainkan apakah level itu berasal dari temuan nyata atau "
            "dari akumulasi false positive."
        ),
        "planted": [
            {
                "category": category,
                "detector": detector,
                "value": value,
                "must_detect": True,
            }
            for category, detector, value in PLANTED_SECRETS
        ],
        "decoys": [
            {
                "value": value,
                "reason": reason,
                "must_detect": False,
            }
            for value, reason in DECOYS
        ],
    }


def main() -> None:
    build_apk()
    EXPECTED_PATH.write_text(
        json.dumps(build_expected(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    size_kb = APK_PATH.stat().st_size / 1024
    print(f"[+] APK sampel  : {APK_PATH}  ({size_kb:.1f} KB)")
    print(f"[+] Ground truth: {EXPECTED_PATH}")
    print(f"[+] Ditanam     : {len(PLANTED_SECRETS)} rahasia (wajib terdeteksi)")
    print(f"[+] Umpan       : {len(DECOYS)} nilai (tidak boleh terdeteksi)")


if __name__ == "__main__":
    main()

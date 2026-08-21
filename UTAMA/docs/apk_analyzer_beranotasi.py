"""
============================================================================
 SALINAN BERANOTASI — apk_analyzer.py
============================================================================

Berkas ini adalah SALINAN dari `UTAMA/apk_analyzer.py` yang diberi anotasi
selengkap mungkin sebagai bahan belajar dan bahan mempertanggungjawabkan kode.

  - Kode produksi (`UTAMA/apk_analyzer.py`) sengaja dibuat BERSIH tanpa komentar.
  - Berkas inilah tempat seluruh penjelasan, alasan desain, dan definisi istilah.
  - Berkas ini TIDAK dijalankan sebagai program; ia rujukan. Bila kode produksi
    berubah, salinan ini diperbarui agar tetap sinkron.

--------------------------------------------------------------------------
 GAMBARAN BESAR
--------------------------------------------------------------------------
Perangkat ini melakukan ANALISIS STATIS terhadap berkas APK Android.

  ISTILAH — Analisis statis : memeriksa aplikasi TANPA menjalankannya.
                              Lawannya adalah analisis dinamis (menjalankan
                              aplikasi lalu mengamati perilakunya).

APK sesungguhnya hanyalah arsip ZIP. Perangkat membukanya, memilih berkas yang
memuat kode ("artefak"), membaca tiap artefak sebagai BYTE MENTAH, lalu menyapu
±25 pola regular expression untuk menemukan URL, endpoint, kredensial, dan
indikator sensitif lain. Temuan berkategori kredensial menaikkan skor risiko.

  ISTILAH — Artefak : berkas di dalam APK yang memuat kode/konfigurasi
                      (mis. index.android.bundle, classes.dex, libapp.so).
  ISTILAH — Regex   : pola untuk mencocokkan teks. Prefiks rb"..." pada Python
                      berarti "raw bytes pattern" — pola yang dijalankan atas
                      byte, bukan teks. Ini yang memungkinkan satu mesin
                      menangani berkas teks maupun biner secara seragam.

Analogi paling tepat: perangkat ini adalah `grep` yang sangat terstruktur atas
isi APK. Ia TIDAK mendekompilasi dan TIDAK memahami makna kode — ia mencocokkan
bentuk teks. Itu sebabnya ia cepat, sekaligus bisa keliru (mis. UUID biasa
disangka kunci API karena bentuknya mirip).

Empat tahap: extract_apk -> find_artifacts -> analyze_artifact -> (skoring).
============================================================================
"""

import argparse
import base64
import datetime
import json
import math
import re
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ==========================================================================
# KONSTANTA
# ==========================================================================

# --- Hermes bytecode -------------------------------------------------------
# ISTILAH — Hermes bytecode : format biner hasil kompilasi kode React Native
#   modern. Bukan JavaScript teks. Seluruh string disimpan berjejalan pada satu
#   blok tanpa pemisah, sehingga regex byte mentah akan menangkap sebuah string
#   beserta ekor string tetangganya. Angka di bawah dipakai untuk mengurai
#   tabel string Hermes agar tiap string terpotong pada batas aslinya.
HERMES_MAGIC = 0x1F1903C103BC1FC6   # 8 byte penanda di awal berkas Hermes
HERMES_HEADER_SIZE = 128            # ukuran header untuk bytecode versi 96

# --- Skoring risiko --------------------------------------------------------
# Ambang penerjemahan skor -> level. Diperiksa dari yang tertinggi lebih dulu.
RISK_THRESHOLDS = ((90, "CRITICAL"), (70, "HIGH"), (50, "MEDIUM"))
MAX_BASE64_DECODES = 50                 # batasi dekode Base64 demi kinerja
MAX_FILE_SIZE = 300 * 1024 * 1024       # lewati artefak > 300 MB

# --- Magic byte berkas biner ----------------------------------------------
# ISTILAH — Magic byte : beberapa byte pertama yang menandai jenis berkas.
#   Dipakai pada blok Base64 untuk MENOLAK aset biner (gambar/arsip) yang
#   sering salah tuduh sebagai "rahasia terdekode". Perbaikan ini lahir dari
#   validasi APK nyata: 9 gambar PNG/WEBP sempat dianggap rahasia.
BINARY_MAGIC = (
    b"\x89PNG\r\n\x1a\n",   # PNG
    b"\xff\xd8\xff",        # JPEG
    b"GIF87a", b"GIF89a",   # GIF
    b"RIFF",                # WEBP / WAV / AVI
    b"\x1f\x8b",            # gzip
    b"PK\x03\x04",          # zip / jar / apk
    b"BZh",                 # bzip2
    b"%PDF",                # PDF
    b"\x7fELF",             # ELF (executable Linux/Android native)
    b"OggS",                # OGG
)

# --- Pemisahan endpoint aplikasi vs URL dokumentasi library ----------------
# Masalah dari validasi APK nyata: 1 backend asli tenggelam di antara puluhan
# URL dokumentasi library (momentjs, reactnavigation, github...). Host di bawah
# adalah host dokumentasi/library yang PASTI bukan backend aplikasi, sehingga
# URL padanya dikecualikan dari daftar "app_endpoints".
LIBRARY_HOSTS = (
    "momentjs.com", "reactnavigation.org", "reactnative.dev", "react.dev",
    "github.com", "githubusercontent.com", "expo.dev", "exp.host", "expo.io",
    "swmansion.com", "cloudflare.com", "w3.org", "schema.org", "schemas.android.com",
    "npmjs.com", "yarnpkg.com", "unpkg.com", "jsdelivr.net", "fb.me", "fb.com",
    "facebook.com", "mozilla.org", "apache.org", "eclipse.org", "json.org",
    "unicode.org", "crbug.com", "dev.to", "medium.com", "stackoverflow.com",
    "xmlpull.org", "xml.org", "adobe.com",
    "googleapis.com", "gstatic.com", "google.com", "googleusercontent.com",
    "crashlytics.com", "doubleclick.net", "android.com",
)

TEMPLATE_HOST_RE = re.compile(r"%[sd@]|\{|\$")

# TEMPLATE_HOST_RE menolak URL yang host-nya masih berupa TEMPLAT, misalnya
# "http://%s/status" milik dev-server Metro atau host ber-placeholder "{host}".
# Host semacam itu baru diisi saat aplikasi berjalan, sehingga bukan alamat
# backend yang benar-benar terekspos di dalam berkas.
# Sebuah URL dianggap "endpoint aplikasi" bila host-nya BUKAN host library DAN
# jalurnya memuat penanda API seperti /api, /apimobile, /v1, /graphql, dst.
APP_ENDPOINT_PATH = re.compile(
    r"/(?:api|apimobile|v[0-9]+|graphql|oauth|rest|auth|mobile)(?:/|$)", re.IGNORECASE
)

# Pola nama SCOPE paket npm huruf-kecil (mis. "@react-navigation", "@babel").
# ISTILAH — npm scope : awalan "@..." pada nama paket JavaScript. Pola kunci
#   penyimpanan React Native (AsyncStorage) juga diawali "@" (mis.
#   "@app:auth_token"), sehingga nama paket npm sempat salah tuduh sebagai kunci
#   penyimpanan. Kunci penyimpanan asli biasanya memakai ":" atau huruf besar;
#   paket npm berupa scope huruf-kecil-strip atau memuat "/". NPM_SCOPE_RE dan
#   uji "/" dipakai untuk membuang paket npm dari storage_keys.
NPM_SCOPE_RE = re.compile(r"@[a-z][a-z0-9-]*")

# --- Detektor kredensial ---------------------------------------------------
# Kamus: nama detektor -> (pola, bobot risiko 50-100).
# ISTILAH — Bobot : mencerminkan tingkat kepastian + dampak. Kunci privat dan
#   kunci AWS diberi 100 (spesifik & berdampak besar); sertifikat 50 (sering
#   wajar). Catatan desain penting terlihat pada dua entri:
#     * "Mailgun API Key" memakai [0-9a-f]{32} (HEKSADESIMAL, format asli
#       Mailgun) — bukan [0-9a-zA-Z]{32} yang longgar. Pola longgar sempat
#       menangkap identifier JavaScript ter-minify pada APK nyata.
#     * "Heroku API Key" DIDETEKSI BERBASIS KONTEKS: kunci Heroku berbentuk
#       UUID biasa tanpa awalan khas, sehingga secara bentuk mustahil dibedakan
#       dari request-id. UUID hanya diterima bila didahului label "heroku".
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

# 15 kategori hasil. "app_endpoints" adalah penyaringan dari "urls".
RESULT_CATEGORIES = (
    "urls", "app_endpoints", "websockets", "ip_addresses", "api_paths",
    "action_endpoints", "api_keys_and_tokens", "sensitive_headers",
    "env_variables", "storage_keys", "db_connections", "flutter_ipc",
    "android_components", "decoded_secrets", "keywords_found",
)

# Indikator yang, bila muncul dalam hasil dekode Base64, menandai kandidat
# rahasia yang layak disimpan.
# Nama-nama ringkasan; dipakai pula saat artefak dilewati agar bentuk hasil sama.
SUMMARY_FIELDS = (
    "total_urls", "total_app_endpoints", "total_api_paths", "total_tokens_found",
    "total_db_connections", "total_decoded_secrets", "total_keywords",
)

SENSITIVE_INDICATORS = (
    "http", "api", "key", "token", "secret", "pass", "auth", "admin",
    "login", "bearer", "jdbc", "mongodb",
)

# Kata kunci indikatif; kehadirannya dicatat sebagai konteks (bukan tuduhan).
KEYWORDS = [
    b"login", b"logout", b"register", b"auth", b"user", b"profile",
    b"upload", b"download", b"payment", b"admin", b"graphql", b"websocket",
    b"password", b"secret", b"token", b"private_key", b"staging", b"debug",
    b"flutter", b"dart", b"obfuscate", b"proguard", b"keystore", b"jks",
    b"encrypt", b"decrypt", b"certificate", b"ssl", b"tls", b"oauth",
    b"session", b"cookie", b"csrf", b"xss", b"injection", b"root",
    b"su ", b"magisk", b"frida", b"xposed",
]


# ==========================================================================
# UTILITAS
# ==========================================================================

def calculate_shannon_entropy(data: bytes) -> float:
    """Menghitung ENTROPI SHANNON — ukuran keacakan data.

    ISTILAH — Entropi Shannon : makin acak data, makin tinggi nilainya.
      Rumus: H = -Σ p(x)·log2 p(x), dengan p(x) = frekuensi tiap byte.
      Guna: memilah kredensial sungguhan (acak -> entropi tinggi) dari
      placeholder seperti "aaaaaaaa..." (berulang -> entropi ~0).
    """
    if not data:
        return 0.0
    counter = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counter.values())


# ==========================================================================
# TAHAP 1 — EKSTRAKSI APK (dengan pengaman Zip Slip)
# ==========================================================================

def extract_apk(apk_path: Path, output_dir: Path) -> None:
    """Membuka APK sebagai ZIP dan mengekstrak seluruh isinya.

    Direktori tujuan sengaja baru dibuat SESUDAH arsip terbukti valid dan
    seluruh entrinya lolos pemeriksaan jalur. Dengan begitu berkas yang bukan
    ZIP tidak meninggalkan direktori hasil kosong.

    ISTILAH — Zip Slip : kerentanan ketika entri arsip bernama "../../berkas"
      diekstrak tanpa pemeriksaan sehingga berkas tertulis DI LUAR direktori
      tujuan. Uji membuktikan zipfile.extractall() Python sudah menetralkannya,
      NAMUN keamanan itu bergantung pada perilaku internalnya. Pemeriksaan
      jalur eksplisit di bawah adalah DEFENSE-IN-DEPTH: setiap entri wajib
      jatuh di dalam direktori tujuan; yang melanggar ditolak tegas.
    """
    output_root = output_dir.resolve()
    with zipfile.ZipFile(apk_path, "r") as apk:
        for member in apk.namelist():
            target = (output_root / member).resolve()
            # Bila 'target' tidak berada di dalam 'output_root', tolak.
            if target != output_root and output_root not in target.parents:
                raise ValueError(
                    f"Entri APK menulis di luar direktori tujuan (Zip Slip): {member!r}"
                )
        output_dir.mkdir(parents=True, exist_ok=True)
        apk.extractall(output_dir)


# ==========================================================================
# PENGURAI HERMES BYTECODE
# ==========================================================================

def extract_hermes_strings(raw: bytes) -> Optional[List[str]]:
    """Mengekstrak string BERSIH dari bundle Hermes bytecode.

    Mengapa perlu: pada Hermes seluruh string berjejalan tanpa pemisah, jadi
    regex byte mentah menangkap endpoint + ekor string berikutnya
    (mis. ".../verify-otp/__setInternalHeight"). Hermes menyimpan sebuah TABEL
    STRING berisi (offset, panjang) tiap string; membacanya memungkinkan tiap
    string dipotong tepat pada batasnya.

    Mengembalikan daftar string bila berkas Hermes dapat diurai; None agar
    pemanggil KEMBALI ke pemindaian byte mentah (aman untuk versi tak dikenal).

    Tata letak berkas (bytecode v96), tiap bagian diselaraskan ke kelipatan 4:
      header(128) -> function headers -> string kinds -> identifier hashes ->
      tabel string kecil -> tabel string overflow -> blok penyimpanan string
    """
    # Tolak cepat bila terlalu pendek atau magic byte tak cocok.
    if len(raw) < HERMES_HEADER_SIZE or struct.unpack_from("<Q", raw, 0)[0] != HERMES_MAGIC:
        return None
    # u32(offset): baca integer 32-bit little-endian pada posisi tersebut.
    def u32(offset: int) -> int:
        return struct.unpack_from("<I", raw, offset)[0]

    # align4: bulatkan ke atas ke kelipatan 4 (aturan penyelarasan Hermes).
    def align4(value: int) -> int:
        return (value + 3) & ~3

    try:
        # Cacah tiap tabel dibaca dari header (offset tetap per struktur Hermes).
        function_count, string_kind_count, identifier_count = u32(40), u32(44), u32(48)
        string_count, overflow_count, storage_size = u32(52), u32(56), u32(60)

        off = align4(HERMES_HEADER_SIZE + function_count * 16)  # lewati func headers
        off = align4(off + string_kind_count * 4)               # lewati string kinds
        off = align4(off + identifier_count * 4)                # lewati identifier hashes
        small_tbl = off                                         # -> tabel string kecil
        off = align4(off + string_count * 4)
        overflow_tbl = off                                      # -> tabel overflow
        off = align4(off + overflow_count * 8)
        storage = off                                           # -> blok penyimpanan

        # Bila perhitungan meleset (mis. versi beda), batalkan dengan aman.
        if storage + storage_size > len(raw):
            return None

        strings = []
        for i in range(string_count):
            entry = u32(small_tbl + i * 4)
            # Tiap entri 32-bit mengemas: bit0=isUTF16, bit1-23=offset, bit24-31=panjang.
            is_utf16 = entry & 1
            s_off = (entry >> 1) & 0x7FFFFF
            s_len = (entry >> 24) & 0xFF
            # Panjang 0xFF menandai entri "overflow" (string > 254 byte):
            # offset & panjang sebenarnya diambil dari tabel overflow.
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
        # Format tak terduga -> kembalikan None, biar dipindai sebagai byte mentah.
        return None


# ==========================================================================
# TAHAP 2 — IDENTIFIKASI ARTEFAK
# ==========================================================================

def find_artifacts(root_dir: Path) -> List[Path]:
    """Memilih hanya berkas pemuat kode dari hasil ekstraksi.

    Pemilihan disesuaikan kerangka kerja:
      React Native -> *.bundle, *.jsbundle
      Kotlin/Java  -> *.dex
      Flutter      -> libflutter.so, libapp.so, *_blob.bin, *.dart
      Semua        -> AndroidManifest.xml
    Fallback: bila tak satu pun cocok, ambil 5 berkas TERBESAR (berkas terbesar
    dalam APK hampir selalu kode, bukan aset).
    """
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
    # sorted(set(...)) : buang duplikat & jadikan urutan deterministik.
    return sorted(set(artifacts))


def classify_app_endpoint(url: str) -> bool:
    """True bila URL adalah endpoint milik aplikasi (bukan URL dokumentasi library).

    Dua syarat: host BUKAN salah satu LIBRARY_HOSTS, DAN jalur memuat penanda
    API (APP_ENDPOINT_PATH). Ini memisahkan permukaan API asli aplikasi —
    bagian yang sensitif — dari puluhan tautan dokumentasi library.
    """
    host_match = re.match(r"[a-z]+://([^/]+)", url, re.IGNORECASE)
    if not host_match:
        return False
    host = host_match.group(1).lower()
    if TEMPLATE_HOST_RE.search(host):
        return False
    if any(lib in host for lib in LIBRARY_HOSTS):
        return False
    return bool(APP_ENDPOINT_PATH.search(url[host_match.end():]))


# ==========================================================================
# TAHAP 3 — ANALISIS POLA (inti perangkat)
# ==========================================================================

def analyze_artifact(artifact_path: Path) -> Dict[str, Any]:
    """Menyapu satu artefak dengan seluruh pola dan menyusun hasil + skor risiko."""
    file_size = artifact_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        # Artefak raksasa dilewati, tetapi bentuk hasilnya tetap lengkap agar
        # pemanggil tidak perlu memperlakukannya sebagai kasus khusus.
        return {
            "file": artifact_path.name,
            "size_kb": round(file_size / 1024, 2),
            "error": "File >300MB, dilewati.",
            "risk_level": "SKIPPED",
            "risk_score": 0,
            "summary": {key: 0 for key in SUMMARY_FIELDS},
        }

    # Baca SELURUH artefak sebagai byte (bukan teks) agar berkas biner tak rusak.
    raw_bytes = artifact_path.read_bytes()

    # Bila Hermes: ganti korpus dengan string bersih (dipisah newline agar regex
    # tak menyeberang batas antar-string). Bila bukan/gagal: tetap byte mentah.
    hermes_strings = extract_hermes_strings(raw_bytes)
    is_hermes = hermes_strings is not None
    if is_hermes:
        raw_bytes = "\n".join(hermes_strings).encode("utf-8", "ignore")

    # Semua hasil ditampung dalam set() agar duplikat otomatis hilang.
    results: Dict[str, set] = {category: set() for category in RESULT_CATEGORIES}

    # finding_weights: bobot PER TEMUAN UNIK. Kunci = string temuan, sehingga
    # temuan yang berulang (token sama muncul puluhan kali) dihitung SEKALI.
    # Skor akhir dihitung dari kumpulan ini (bagian N), bukan per kecocokan.
    finding_weights: Dict[str, int] = {}

    # --- A. URL & websocket + penyaringan app_endpoints -------------------
    # \x00-\x20 dan \x7f (byte NUL + karakter kontrol) SENGAJA dikeluarkan dari
    # kelas karakter. Alasannya batas string: pada artefak biner seperti .dex,
    # string disimpan berjejalan dan dipisahkan byte NUL beserta byte panjang.
    # Tanpa pengecualian ini satu kecocokan akan menelan string-string
    # tetangganya menjadi satu blob panjang. URL sendiri memang tidak pernah
    # boleh memuat karakter kontrol (RFC 3986), jadi tidak ada URL sah yang
    # hilang. Untuk bundel Hermes efeknya nihil karena string di sana sudah
    # dipisah baris baru lebih dulu oleh extract_hermes_strings().
    for url in re.findall(rb"https?://[^\s\x00-\x20\x7f\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        cleaned = url.decode("utf-8", errors="ignore").rstrip(".,);:]")
        if len(cleaned) > 10:
            results["urls"].add(cleaned)
            if classify_app_endpoint(cleaned):
                results["app_endpoints"].add(cleaned)
    for ws in re.findall(rb"wss?://[^\s\x00-\x20\x7f\"'`\\<>\(\)\{\}\[\]]+", raw_bytes):
        results["websockets"].add(ws.decode("utf-8", errors="ignore").rstrip(".,);:]"))

    # --- B. Alamat IPv4 (kecualikan alamat lokal/khusus) ------------------
    for ip in re.findall(
        rb"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        raw_bytes,
    ):
        ip_str = ip.decode("utf-8", errors="ignore")
        if not ip_str.startswith(("127.", "0.0.0.0", "255.255.255.", "10.0.2.")):
            results["ip_addresses"].add(ip_str)

    # --- C. Path API ------------------------------------------------------
    # Batas kiri/kanan menerima tanda kutip ATAU batas baris, agar path
    # standalone pada bundle Hermes ikut tertangkap (bukan hanya literal
    # berkutip pada JavaScript teks biasa).
    for path in re.findall(
        rb"(?:[\"']|^|\n)(/(?:api|apimobile|v[0-9]+|graphql|rest|auth|user|admin|wp-json|oauth|token|session|upload|download|payment|checkout)[a-zA-Z0-9._/\-]*)(?:[\"']|$|\n)",
        raw_bytes,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        results["api_paths"].add(path.decode("utf-8", errors="ignore").rstrip("/"))

    # --- D. Action endpoints (nama aksi + pasangan kunci-nilai) -----------
    action_patterns = (
        rb"[\"']((?:get|post|put|delete|check|fetch|update|create|remove|detail|user|auth|list|verify|validate|reset|confirm|send|receive)[a-zA-Z0-9_-]{3,50})[\"']",
        rb"\b(?:[a-zA-Z0-9_-]{0,20}(?:checkout|checkin|detail|user|profile|dashboard|settings|notification)[a-zA-Z0-9_-]{0,20})\b",
    )
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

    # --- E. Token & kredensial (menaikkan skor) ---------------------------
    for name, (pattern, weight) in TOKEN_PATTERNS.items():
        for match in re.findall(pattern, raw_bytes):
            # Penyaringan entropi HANYA untuk Generic API Key (polanya longgar).
            if name == "Generic API Key" and calculate_shannon_entropy(match) < 3.8:
                continue
            finding_key = f"[{name}] {match.decode('utf-8', errors='ignore')}"
            results["api_keys_and_tokens"].add(finding_key)
            finding_weights[finding_key] = weight

    # --- F. Header sensitif ------------------------------------------------
    for h in re.findall(
        rb"[\"'](Authorization|X-API-Key|X-Auth-Token|X-Access-Token|X-Forwarded-For|X-Real-IP|Bearer\s+[A-Za-z0-9\-._~+/]+=*)[\"']",
        raw_bytes,
        flags=re.IGNORECASE,
    ):
        results["sensitive_headers"].add(h.decode("utf-8", errors="ignore"))

    # --- G. Variabel lingkungan (prefiks kerangka kerja) ------------------
    for env in re.findall(rb"\b(?:REACT_APP_|EXPO_PUBLIC_|NEXT_PUBLIC_|APP_|FLUTTER_|VITE_|NUXT_)[A-Z0-9_]{3,}\b", raw_bytes):
        results["env_variables"].add(env.decode("utf-8", errors="ignore"))

    # --- H. Kunci penyimpanan lokal (buang nama paket npm) ----------------
    for key in re.findall(rb"[\"'](@[a-zA-Z0-9_:/.\-]+)[\"']", raw_bytes):
        key_str = key.decode("utf-8", errors="ignore")
        # Lewati bila berbentuk paket npm ("@scope/pkg" atau "@scope" huruf kecil).
        if "/" in key_str or NPM_SCOPE_RE.fullmatch(key_str):
            continue
        results["storage_keys"].add(key_str)
    for key in re.findall(rb"[\"']((?:shared_preferences_|flutter\.secure_storage|AsyncStorage_)[a-zA-Z0-9_]+)[\"']", raw_bytes):
        results["storage_keys"].add(key.decode("utf-8", errors="ignore"))

    # --- I. String koneksi basis data (menaikkan skor, bobot 95) ----------
    for db in re.findall(rb"(?i)(?:jdbc:(?:mysql|postgresql|oracle|sqlserver)://[^\s\"']{10,}|mongodb(?:\+srv)?://[^\s\"']{10,}|redis://[^\s\"']{10,}|amqp://[^\s\"']{10,})", raw_bytes):
        db_str = db.decode("utf-8", errors="ignore")
        results["db_connections"].add(db_str)
        finding_weights[f"[db] {db_str}"] = 95

    # --- J. Flutter IPC (jalur komunikasi antar-proses Flutter) -----------
    for ch in re.findall(rb"[\"']((?:MethodChannel|EventChannel|BasicMessageChannel)\([\"'][^\"']+[\"']\))[\"']", raw_bytes):
        results["flutter_ipc"].add(ch.decode("utf-8", errors="ignore"))
    for inv in re.findall(rb"[\"']([a-zA-Z_]+(?:Channel|Plugin|Handler))[\"']", raw_bytes):
        inv_str = inv.decode("utf-8", errors="ignore")
        if len(inv_str) > 6:
            results["flutter_ipc"].add(inv_str)

    # --- K. Komponen Android & permission ---------------------------------
    for comp in re.findall(rb"[\"']((?:com|org|net|io)\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_.]+(?:Activity|Service|Receiver|Provider|Fragment))[\"']", raw_bytes):
        results["android_components"].add(comp.decode("utf-8", errors="ignore"))
    for perm in re.findall(rb"[\"'](android\.permission\.[A-Z_]+)[\"']", raw_bytes):
        results["android_components"].add(perm.decode("utf-8", errors="ignore"))

    # --- L. Lapisan anti-obfuskasi: dekode Base64 (menaikkan skor, 70) ----
    # ISTILAH — Obfuskasi : menyembunyikan data (mis. rahasia dienkode Base64
    #   dulu). Blok ini mencoba mendekode kandidat Base64, menolak aset biner
    #   (magic byte), lalu menyimpan yang memuat indikator sensitif.
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
        if decoded_bytes.startswith(BINARY_MAGIC):   # tolak gambar/arsip
            continue
        decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
        if any(ind in decoded_str.lower() for ind in SENSITIVE_INDICATORS):
            secret_str = decoded_str[:200]
            results["decoded_secrets"].add(secret_str)
            finding_weights[f"[decoded] {secret_str}"] = 70
            decoded_count += 1

    # --- M. Kata kunci indikatif (konteks, bukan tuduhan) -----------------
    for kw in KEYWORDS:
        if re.search(rb"\b" + kw + rb"\b", raw_bytes, re.IGNORECASE):
            results["keywords_found"].add(kw.decode("utf-8", errors="ignore").strip())

    # --- N. Klasifikasi risiko: SEVERITY + BREADTH ------------------------
    # ISTILAH — Severity : bobot temuan TERPARAH (0-100). Satu kunci AWS sudah
    #   cukup menaikkan risiko tanpa menunggu banyak temuan.
    # ISTILAH — Breadth  : bonus kecil bila temuan BERAGAM, DIBATASI +20, agar
    #   banyaknya temuan tak mendominasi tingkat risiko.
    # Karena finding_weights berbasis temuan unik, duplikat tak menggelembung.
    # Skor terikat 0-120. Model ini menggantikan model lama yang akumulatif
    # tanpa batas (yang membuat APK besar otomatis CRITICAL).
    severity = max(finding_weights.values(), default=0)
    breadth_bonus = min(max(len(finding_weights) - 1, 0), 5) * 4
    risk_score = severity + breadth_bonus
    risk_level = "LOW"
    for threshold, level in RISK_THRESHOLDS:
        if risk_score >= threshold:
            risk_level = level
            break

    # Susun hasil. **{...} membongkar tiap kategori menjadi daftar terurut.
    return {
        "file": artifact_path.name,
        "size_kb": round(file_size / 1024, 2),
        "is_hermes": is_hermes,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "summary": {
            "total_urls": len(results["urls"]),
            "total_app_endpoints": len(results["app_endpoints"]),
            "total_api_paths": len(results["api_paths"]),
            "total_tokens_found": len(results["api_keys_and_tokens"]),
            "total_db_connections": len(results["db_connections"]),
            "total_decoded_secrets": len(results["decoded_secrets"]),
            "total_keywords": len(results["keywords_found"]),
        },
        **{key: sorted(value) for key, value in results.items()},
    }


# ==========================================================================
# PIPELINE UTAMA (baris perintah)
# ==========================================================================

def analyze_apk(
    apk_path: Path,
    on_start: Optional[Callable[[str, float], None]] = None,
    on_result: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Optional[Tuple[Dict[str, Any], Path]]:
    """Menjalankan seluruh pipeline atas satu APK: ekstrak -> pilih artefak ->
    analisis -> urutkan -> tulis JSON.

    Fungsi inilah yang dipakai bersama oleh mode baris perintah (`main()`) dan
    antarmuka bermenu (`apk_cli.py`), sehingga alur analisis hanya ditulis satu
    kali. Dua parameter callback bersifat opsional dan hanya untuk menampilkan
    kemajuan: `on_start` dipanggil sebelum sebuah artefak dipindai, `on_result`
    setelahnya. Mengembalikan pasangan (laporan, path JSON), atau None bila
    tidak ada artefak yang dapat dianalisis.
    """
    # Nama folder keluaran memuat timestamp agar tiap analisis tak saling timpa.
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"{apk_path.stem}_analysis_{timestamp}")
    extract_dir = output_dir / "extracted_files"

    extract_apk(apk_path, extract_dir)
    artifacts = find_artifacts(extract_dir)
    if not artifacts:
        return None

    report: Dict[str, Any] = {
        "metadata": {
            "target_apk": apk_path.name,
            "analysis_timestamp": timestamp,
            "total_artifacts_found": len(artifacts),
        },
        "artifacts": {},
    }
    for artifact in artifacts:
        relative_path = str(artifact.relative_to(extract_dir))
        if on_start:
            on_start(relative_path, artifact.stat().st_size / 1024)
        result = analyze_artifact(artifact)
        report["artifacts"][relative_path] = result
        if on_result:
            on_result(relative_path, result)

    # Urutkan artefak menurun berdasar skor agar yang paling berisiko di atas.
    report["artifacts"] = dict(
        sorted(report["artifacts"].items(), key=lambda x: x[1].get("risk_score", 0), reverse=True)
    )

    output_json = output_dir / "reverse_results.json"
    output_json.write_text(
        json.dumps(report, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    return report, output_json


def main() -> None:
    """Titik masuk CLI: python3 apk_analyzer.py <target.apk>"""
    parser = argparse.ArgumentParser(description="Multi-framework APK static analyzer")
    parser.add_argument("apk_path", type=Path, help="Path ke file .apk target")
    args = parser.parse_args()

    apk_path = args.apk_path.resolve()
    if not apk_path.is_file():
        print(f"[!] Error: File '{apk_path}' tidak ditemukan.")
        sys.exit(1)

    print(f"[*] Target: {apk_path.name}")
    print("[*] Mengekstrak APK lalu memindai artefak (RN / Kotlin / Flutter)...")

    # Dua fungsi kecil ini hanya menampilkan kemajuan ke layar; seluruh logika
    # analisis berada di analyze_apk().
    def on_start(relative_path: str, size_kb: float) -> None:
        print(f"[*] Menganalisis: {relative_path} ({size_kb:.1f} KB)")

    def on_result(relative_path: str, result: Dict[str, Any]) -> None:
        # Artefak yang dilewati tidak memiliki temuan untuk ditampilkan.
        if "error" in result:
            print(f"    -> Dilewati: {result['error']}")
            return
        summary = result["summary"]
        print(
            f"    -> Risiko: {result['risk_level']}"
            f" | Token: {summary['total_tokens_found']}"
            f" | Endpoint: {summary['total_app_endpoints']}"
        )

    try:
        outcome = analyze_apk(apk_path, on_start=on_start, on_result=on_result)
        if outcome is None:
            print("[!] Tidak ditemukan artefak untuk dianalisis.")
            sys.exit(1)
        _, output_json = outcome
        print("\n[+] Analisis selesai.")
        print(f"[+] Hasil tersimpan di: {output_json.resolve()}")

    # Hanya galat yang MEMANG bisa terjadi pada masukan pengguna yang ditangkap:
    # berkas bukan ZIP, entri Zip Slip (ValueError), dan galat baca/tulis berkas.
    # Galat lain sengaja dibiarkan naik apa adanya karena itu bug yang perlu
    # terlihat. Kode keluar 1 supaya kegagalan terbaca oleh skrip pemanggil.
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        print(f"[!] Gagal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

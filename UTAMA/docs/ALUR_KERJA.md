# Dokumentasi Alur Kerja: APK Static Analyzer

Dokumen ini menjelaskan cara kerja `apk_analyzer.py` secara menyeluruh, dari APK
masuk sampai laporan JSON keluar, ditutup dengan penerapannya terhadap aplikasi
MyErpskrip. Ditulis sebagai bahan Bab Perancangan serta Bab Hasil dan Pembahasan
laporan Kerja Praktik.

Seluruh rujukan fungsi dan blok merujuk pada berkas `apk_analyzer.py` di
direktori proyek.

---

## 1. Ringkasan dalam Satu Paragraf

Tool ini melakukan **analisis statis** terhadap berkas APK Android. Ia membuka APK
sebagai arsip ZIP, mencari berkas-berkas yang memuat kode aplikasi, lalu membaca
berkas tersebut sebagai **byte mentah** dan menyapunya dengan sekitar 25 pola
*regular expression* untuk menemukan URL, endpoint API, kredensial, dan indikator
sensitif lain. Temuan berkategori kredensial diringkas menjadi satu skor risiko
terikat, yang di akhir diterjemahkan menjadi level `LOW` sampai `CRITICAL`.

Analogi yang paling tepat: **tool ini adalah `grep` yang sangat terstruktur
terhadap isi APK.**

Konsekuensi penting dari pendekatan ini — dan ini harus dinyatakan jujur dalam
laporan:

- Tool **tidak** melakukan dekompilasi. Ia tidak pernah mengubah `.dex` menjadi
  kode Java yang terbaca.
- Tool **tidak** menjalankan aplikasi. Tidak ada analisis dinamis sama sekali.
- Tool **tidak** memahami semantik kode. Ia hanya mencocokkan bentuk teks.

Ketiga batasan itu yang membuatnya cepat dan tidak butuh dependensi eksternal,
sekaligus yang membuatnya bisa keliru — misalnya menyangka sebuah UUID biasa
sebagai kunci API, karena bentuk keduanya memang mirip dan pencocokan pola tidak
tahu bedanya.

---

## 2. Diagram Alur

```
             ┌──────────────┐
             │  target.apk  │
             └──────┬───────┘
                    │
        TAHAP 1     ▼
    ┌───────────────────────────────┐
    │ extract_apk()                 │   APK dibuka sebagai ZIP,
    │ zipfile.extractall            │   seluruh isi diekstrak
    └───────────────┬───────────────┘
                    │
        TAHAP 2     ▼
    ┌───────────────────────────────┐
    │ find_artifacts()              │   Pilih hanya berkas yang
    │ rglob per ekstensi            │   memuat kode / konfigurasi
    └───────────────┬───────────────┘
                    │
                    │  untuk setiap artefak
        TAHAP 3     ▼
    ┌───────────────────────────────┐
    │ analyze_artifact()            │   read_bytes() lalu
    │ 13 blok deteksi (A s.d. M)    │   ±25 regex disapukan
    └───────────────┬───────────────┘
                    │
        TAHAP 4     ▼
    ┌───────────────────────────────┐
    │ blok N: klasifikasi risiko    │   risk_score → risk_level
    └───────────────┬───────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  reverse_results.json │
        └───────────────────────┘
```

---

## 3. Tahap 1 — Ekstraksi APK

**Fungsi:** `extract_apk()`.

Berkas `.apk` sebenarnya adalah arsip ZIP biasa dengan struktur direktori yang
sudah dibakukan Android. Karena itu ekstraksinya cukup menggunakan modul standar
`zipfile`, tanpa pustaka pihak ketiga.

```python
with zipfile.ZipFile(apk_path, "r") as apk:
    apk.extractall(output_dir)
```

Fungsi sesungguhnya menambahkan pemeriksaan jalur sebelum `extractall` sebagai
pengaman Zip Slip; lihat bagian 9.3.

Isi khas sebuah APK setelah diekstrak:

| Path | Keterangan |
|---|---|
| `AndroidManifest.xml` | Deklarasi permission, activity, service (format binary XML) |
| `classes.dex` | Bytecode Dalvik hasil kompilasi Java/Kotlin |
| `resources.arsc` | Tabel sumber daya terkompilasi |
| `assets/` | Aset mentah — di sinilah bundel React Native berada |
| `lib/<abi>/` | Pustaka native `.so` — di sinilah kode Flutter berada |
| `res/` | Layout, gambar, string |
| `META-INF/` | Tanda tangan digital APK |

Hasil ekstraksi ditempatkan pada `<nama_apk>_analysis_<timestamp>/extracted_files/`.

---

## 4. Tahap 2 — Identifikasi Artefak

**Fungsi:** `find_artifacts()`.

Tidak semua berkas hasil ekstraksi perlu dianalisis. Gambar, layout, dan berkas
tanda tangan tidak memuat endpoint maupun kredensial. Tahap ini menyaring hanya
berkas yang berpotensi memuat logika aplikasi, dan pemilihannya disesuaikan
dengan kerangka kerja yang dipakai aplikasi target:

| Kerangka Kerja | Berkas yang dicari | Alasan |
|---|---|---|
| React Native | `*.bundle`, `*.jsbundle` | Kode JavaScript dibundel; versi modern berupa Hermes bytecode (lihat bagian 8.6) |
| Kotlin / Java | `*.dex` | Bytecode Dalvik; *string pool*-nya memuat literal dalam bentuk teks biasa |
| Flutter | `libflutter.so`, `libapp.so`, `*_blob.bin`, `*.dart` | Kode Dart dikompilasi ke biner native, namun literal string tetap tersimpan |
| Semua | `AndroidManifest.xml` | Memuat daftar permission dan komponen aplikasi |

Terdapat pula mekanisme **fallback**: apabila tidak satu pun pola di
atas cocok — misalnya aplikasi memakai kerangka kerja yang tidak dikenali — maka
tool mengambil **5 berkas terbesar** sebagai artefak. Dasar pemikirannya, berkas
terbesar dalam sebuah APK hampir selalu berisi kode, bukan aset.

Hasil akhirnya dinormalisasi dengan `sorted(list(set(...)))` agar tidak ada
artefak ganda dan urutannya deterministik.

---

## 5. Tahap 3 — Analisis Pola

**Fungsi:** `analyze_artifact()`. Ini adalah inti tool.

### 5.1 Prinsip Dasar

Artefak dibaca **seluruhnya sebagai byte**, bukan sebagai teks:

```python
raw_bytes = artifact_path.read_bytes()
```

Pilihan ini penting dan perlu dijelaskan di laporan. Berkas `.dex` dan `.so`
adalah berkas biner — bila dipaksa dibaca sebagai teks ber-encoding UTF-8, proses
akan gagal atau memotong data. Dengan membacanya sebagai byte, seluruh pola dapat
ditulis sebagai *bytes pattern* (`rb"..."`) dan diterapkan secara seragam pada
berkas teks maupun biner. Inilah yang memungkinkan satu mesin analisis yang sama
menangani React Native, Kotlin, dan Flutter sekaligus.

Terdapat pembatas ukuran: berkas di atas 300 MB dilewati untuk
mencegah pemakaian memori berlebih.

### 5.2 Tiga Belas Blok Deteksi

Analisis dibagi menjadi 13 blok berlabel A sampai M, masing-masing mengisi satu
kategori hasil. Seluruh hasil ditampung dalam `set` agar duplikat otomatis hilang.

| Blok | Kategori | Yang dicari |
|---|---|---|
| A | `urls`, `websockets` | `http://`, `https://`, `ws://`, `wss://` |
| A′ | `app_endpoints` | URL milik aplikasi, disaring dari URL pustaka (bagian 5.6) |
| B | `ip_addresses` | Alamat IPv4 |
| C | `api_paths` | Path seperti `/api/...`, `/v1/...`, `/graphql` |
| D | `action_endpoints` | Nama aksi (`getUser`, `checkoutOrder`) dan pasangan kunci-nilai `endpoint: "..."` |
| E | `api_keys_and_tokens` | 19 pola kredensial |
| F | `sensitive_headers` | `Authorization`, `X-API-Key`, `Bearer ...` |
| G | `env_variables` | `REACT_APP_`, `EXPO_PUBLIC_`, `NEXT_PUBLIC_`, `FLUTTER_`, dll. |
| H | `storage_keys` | Kunci penyimpanan lokal (`@app:token`, `shared_preferences_*`) |
| I | `db_connections` | `jdbc:`, `mongodb://`, `redis://`, `amqp://` |
| J | `flutter_ipc` | `MethodChannel`, `EventChannel`, nama `*Handler` / `*Plugin` |
| K | `android_components` | Activity/Service/Receiver dan `android.permission.*` |
| L | `decoded_secrets` | Rahasia yang tersembunyi di balik enkode Base64 |
| M | `keywords_found` | 40 kata kunci indikatif (`password`, `frida`, `keystore`, dll.) |

Klasifikasi risiko (blok N) tidak mengisi kategori temuan, melainkan mengubah
temuan menjadi skor dan level; dibahas di bagian 6.

### 5.3 Blok E — Deteksi Kredensial

Blok ini yang paling menentukan skor risiko. Strukturnya berupa kamus: nama
detektor dipetakan ke pasangan (pola, bobot risiko).

```python
TOKEN_PATTERNS = {
    "AWS Access Key": (rb"(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}", 100),
    "Google API Key": (rb"AIza[0-9A-Za-z\-_]{35}", 90),
    ...
}
```

Terdapat 19 detektor dengan bobot 50 sampai 100. Bobot mencerminkan tingkat
kepastian sekaligus dampak: kunci privat dan kunci AWS diberi bobot 100 karena
polanya spesifik dan dampak kebocorannya besar, sementara blok sertifikat diberi
bobot 50 karena keberadaannya sering wajar dan tidak selalu berbahaya.

**Penyaringan entropi.** Khusus detektor `Generic API Key`, hasil pencocokan masih
disaring dengan **entropi Shannon** (blok E). Pola generik seperti
`api_key = "..."` terlalu longgar dan akan banyak menangkap nilai *placeholder*.
Entropi mengukur keacakan karakter: kredensial sungguhan bersifat acak sehingga
entropinya tinggi, sedangkan placeholder seperti `"aaaaaaaaaaaaaaaaaaaa"` sangat
berulang sehingga entropinya mendekati nol. Ambang yang dipakai adalah 3.8.

Perhitungannya ada pada `calculate_shannon_entropy()`:

```
H = -Σ p(x) · log₂ p(x)
```

dengan `p(x)` adalah frekuensi kemunculan tiap byte. Penyaring ini bekerja dua
arah: nilai berpola berulang seperti `AKIAAAAAAAAAAAAAAAAA` ditolak karena
entropinya mendekati nol, sementara nilai acak sungguhan tetap lolos dan
terdeteksi.

**Deteksi berbasis bentuk vs berbasis konteks.** Sebagian besar detektor bekerja
berbasis **bentuk**, sebab kredensial yang dicarinya memiliki awalan khas: `AKIA`
pada AWS, `AIza` pada Google, `ghp_` pada GitHub. Bentuk semacam itu praktis
tidak mungkin muncul secara kebetulan.

Sebagian kredensial tidak seberuntung itu. Kunci API Heroku, misalnya, berbentuk
UUID biasa tanpa awalan apa pun — bentuknya identik dengan *request-id* maupun
*trace-id* yang lazim bertaburan di dalam aplikasi. Mendeteksinya berbasis bentuk
berarti menuduh setiap UUID sebagai kredensial.

Untuk kasus seperti ini dipakai deteksi berbasis **konteks**: nilai hanya
dianggap kredensial apabila didahului label yang bermakna.

| | Berbasis bentuk | Berbasis konteks |
|---|---|---|
| Dasar penerimaan | Rupa nilainya | Label yang mendahuluinya |
| Contoh | `AKIA` + 16 karakter | UUID yang didahului kata "heroku" |
| Dipakai bila | Pola khas dan tidak ambigu | Pola generik dan mudah tertukar |

Prinsip yang sama menuntun dua keputusan lain. Pola Mailgun ditulis
`key-[0-9a-f]{32}\b` mengikuti format heksadesimal yang sesungguhnya — bukan
`[0-9a-zA-Z]{32}` yang lebih longgar — karena bentuk longgar itu akan menangkap
identifier JavaScript hasil *minify*. Pada blok H, kandidat kunci penyimpanan
yang mengandung `/` atau berbentuk *scope* npm huruf kecil dibuang lewat
`NPM_SCOPE_RE`, sebab nama paket seperti `@react-navigation/native` berbentuk
sama persis dengan kunci penyimpanan lokal.

### 5.4 Blok L — Lapisan Anti-Obfuskasi

Blok ini menangani kasus rahasia yang tidak disimpan sebagai teks biasa,
melainkan dienkode Base64 lebih dahulu. Alurnya bertingkat:

1. Cari untai yang berbentuk Base64 (minimal 32 karakter).
2. Coba dekode dengan `validate=True`; yang gagal diabaikan.
3. Hitung entropi hasil dekode; bila di bawah 3.5, abaikan — kemungkinan besar
   hasil dekode yang kebetulan valid namun tidak bermakna.
4. Tolak bila hasil dekode diawali *magic byte* berkas biner (`\x89PNG`,
   `RIFF`/WEBP, JPEG, dan seterusnya) melalui daftar `BINARY_MAGIC`. Aplikasi
   modern lazim menanamkan gambar sebagai untai Base64 di dalam kodenya, dan
   potongan acak dari data gambar mudah kebetulan memuat indikator sensitif.
5. Periksa apakah hasil dekode memuat indikator sensitif (`http`, `token`,
   `secret`, `jdbc`, dan sebagainya).
6. Bila ya, simpan 200 karakter pertama dan tambahkan 70 ke skor risiko.

Terdapat pembatas 50 hasil dekode per artefak demi menjaga kinerja.

### 5.5 Penanganan Bundel Hermes

Aplikasi React Native modern tidak mengemas kode sebagai JavaScript teks,
melainkan sebagai **Hermes bytecode** — berkas biner tempat seluruh untai teks
disimpan berjejalan pada satu blok penyimpanan tanpa pemisah antar-untai:

```
...https://api.contoh.id/apimobile/auth/verify-otp/__setInternalHeightchevron...
   └──────────── untai 1 ─────────────┘└─ untai 2 ─┘└──── untai 3 ─────┘
```

Pemindaian byte mentah tidak mengetahui batas antar-untai, sehingga pola URL akan
menangkap sebuah endpoint beserta ekor untai berikutnya
(`.../verify-otp/__setInternalHeight`). Alamatnya ada, tetapi ternoda dan tidak
dapat dipakai.

Hermes sendiri menyimpan **tabel untai teks** berisi pasangan (offset, panjang)
untuk tiap untai. Fungsi `extract_hermes_strings()` membaca header Hermes,
menghitung letak tabel dan blok penyimpanan, lalu memotong tiap untai tepat pada
batas aslinya. Bila artefak dikenali sebagai bundel Hermes, korpus pemindaian
diganti dengan untai-untai bersih ini — dipisah baris baru agar pola tidak
menyeberang batas. Bila bukan Hermes atau gagal diurai, pemindaian kembali ke
byte mentah.

Struktur berkas yang diurai (versi bytecode 96):

| Bagian | Isi |
|---|---|
| Header (128 byte) | magic `0x1F1903C103BC1FC6`, versi, dan cacah tiap tabel |
| Tabel untai kecil | `stringCount` entri; tiap entri 32-bit mengemas offset (23 bit) + panjang (8 bit) |
| Tabel untai overflow | untuk untai yang panjangnya melebihi 255 byte |
| Blok penyimpanan | seluruh byte untai, berjejalan |

Karena untai kini terpotong bersih, blok `api_paths` (C) juga menerima jalur
berdiri sendiri yang berbatas awal/akhir baris, bukan hanya literal berkutip
seperti pada JavaScript biasa.

Persoalan batas untai tidak hanya milik Hermes. Berkas `.dex` menyimpan *string
pool*-nya dengan cara serupa — untai berjejalan, dipisah satu byte NUL, dan tiap
untai didahului byte penanda panjang. Karena artefak `.dex` dipindai sebagai byte
mentah, pola URL bisa menyeberangi pemisah itu dan menyambung belasan alamat
menjadi satu untai panjang. Karena itu kelas karakter pada pola URL dan WebSocket
mengecualikan seluruh byte kendali (`\x00`–`\x20` dan `\x7f`): sebuah URL yang sah
memang tidak pernah boleh memuat karakter kendali (RFC 3986), sehingga byte NUL
pemisah antar-untai sekaligus berfungsi sebagai penanda batas.

### 5.6 Pemisahan Endpoint Aplikasi dari URL Pustaka

Sebuah aplikasi modern membawa puluhan pustaka pihak ketiga, dan pustaka
membawa serta tautan dokumentasinya sendiri. Akibatnya daftar URL mentah
bercampur: alamat peladen milik aplikasi berbaur dengan `momentjs.com`,
`reactnavigation.org`, atau `github.com` yang sekadar tertulis pada komentar
kode pustaka.

Karena itu disediakan kategori tersendiri, `app_endpoints`, yang diisi oleh
`classify_app_endpoint()`. Sebuah URL masuk ke kategori ini bila memenuhi dua
syarat sekaligus:

1. **Host-nya bukan host pustaka** — diperiksa terhadap daftar `LIBRARY_HOSTS`.
2. **Jalurnya memuat penanda API** — misalnya `/api`, `/v1`, `/auth`, atau
   segmen serupa yang menandakan antarmuka program, bukan halaman dokumentasi.
3. **Host-nya bukan templat** — alamat seperti `http://%s/status` milik
   dev-server Metro baru diisi saat aplikasi berjalan, sehingga bukan alamat
   peladen yang benar-benar terekspos di dalam berkas. `TEMPLATE_HOST_RE`
   menolak host yang memuat `%s`, `{`, atau `$`.

Daftar `LIBRARY_HOSTS` mencakup dua rumpun: host dokumentasi/spesifikasi
(`momentjs.com`, `w3.org`, `xmlpull.org`) dan host layanan pihak ketiga yang
dibawa SDK (`googleapis.com`, `gstatic.com`) — misalnya deretan URL cakupan
OAuth Google Play Services yang tertanam pada berkas dex. Keduanya bukan
permukaan antarmuka milik aplikasi.

Kategori ini bersifat inventarisasi, bukan tuduhan: ia tidak menaikkan skor
risiko, melainkan menjawab pertanyaan "permukaan antarmuka apa yang terbaca dari
berkas yang didistribusikan".

---

## 6. Tahap 4 — Skoring dan Klasifikasi Risiko

Temuan yang terkumpul perlu diringkas menjadi satu angka agar artefak dapat
diurutkan menurut tingkat kegentingannya. Dari 15 kategori hasil, **hanya tiga
yang memengaruhi skor**:

| Sumber | Bobot |
|---|---|
| Kredensial (blok E) | 50–100, sesuai bobot detektor |
| Connection string basis data (blok I) | 95 |
| Rahasia hasil dekode Base64 (blok L) | 70 |

Kategori sisanya — URL, endpoint aplikasi, jalur API, permission, kata kunci,
dan seterusnya — murni bersifat **inventarisasi**. Kategori tersebut memperkaya
laporan bagi analis, tetapi bukan tuduhan, sehingga tidak menaikkan skor.

### 6.1 Mengapa Bukan Model Akumulatif

Cara paling sederhana menyusun skor adalah menjumlahkan bobot setiap kecocokan.
Cara itu tidak dipakai, karena mengandung tiga cacat:

1. **Duplikat menggelembungkan skor.** Satu token yang berulang lima puluh kali
   di dalam berkas akan menaikkan skor lima puluh kali lipat, padahal secara
   substansi ia hanyalah satu kebocoran.
2. **Tidak ada batas atas.** Skor menumpuk tanpa plafon, sehingga artefak
   berukuran besar hampir selalu mencapai level tertinggi semata karena
   volumenya — bukan karena bahayanya.
3. **Volume mengalahkan tingkat bahaya.** Empat blok sertifikat (bobot 50)
   berjumlah 200, sedangkan satu kunci AWS (bobot 100) tetap 100. Padahal satu
   kunci AWS yang bocor jauh lebih berbahaya daripada empat blok sertifikat yang
   keberadaannya sering wajar.

### 6.2 Model Severity + Breadth

Skor karena itu disusun dari dua komponen, dihitung atas **temuan unik**:

| Komponen | Makna | Perhitungan |
|---|---|---|
| *severity* | seberapa berbahaya temuan terparah | bobot tertinggi di antara temuan unik (0–100) |
| *breadth* | seberapa beragam temuannya | `min(jumlah_temuan_unik − 1, 5) × 4`, maksimum +20 |

Skor akhir adalah `severity + breadth`, terikat pada rentang 0–120. Karena
dihitung dari temuan unik, duplikat tidak berpengaruh. Karena bonus keragaman
dibatasi, volume tidak dapat mendominasi. Karena dasarnya temuan terparah, satu
kunci berbahaya langsung mengangkat tingkat risiko tanpa perlu ditemani temuan
lain.

Perilaku model pada tiga skenario:

| Skenario | Skor | Level |
|---|---|---|
| 1 kunci AWS | 100 | `CRITICAL` |
| 4 blok sertifikat | 50 | `MEDIUM` |
| 50 token identik | 100 (dihitung sekali) | `CRITICAL` |

Klasifikasi akhir:

| Rentang skor | Level |
|---|---|
| ≥ 90 | `CRITICAL` |
| ≥ 70 | `HIGH` |
| ≥ 50 | `MEDIUM` |
| < 50 | `LOW` |

Perlu ditegaskan satu hal dalam membaca level ini: yang dinilai adalah
**kebocoran kredensial**. Artefak yang tidak memuat kredensial keras akan
berlevel `LOW` sekalipun seluruh permukaan antarmukanya terbaca. Eksposur
permukaan endpoint dilaporkan pada kategori `app_endpoints`, bukan pada skor.

---

## 7. Keluaran

Keluaran berupa satu berkas `reverse_results.json` di dalam direktori
`<nama_apk>_analysis_<timestamp>/`. Strukturnya:

```json
{
  "metadata": {
    "target_apk": "...",
    "analysis_timestamp": "...",
    "total_artifacts_found": 3
  },
  "artifacts": {
    "assets/index.android.bundle": {
      "file": "index.android.bundle",
      "size_kb": 2048.5,
      "risk_level": "LOW",
      "risk_score": 0,
      "summary": { "total_urls": 84, "total_app_endpoints": 18, "...": 0 },
      "urls": [ "..." ],
      "app_endpoints": [ "..." ],
      "api_keys_and_tokens": [],
      "...": []
    }
  }
}
```

Artefak diurutkan menurun berdasarkan `risk_score`, sehingga berkas paling
berisiko selalu tampil paling atas. Artefak yang dilewati karena melebihi batas
300 MB tetap muncul dengan bentuk hasil yang sama, ditandai `risk_level`
`SKIPPED` beserta keterangan pada kunci `error`.

Seluruh langkah di atas — ekstraksi, pemilihan artefak, pemindaian, pengurutan,
dan penulisan JSON — dikerjakan satu fungsi `analyze_apk()`. Mode baris perintah
maupun antarmuka bermenu sama-sama memanggil fungsi tersebut, sehingga alur
analisis hanya ditulis satu kali dan keduanya dijamin menghasilkan keluaran yang
identik.

Cara menjalankan:

```bash
python3 apk_analyzer.py /path/ke/target.apk
```

Tool hanya memakai pustaka standar Python, sehingga tidak memerlukan instalasi
dependensi apa pun.

---

## 8. Penerapan terhadap MyErpskrip

Perangkat yang telah dibangun diterapkan untuk menganalisis **MyErpskrip.apk**,
aplikasi Android milik PT Queen Network Nusantara. Bagian ini memuat jalannya
penerapan dan hasil yang diperoleh. Profil lengkap aplikasinya ada pada
`RINGKASAN_MYERPSKRIP.md`.

### 8.1 Karakteristik Artefak yang Dihadapi

Aplikasi ini dibangun dengan React Native/Expo, dan empat karakteristik
artefaknya menentukan bagaimana perangkat harus bekerja:

| Karakteristik artefak | Konsekuensi bila diabaikan | Ditangani oleh |
|---|---|---|
| Kode dikemas sebagai bundel Hermes; untai teks berjejalan tanpa pemisah | Alamat terekstrak bersambung dengan ekor untai tetangga | `extract_hermes_strings()` — bagian 5.5 |
| Kode JavaScript ter-*minify*; identifier acak menyerupai bentuk kunci API | Identifier biasa tertuduh sebagai kredensial | Deteksi berbasis konteks + pola ketat — bagian 5.3 |
| Aset gambar tertanam sebagai untai Base64 | Data gambar tertuduh sebagai rahasia terenkode | Penolakan `BINARY_MAGIC` — bagian 5.4 |
| Puluhan pustaka pihak ketiga membawa tautan dokumentasinya | Alamat milik aplikasi tenggelam di antara URL pustaka | `classify_app_endpoint()` — bagian 5.6 |

Keempatnya adalah ciri umum aplikasi React Native modern, sehingga penanganan
yang dirancang untuk MyErpskrip berlaku pula bagi aplikasi sejenis.

### 8.2 Jalannya Analisis

```bash
python3 apk_analyzer.py MyErpskrip.apk
```

Berkas APK berukuran 52,6 MB dibuka sebagai arsip ZIP dan diekstrak (± 60 MB).
Dari seluruh isinya, **enam artefak** diidentifikasi sebagai pemuat kode atau
konfigurasi, lalu dipindai satu per satu:

| Artefak | Ukuran | Keterangan |
|---|---|---|
| `assets/index.android.bundle` | 10,86 MB | Bundel Hermes bytecode versi 96 |
| `classes.dex` | 9,27 MB | Kode Java/Kotlin |
| `classes3.dex` | 8,35 MB | Kode Java/Kotlin |
| `classes4.dex` | 7,60 MB | Kode Java/Kotlin |
| `classes2.dex` | 32,8 KB | Kode Java/Kotlin |
| `AndroidManifest.xml` | 26,0 KB | Binary XML (AXML) |

Bundel Hermes dikenali dari *magic byte* pada headernya, sehingga pemindaian
atas artefak tersebut dijalankan terhadap untai teks yang telah dipotong pada
batas aslinya, bukan terhadap byte mentah.

### 8.3 Hasil Analisis

| Kategori | Jumlah |
|---|---|
| URL ter-inventaris | 84 |
| Endpoint aplikasi (`app_endpoints`) | 18 |
| Kanal WebSocket | 1 |
| Jalur API berdiri sendiri | 1 |
| Variabel lingkungan | 14 |
| Kata kunci sensitif | 24 pada bundel, 16–19 pada tiap berkas dex |
| **Kredensial keras (`api_keys_and_tokens`)** | **0** |
| **Connection string basis data** | **0** |
| **Rahasia hasil dekode Base64** | **0** |
| **Kunci penyimpanan lokal** | **0** |
| Tingkat risiko seluruh artefak | `LOW` |

Sebaran temuan antar-artefak menunjukkan bahwa hampir seluruh informasi berguna
berada pada satu berkas: bundel Hermes menyumbang 84 URL, 18 endpoint aplikasi,
dan 24 kata kunci sensitif, sedangkan keempat berkas dex hanya menyumbang
alamat pustaka dan sedikit kata kunci. Temuan ini sejalan dengan sifat aplikasi
React Native, yaitu seluruh logika aplikasi berada di sisi JavaScript.

### 8.4 Pembacaan Hasil

**Tidak ditemukan kredensial keras yang tertanam pada MyErpskrip.** Tidak ada
kunci API, token, connection string, maupun rahasia terenkode Base64 pada
keenam artefak. Karena skor risiko menilai kebocoran kredensial, seluruh artefak
berlevel `LOW`, dan level itu mencerminkan keadaan yang sebenarnya.

Meski demikian, level `LOW` tidak berarti aplikasi tanpa catatan. Hasil
pemindaian memperlihatkan bahwa **permukaan antarmuka peladen aplikasi terbaca
sepenuhnya dari berkas yang didistribusikan**, tanpa perlu mendekompilasi
maupun menjalankan aplikasi: 18 alamat endpoint terpisah dari URL pustaka,
mencakup alur autentikasi berbasis OTP, penagihan dan pembayaran, notifikasi,
data teknis pelanggan, serta tiket gangguan — ditambah satu kanal WebSocket.

Hal itu bukan cacat aplikasi, sebab alamat endpoint memang harus tertulis di
dalam aplikasi agar dapat dihubungi. Namun keterbacaannya menegaskan bahwa
pengamanan tidak dapat bertumpu pada anggapan "alamatnya tidak diketahui
orang": setiap endpoint yang terbaca wajib memiliki pengamanan sendiri di sisi
peladen, terutama pada jalur autentikasi dan pembayaran.

Keluaran pemindaian diperiksa kembali terhadap artefaknya untuk memastikan tiap
alamat terekstrak utuh dan tiap kategori terisi dengan nilai yang bermakna.

---

## 9. Keterbatasan yang Diketahui

Bagian ini mencatat batas kemampuan perangkat secara terbuka, sekaligus menjadi
dasar arah pengembangan selanjutnya.

**9.1 AndroidManifest.xml belum diurai secara utuh.**
Manifest pada APK yang telah dipaketkan disimpan dalam format binary XML (AXML),
bukan XML teks. Pola perangkat mensyaratkan literal berada di antara tanda
kutip, sehingga permission dan komponen hanya terbaca sebagian melalui
pemindaian untai teks. Diperlukan pengurai AXML untuk menutup celah ini.

**9.2 Skor belum menilai eksposur permukaan endpoint.**
Skor risiko hanya menilai kebocoran kredensial. Aplikasi yang seluruh permukaan
antarmukanya terbaca, namun tidak memuat kredensial keras, tetap berlevel `LOW`.
Eksposur semacam itu dilaporkan pada kategori `app_endpoints` dan perlu dibaca
tersendiri oleh analis. Menjadikannya bagian dari skor adalah pengembangan yang
paling layak didahulukan.

**9.3 Pemakaian memori.**
Artefak dimuat seluruhnya ke memori melalui `read_bytes()`, lalu sekitar 25 pola
disapukan berulang kali ke buffer yang sama. Untuk berkas berukuran ratusan
megabyte, pendekatan ini boros memori sekaligus lambat. Pembatas 300 MB per
artefak dipasang sebagai pengaman sementara.

**9.4 Kinerja blok Base64.**
Pencarian kandidat Base64 menyapu seluruh berkas dan merupakan blok paling
lambat. Pembatas 50 hanya menghitung hasil dekode yang berhasil, sehingga pada
kasus terburuk seluruh kandidat tetap diproses.

**9.5 Batas metode analisis statis.**
Alamat yang dirakit saat program berjalan — misalnya `base + "/" + versi +
"/user"` — tidak akan pernah terlihat, sebab bentuk utuhnya baru terbentuk
ketika aplikasi dijalankan. Keterbatasan ini melekat pada metode analisis statis
dan tidak dapat dihilangkan tanpa menambahkan analisis dinamis.

**9.6 Ketergantungan pada versi bytecode Hermes.**
Pengurai untai teks Hermes ditulis mengikuti tata letak header versi bytecode
96. Versi Hermes yang lebih baru dapat mengubah tata letak tersebut. Bila header
gagal diurai, perangkat tidak berhenti melainkan kembali memindai byte mentah,
sehingga hasilnya tetap keluar meski tidak sebersih semestinya.

---

## 10. Catatan Keamanan Perangkat

Perangkat ini membuka arsip yang tidak dipercaya, sehingga ekstraksinya sendiri
perlu diamankan. **Zip Slip** adalah kerentanan ketika entri arsip bernama
`../../berkas` diekstrak tanpa pemeriksaan sehingga berkas tertulis di luar
direktori tujuan.

`extract_apk()` karena itu memeriksa jalur setiap entri secara eksplisit dan
menolak arsip yang memuat entri di luar direktori tujuan, alih-alih bergantung
pada perilaku internal pustaka standar. Arsip semacam itu **ditolak tegas**,
bukan diam-diam disanitasi, sehingga jaminan keamanannya tersurat dan tidak
ikut hilang bila metode ekstraksi kelak diubah.

---

## 11. Glosarium

| Istilah | Penjelasan |
|---|---|
| **Analisis statis** | Pemeriksaan aplikasi tanpa menjalankannya |
| **Artefak** | Berkas di dalam APK yang memuat kode atau konfigurasi |
| **Entropi Shannon** | Ukuran keacakan data; makin acak, makin tinggi nilainya |
| **Hermes bytecode** | Format biner hasil kompilasi JavaScript pada React Native |
| **Minify** | Pemendekan nama identifier agar berkas kode lebih kecil |
| **Magic byte** | Byte penanda di awal berkas yang menyatakan jenis formatnya |
| **Zip Slip** | Kerentanan penulisan berkas di luar direktori tujuan saat ekstraksi arsip |
| **AXML** | Format binary XML milik Android untuk menyimpan manifest |

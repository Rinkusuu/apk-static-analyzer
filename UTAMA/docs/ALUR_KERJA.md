# Dokumentasi Alur Kerja: APK Static Analyzer

Dokumen ini menjelaskan cara kerja `apk_analyzer.py` secara menyeluruh, dari APK
masuk sampai laporan JSON keluar. Ditulis sebagai bahan Bab Analisis & Perancangan
laporan Kerja Praktik.

Seluruh rujukan fungsi dan blok merujuk pada berkas `apk_analyzer.py` di
direktori proyek.

---

## 1. Ringkasan dalam Satu Paragraf

Tool ini melakukan **analisis statis** terhadap berkas APK Android. Ia membuka APK
sebagai arsip ZIP, mencari berkas-berkas yang memuat kode aplikasi, lalu membaca
berkas tersebut sebagai **byte mentah** dan menyapunya dengan sekitar 25 pola
*regular expression* untuk menemukan URL, endpoint API, kredensial, dan indikator
sensitif lain. Setiap temuan berkategori kredensial menambah angka pada skor
risiko, yang di akhir diterjemahkan menjadi level `LOW` sampai `CRITICAL`.

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
| React Native | `*.bundle`, `*.jsbundle` | Seluruh kode JavaScript dibundel apa adanya, sering nyaris tanpa obfuskasi |
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

dengan `p(x)` adalah frekuensi kemunculan tiap byte. Pengujian membuktikan
mekanisme ini bekerja: umpan berentropi rendah berhasil ditolak, sementara nilai
acak sungguhan tetap terdeteksi.

### 5.4 Blok L — Lapisan Anti-Obfuskasi

Blok ini menangani kasus rahasia yang tidak disimpan sebagai teks biasa,
melainkan dienkode Base64 lebih dahulu. Alurnya bertingkat:

1. Cari untai yang berbentuk Base64 (minimal 32 karakter).
2. Coba dekode dengan `validate=True`; yang gagal diabaikan.
3. Hitung entropi hasil dekode; bila di bawah 3.5, abaikan — kemungkinan besar
   hasil dekode yang kebetulan valid namun tidak bermakna.
4. Periksa apakah hasil dekode memuat indikator sensitif (`http`, `token`,
   `secret`, `jdbc`, dan sebagainya).
5. Bila ya, simpan 200 karakter pertama dan tambahkan 70 ke skor risiko.

Terdapat pembatas 50 hasil dekode per artefak demi menjaga kinerja.

---

## 6. Tahap 4 — Skoring dan Klasifikasi Risiko

Skor risiko bersifat **akumulatif**: setiap temuan menambah bobotnya ke
`risk_score`. Yang penting dicatat, dari 14 kategori hasil, **hanya tiga yang
memengaruhi skor**:

| Sumber | Kontribusi |
|---|---|
| Kredensial (blok E) | 50–100 per temuan, sesuai bobot detektor |
| Connection string basis data (blok I) | 95 per temuan |
| Rahasia hasil dekode Base64 (blok L) | 70 per temuan |

Sebelas kategori sisanya — URL, path API, permission, kata kunci, dan seterusnya
— murni bersifat **inventarisasi**. Kategori tersebut memperkaya laporan bagi
analis, tetapi tidak dianggap sebagai tuduhan sehingga tidak menaikkan skor.
Pemisahan ini merupakan keputusan desain yang tepat dan patut dipertahankan.

Cara skor tersebut dijadikan angka telah diperbarui dari model akumulatif
menjadi model **severity + breadth** yang terikat; lihat bagian 8.5.

Klasifikasi akhir:

| Rentang skor | Level |
|---|---|
| ≥ 90 | `CRITICAL` |
| ≥ 70 | `HIGH` |
| ≥ 50 | `MEDIUM` |
| < 50 | `LOW` |

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
      "risk_level": "CRITICAL",
      "risk_score": 2930,
      "summary": { "total_urls": 42, "total_tokens_found": 13, "...": 0 },
      "urls": [ "..." ],
      "api_keys_and_tokens": [ "[AWS Access Key] AKIA..." ],
      "...": []
    }
  }
}
```

Artefak diurutkan menurun berdasarkan `risk_score` di `main()`, sehingga
berkas paling berisiko selalu tampil paling atas.

Cara menjalankan:

```bash
python3 apk_analyzer.py /path/ke/target.apk
```

Tool hanya memakai pustaka standar Python, sehingga tidak memerlukan instalasi
dependensi apa pun.

---

## 8. Metode Pengujian

Untuk mengukur ketepatan tool secara objektif, dibangun sebuah APK sintetis yang
isinya diketahui sepenuhnya. Berkas pengujian berada di direktori `tests/`.

### 8.1 Rancangan

`make_sample_apk.py` membangkitkan dua berkas sekaligus:

- `sample.apk` — arsip ZIP valid berisi `AndroidManifest.xml`, `classes.dex`, dan
  `assets/index.android.bundle`, meniru struktur APK sungguhan.
- `expected.json` — *ground truth*, yaitu daftar seluruh nilai yang ditanam.

Karena keduanya dibangkitkan dari struktur data yang sama, ground truth tidak
mungkin melenceng dari isi APK yang diuji.

Isi sampel dirancang mengandung dua jenis nilai:

| Jenis | Jumlah | Maksud |
|---|---|---|
| Rahasia tertanam (`must_detect: true`) | 19 | Menguji **recall** — apakah ada yang terlewat |
| Umpan (`must_detect: false`) | 41 | Menguji **precision** — apakah ada yang salah tuduh |

Umpan terdiri atas 40 UUID biasa — nilai yang di aplikasi nyata lazim muncul
sebagai *request-id* atau *trace-id* dan sama sekali bukan kredensial — ditambah
satu placeholder berentropi rendah.

Seluruh kredensial pada sampel adalah nilai palsu yang sengaja dibentuk agar
cocok dengan pola analyzer. Tidak ada kredensial sungguhan yang digunakan.

### 8.2 Metrik

`evaluate.py` menjalankan pipeline analyzer yang sesungguhnya terhadap
sampel, lalu membandingkan hasilnya dengan ground truth:

- **True Positive (TP)** — rahasia tertanam yang berhasil ditemukan.
- **False Negative (FN)** — rahasia tertanam yang terlewat.
- **False Positive (FP)** — nilai yang dilaporkan sebagai kredensial padahal bukan.
- **Precision** = TP / (TP + FP) — seberapa dapat dipercaya setiap temuan.
- **Recall** = TP / (TP + FN) — seberapa lengkap penemuannya.

Penghitungan FP hanya diterapkan pada kategori yang bersifat tuduhan
(`api_keys_and_tokens` dan `db_connections`), tidak pada kategori inventarisasi.

### 8.3 Hasil Pengukuran

| Metrik | Kondisi Awal | Sekarang | Perubahan |
|---|---|---|---|
| True Positive | 20 | 20 | tetap |
| False Negative | 0 | 0 | tetap |
| False Positive | 40 | **0** | −40 |
| **Precision** | **33.33%** | **100.00%** | +66.67 poin |
| **Recall** | **100.00%** | **100.00%** | tetap |

Skor risiko tidak dimasukkan ke tabel perbandingan karena skalanya berubah pada
langkah 8.5 (model lama tak terbatas; model baru terikat 0–120), sehingga
angkanya tidak sebanding langsung. Hanya precision dan recall yang definisinya
sama lintas versi dan layak dibandingkan.

Analisis atas kondisi awal:

1. **Recall sempurna sejak awal.** Seluruh 20 kredensial tertanam berhasil
   ditemukan, mencakup kunci AWS, Google, GitHub, GitLab, Stripe, Slack,
   Telegram, Alibaba, Twilio, SendGrid, Heroku, token JWT, blok kunci privat,
   serta dua connection string. Kemampuan deteksi dasarnya memang kuat.

2. **Precision rendah, dan penyebabnya tunggal.** Seluruh 40 false positive
   berasal dari satu detektor saja, yaitu `Heroku API Key`. Delapan belas
   detektor lainnya tidak menghasilkan satu pun kesalahan.

3. **Skor risiko terdistorsi.** Dari total skor 3885, sebanyak 2400 (62%)
   disumbang oleh false positive tersebut, sehingga level `CRITICAL` yang
   dilaporkan sebagian besar bukan berasal dari temuan yang sahih.

### 8.4 Perbaikan: Deteksi Berbasis Konteks

Kunci API Heroku berbentuk UUID biasa dan **tidak memiliki awalan khas** seperti
`AKIA` pada AWS, `AIza` pada Google, atau `ghp_` pada GitHub. Akibatnya, kunci
Heroku sungguhan dan sekadar *request-id* maupun *trace-id* memiliki bentuk yang
identik dan mustahil dibedakan berdasarkan pola semata.

Pendekatan deteksi karena itu diubah dari **berbasis bentuk** menjadi **berbasis
konteks**: sebuah UUID hanya dianggap kredensial apabila didahului label yang
menyebut "heroku".

| | Pendekatan lama | Pendekatan baru |
|---|---|---|
| Dasar deteksi | Bentuk (*pattern matching*) | Konteks (*contextual matching*) |
| Cakupan | Seluruh UUID | Hanya UUID berlabel heroku |

Detektor **tidak dihapus**, sebab menghapusnya berarti menghilangkan kemampuan
mendeteksi kunci Heroku sungguhan. Untuk membuktikannya, sampel uji diperluas
dengan satu kunci Heroku berlabel `HEROKU_API_KEY`. Hasil pengukuran menunjukkan
kunci tersebut tetap terdeteksi (True Positive tetap 20, False Negative tetap 0)
sementara seluruh 40 false positive hilang.

Perbaikan ini juga menjawab risiko *alert fatigue*: pada kondisi awal, dua dari
setiap tiga temuan kredensial adalah alarm palsu. Perangkat dengan rasio semacam
itu cenderung diabaikan analis, sehingga temuan sungguhan justru berisiko
terlewat meskipun recall-nya sempurna.

### 8.5 Perbaikan: Model Skoring Severity + Breadth

Model skoring awal bersifat akumulatif tanpa batas dan mengandung tiga cacat:

1. **Duplikat menggelembungkan skor.** Skor ditambah untuk setiap kecocokan,
   padahal daftar temuan menyimpan nilai unik. Satu token yang berulang 50 kali
   menaikkan skor 50 kali lipat, meski hanya tercatat sebagai satu temuan.
2. **Tidak ada batas atas.** Skor menumpuk tanpa plafon, sehingga APK berukuran
   besar hampir selalu mencapai `CRITICAL` semata karena volumenya.
3. **Volume mengalahkan tingkat bahaya.** Empat blok sertifikat (bobot 50) yang
   berjumlah 200 tergolong `CRITICAL`, sedangkan satu kunci AWS sungguhan (bobot
   100) hanya `HIGH` — terbalik dari risiko sebenarnya.

Model diganti menjadi dua komponen:

| Komponen | Makna | Perhitungan |
|---|---|---|
| *severity* | seberapa berbahaya temuan terparah | bobot tertinggi di antara temuan unik (0–100) |
| *breadth* | seberapa beragam temuannya | `min(jumlah_temuan_unik − 1, 5) × 4`, maksimum +20 |

Skor akhir adalah `severity + breadth`, terikat pada rentang 0–120. Karena skor
dihitung dari **temuan unik**, duplikat tidak lagi berpengaruh. Karena bonus
keragaman dibatasi, volume tidak dapat mendominasi. Karena dasarnya adalah
temuan terparah, satu kunci berbahaya langsung menaikkan tingkat risiko.

Perilaku ini diverifikasi oleh `tests/test_scoring.py`:

| Skenario | Model lama | Model baru |
|---|---|---|
| 1 kunci AWS | 100 → `HIGH` | 100 → `CRITICAL` |
| 4 blok sertifikat | 200 → `CRITICAL` | 50 → `MEDIUM` |
| 50 token identik | 4250 → `CRITICAL` | 100 → dihitung sekali |

Sebagai konsekuensi, skala skor berubah total. Angka skor sebelum dan sesudah
perbaikan ini **tidak dapat dibandingkan langsung**; hanya precision dan recall
yang tetap sebanding lintas versi.

---

## 9. Keterbatasan yang Diketahui

Bagian ini didasarkan pada pembacaan kode dan hasil pengujian, dan menjadi dasar
perbaikan pada tahap selanjutnya.

**9.1 ~~Pola `Heroku API Key` terlalu longgar.~~ — SUDAH DIPERBAIKI.**
Pola lama, `[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-...`, sesungguhnya hanyalah pola UUID
generik, sehingga setiap UUID di dalam APK dianggap kredensial. Ini merupakan
penyebab tunggal seluruh false positive pada pengukuran awal. Telah diperbaiki
melalui deteksi berbasis konteks; lihat bagian 8.4.

**9.2 ~~Skor risiko tidak dinormalisasi.~~ — SUDAH DIPERBAIKI.**
Model skoring lama bertambah per kemunculan tanpa batas atas, sehingga duplikat
menggelembungkan skor dan APK besar hampir selalu `CRITICAL` karena volumenya.
Telah diganti dengan model *severity + breadth* yang terikat 0–120 dan berbasis
temuan unik; lihat bagian 8.5.

**9.3 Ketahanan terhadap Zip Slip — hipotesis yang diuji dan terbantah.**
Zip Slip adalah kerentanan ketika entri arsip bernama `../../berkas` diekstrak
tanpa pemeriksaan sehingga berkas tertulis di luar direktori tujuan. Karena
`extract_apk()` memakai `zipfile.extractall()`, sempat diduga perangkat ini
rentan. Dugaan tersebut diuji dengan APK jahat buatan sendiri
(`tests/test_zip_slip.py`), dan hasilnya **membantah dugaan**: pustaka standar
Python 3 sudah menetralkan Zip Slip pada dua vektor sekaligus —

- entri `../../berkas` disanitasi menjadi `dest/berkas` (komponen `..` dibuang);
- entri symlink yang menunjuk keluar ditulis sebagai berkas teks biasa, bukan
  sebagai tautan, sehingga tidak dapat ditembus.

Meski demikian, keamanan itu bergantung pada perilaku internal `extractall()`.
Bila kelak metode ekstraksi diubah menjadi perulangan manual (misalnya untuk
melewati berkas berukuran sangat besar satu per satu), perlindungan implisit itu
dapat hilang tanpa disadari. Karena itu `extract_apk()` dilengkapi pemeriksaan
jalur eksplisit sebagai *defense-in-depth* — bukan menambal kerentanan yang ada,
melainkan menjadikan jaminan keamanan tersurat dan tahan terhadap perubahan kode.
Uji `test_zip_slip.py` dipertahankan sebagai *regression test* yang menjaga agar
jaminan itu tidak diam-diam hilang di kemudian hari.

**9.4 AndroidManifest.xml tidak diurai secara benar.**
Pada APK sungguhan, manifest disimpan dalam format binary XML (AXML) tanpa tanda
kutip. Pola analyzer mensyaratkan literal berada di antara tanda kutip, sehingga
permission dan komponen pada APK nyata banyak yang tidak terbaca. Diperlukan
pengurai AXML untuk menutup celah ini.

**9.5 Pemakaian memori.**
Artefak dimuat seluruhnya ke memori melalui `read_bytes()`, lalu sekitar 25 pola
disapukan berulang kali ke buffer yang sama. Untuk berkas berukuran ratusan
megabyte, pendekatan ini boros memori sekaligus lambat.

**9.6 Kinerja blok Base64.**
Pencarian kandidat Base64 menyapu seluruh berkas dan merupakan blok paling
lambat. Pembatas 50 hanya menghitung hasil dekode yang berhasil, sehingga pada
kasus terburuk seluruh kandidat tetap diproses.

**9.7 Batas metode analisis statis.**
Endpoint yang dirakit saat program berjalan — misalnya `base + "/" + versi +
"/user"` — tidak akan pernah terlihat, sebab bentuk utuhnya baru terbentuk ketika
aplikasi dijalankan. Keterbatasan ini melekat pada metode analisis statis dan
tidak dapat dihilangkan tanpa menambahkan analisis dinamis.

---

## 10. Glosarium

| Istilah | Penjelasan |
|---|---|
| **Analisis statis** | Pemeriksaan aplikasi tanpa menjalankannya |
| **Artefak** | Berkas di dalam APK yang memuat kode atau konfigurasi |
| **Entropi Shannon** | Ukuran keacakan data; makin acak, makin tinggi nilainya |
| **False positive** | Temuan yang dilaporkan padahal sebenarnya bukan ancaman |
| **False negative** | Ancaman nyata yang justru terlewat |
| **Precision** | Proporsi temuan yang benar-benar sahih |
| **Recall** | Proporsi ancaman nyata yang berhasil ditemukan |
| **Ground truth** | Kondisi sebenarnya yang telah diketahui, dipakai sebagai acuan uji |
| **Zip Slip** | Kerentanan penulisan berkas di luar direktori tujuan saat ekstraksi arsip |
| **AXML** | Format binary XML milik Android untuk menyimpan manifest |

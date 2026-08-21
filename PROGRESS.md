# Catatan Pengembangan — APK Static Analyzer

Berkas ini adalah memori proyek. Sesi Claude yang baru cukup membaca berkas ini
untuk melanjutkan pekerjaan tanpa menelusuri ulang seluruh direktori.

**Terakhir diperbarui:** 2026-08-21

---

## Tentang Proyek

Pengembangan perangkat analisis statis APK Android untuk mendeteksi endpoint dan
kredensial yang terekspos di dalam berkas aplikasi. Dibangun dari nol selama
Kerja Praktik di PT Queen Network Nusantara.

**Objek uji tunggal: aplikasi MyErpskrip** (`com.qnn.myerpskrip`) — aplikasi
Android produksi milik perusahaan, berbasis React Native/Expo dengan bundel
Hermes. Seluruh angka evaluasi berasal dari pemindaian APK tersebut, bukan dari
aplikasi buatan sendiri. Profil objek uji ada di
`UTAMA/docs/RINGKASAN_MYERPSKRIP.md`.

Arah pengembangan yang dipilih: **jangan menambah fitur sebelum yang ada bisa
diukur.** Karena itu urutan kerjanya adalah membangun alat ukur lebih dulu,
menetapkan angka kondisi awal, baru memperbaiki — sehingga setiap perbaikan
dapat dibuktikan dengan selisih angka, bukan sekadar diklaim.

## Cara Kerja Perangkat (ringkas)

Analisis statis, tanpa dekompilasi dan tanpa menjalankan aplikasi. Pada dasarnya
`grep` terstruktur terhadap isi APK. Empat tahap: ekstrak ZIP → pilih artefak
(`.bundle`/`.dex`/`.so`/manifest) → baca sebagai byte lalu sapu ±25 regex →
akumulasi skor risiko. Penjelasan lengkap di `UTAMA/docs/ALUR_KERJA.md`.

## Struktur Direktori

| Path | Status |
|---|---|
| `UTAMA/` | **Dikumpulkan.** Aman, tidak ada data pihak lain |
| `PENDUKUNG/` | **Jangan dikumpulkan.** Hasil analisis APK produksi pihak ketiga |

Aturan lengkap ada di `README.md`.

---

## Fase 0 — Prototipe Pertama

Prototipe pertama dibangun untuk membuktikan bahwa pendekatannya masuk akal:
membuka APK sebagai ZIP, memilih artefak kode, lalu menyapunya dengan pola
regex. Prototipe ini sudah mampu menemukan banyak hal saat dijalankan terhadap
MyErpskrip, namun statusnya masih mentah:

- belum ada dokumentasi mengenai cara kerjanya;
- ketepatannya belum pernah diukur, sehingga temuannya belum dapat dipercaya;
- belum masuk version control;
- keluarannya belum dipisahkan dari data internal yang tidak boleh disebar.

## Fase 1 — Membangun Fondasi *(selesai)*

- [x] Kode ditata ke struktur proyek tersendiri di `KP/FINAL/`
- [x] Berkas utama dinamai `apk_analyzer.py`
- [x] Alur kerja dibedah dan didokumentasikan (`UTAMA/docs/ALUR_KERJA.md`, 10 bagian)
- [x] Direktori dipisah `UTAMA/` vs `PENDUKUNG/` agar data pihak ketiga tidak
      ikut terkumpul
- [x] Repositori git diinisialisasi, di-push ke GitHub privat

## Fase 2 — Membangun Alat Ukur *(selesai)*

Ketepatan diukur langsung terhadap MyErpskrip dengan metode *differential
analysis*: hasil pemindaian otomatis dibandingkan terhadap hasil pembacaan
manual atas artefak aplikasi yang sama.

- [x] Ground truth manual disusun dari pembacaan bundel Hermes MyErpskrip —
      permukaan API yang benar-benar ada, dan ada-tidaknya kredensial keras
      (`PENDUKUNG/temuan_differential.md`, tidak di-push)
- [x] Kondisi awal dibekukan sebagai hasil pemindaian 31 Juli 2026
      (`PENDUKUNG/hasil_apk_nyata/`), menjadi titik banding seluruh perbaikan
- [x] Setiap hasil pemindaian berikutnya disimpan bertanggal agar selisihnya
      dapat ditelusuri
- [x] Uji regresi internal di `UTAMA/tests/` — alat bantu pengembangan agar
      perbaikan yang sudah jadi tidak rusak kembali, **bukan** sumber angka
      evaluasi. Tidak dibahas di laporan maupun dokumen bahan laporan.

## Fase 3 — Perbaikan Ketepatan *(berjalan)*

- [x] **Detektor Heroku API Key diubah ke deteksi berbasis konteks.**
      Pola lama hanyalah pola UUID generik, sehingga setiap request-id maupun
      trace-id di dalam APK dianggap kredensial. Pola baru hanya menerima UUID
      yang didahului label bermakna "heroku". Detektor tidak dihapus, hanya
      syarat penerimaannya diperketat. Pada MyErpskrip: 6 FP Heroku -> 0.
- [x] **Zip Slip: hipotesis diuji, terbantah, lalu diperkuat.** Diduga
      `extract_apk()` rentan Zip Slip. Diuji dengan APK jahat buatan sendiri
      (`tests/test_zip_slip.py`) dan **terbantah** — `zipfile.extractall()` Python
      sudah menetralkan `../` maupun symlink. Meski begitu, ditambahkan
      pemeriksaan jalur eksplisit sebagai *defense-in-depth* agar APK jahat
      **ditolak tegas**, bukan diam-diam disanitasi, dan agar keamanan tidak
      bergantung pada detail internal `extractall()`. Uji dipertahankan sebagai
      *regression test*.
- [x] **Model skoring diganti menjadi severity + breadth (terikat 0–120).**
      Model lama akumulatif tanpa batas punya tiga cacat: duplikat
      menggelembungkan skor, tidak ada plafon sehingga APK besar otomatis
      CRITICAL, dan banyak temuan lemah mengalahkan satu temuan berat. Model
      baru: skor = bobot temuan terparah + bonus keragaman terbatas, dihitung
      dari temuan unik. Diverifikasi `tests/test_scoring.py`. Akibatnya skala
      skor berubah total — angka skor lama dan baru TIDAK sebanding langsung,
      hanya precision/recall yang tetap sebanding.

## Fase 4 — Analisis Pembanding terhadap MyErpskrip *(berjalan)*

Metode *differential analysis*: jalankan perangkat terhadap MyErpskrip, lalu
bandingkan dengan analisis manual atas artefak yang sama untuk menemukan
kesenjangan yang tidak akan pernah terlihat dari aplikasi uji buatan sendiri.
(Bukti konkret berisi host dan endpoint internal disimpan di
`PENDUKUNG/temuan_differential.md`, tidak di-push.)

Kesenjangan yang ditemukan pada bundel Hermes MyErpskrip:

- [x] **False positive Mailgun.** Pola `key-[0-9a-zA-Z]{32}` menangkap identifier
      JS ter-minify. Diperketat ke `key-[0-9a-f]{32}\b` (format hex asli Mailgun).
- [x] **False positive Base64 pada aset biner.** Gambar tertanam (PNG/WEBP) lolos
      sebagai "decoded secret". Ditambahkan penolakan berbasis magic byte
      (`BINARY_MAGIC`). `decoded_secrets` kini dihitung sebagai kategori tuduhan
      di harness.
- [x] **Kesadaran Hermes bytecode.** Bundle RN modern adalah Hermes bytecode;
      string disimpan berjejalan tanpa pemisah, sehingga regex byte mentah
      menangkap endpoint + ekor string tetangga. Ditulis `extract_hermes_strings()`
      yang membaca tabel string Hermes (offset+panjang) dan memotong tiap string
      pada batas aslinya. Dikunci uji regresi `tests/test_hermes.py`; pada
      MyErpskrip: 17 endpoint backend kini terekstrak utuh (auth OTP, penagihan,
      notifikasi, dll.), URL bersih 60→84. Blok `api_paths` juga
      diperluas untuk path standalone.
- [x] **Pisahkan API aplikasi vs URL dokumentasi library.** Kategori baru
      `app_endpoints`: URL pada host non-library dengan jalur ber-penanda API
      (`classify_app_endpoint` + `LIBRARY_HOSTS`). Pada MyErpskrip: dari 84 URL,
      21 diisolasi sebagai endpoint aplikasi (18 benar, 3 salah tuduh). Diuji di `test_hermes.py`.
- [x] **Filter nama paket npm dari storage_keys.** Pola `@...` sempat menangkap
      nama paket npm (`@react-navigation`, `@scope/pkg`) sebagai kunci
      penyimpanan. Ditambah aturan buang bila mengandung `/` atau berbentuk
      scope huruf-kecil (`NPM_SCOPE_RE`). Diuji di `test_scoring.py`; pada
      MyErpskrip storage_keys 6 (semua npm) -> 0.
- [x] **Batas string pada artefak biner (.dex).** Perbaikan Hermes hanya
      berlaku untuk `.bundle`; string di `.dex` masih dibaca sebagai byte mentah
      sehingga regex URL menembus byte NUL pemisah antar-string dan menyambung
      belasan URL tetangga menjadi satu blob tak terbaca. Kelas karakter regex
      URL/WebSocket kini mengecualikan `\x00-\x20` dan `\x7f` — URL sah memang
      tidak boleh memuat karakter kontrol (RFC 3986), dan bundel Hermes tidak
      terpengaruh karena string di sana sudah dipisah lebih dulu. Pada
      MyErpskrip: `classes.dex` 6 -> 19 URL utuh, `classes3.dex` 16 -> 28.
- [x] **Tiga false positive `app_endpoints` terakhir ditutup.** Setelah string
      terpotong benar, sisanya tinggal dua jenis: URL layanan/dokumentasi pihak
      ketiga (`googleapis.com`, `xmlpull.org`) dan URL ber-templat host
      (`http://%s/status` milik dev-server Metro). `LIBRARY_HOSTS` diperluas ke
      host layanan Google dan host spesifikasi/dokumentasi, ditambah
      `TEMPLATE_HOST_RE` yang menolak host berisi `%s`/`{`/`$` karena baru diisi
      saat aplikasi berjalan. Pada MyErpskrip: app_endpoints 21 -> 18, seluruhnya
      endpoint backend asli — precision 85,71% -> 100%, recall tetap 16/16.
      Dikunci di `tests/test_hermes.py` bagian 5 (blob mirip tabel string .dex).
- [ ] **Belum menilai eksposur permukaan endpoint** (skor masih fokus kredensial).

## Pembenahan Kode *(19 Agustus 2026)*

- **Artefak >300 MB tidak lagi menggagalkan analisis.** `analyze_artifact()`
  dahulu mengembalikan dict tanpa `risk_level`/`summary`, sehingga `main()`
  melempar `KeyError` dan tidak ada JSON yang tertulis sama sekali. Kini bentuk
  hasilnya lengkap dengan `risk_level: "SKIPPED"`, `risk_score: 0`, dan ringkasan
  bernilai nol (`SUMMARY_FIELDS`).
- **CLI menampilkan endpoint dari artefak yang memuatnya terbanyak.** Dahulu
  diambil artefak pertama; karena seluruh artefak MyErpskrip berskor 0, yang
  terpilih adalah `AndroidManifest.xml` yang endpointnya nol, sehingga daftar 21
  endpoint tidak pernah tampil di layar.
- **Folder `tests/` tidak lagi dipindai** saat mencari kandidat APK, agar berkas
  uji tidak muncul di menu maupun tangkapan layar.
- **Pipeline analisis disatukan** ke `apk_analyzer.analyze_apk()` — dipakai
  bersama oleh `main()` dan `apk_cli.action_analyze()`, dengan callback opsional
  `on_start`/`on_result` untuk tampilan kemajuan. Duplikasi penyusunan metadata,
  pengurutan, dan penulisan JSON hilang.
- **Sisa dead code dibersihkan**: cek `isinstance(match, tuple)` yang tak pernah
  aktif, f-string tanpa placeholder, serta lambda `u32`/`align4` diubah menjadi
  `def`.
- Salinan beranotasi diperbarui dan diverifikasi identik secara struktur
  (perbandingan AST setelah docstring dilepas). Tiga uji regresi hijau.

## Pembenahan Kode *(21 Agustus 2026)*

- **Kegagalan analisis tidak lagi menumpahkan traceback.** `main()` dahulu
  mencetak pesan ramah lalu `traceback.print_exc()`, dan urutannya kacau karena
  stderr/stdout. Kini hanya galat yang memang mungkin datang dari masukan
  pengguna yang ditangkap (`BadZipFile`, `ValueError` Zip Slip, `OSError`);
  galat lain sengaja dibiarkan naik karena itu bug yang perlu terlihat.
- **Kode keluar bermakna.** Berkas tidak ditemukan, bukan ZIP, atau tanpa
  artefak kini `exit 1` — sebelumnya semuanya `exit 0` sehingga kegagalan tak
  terbaca oleh skrip pemanggil.
- **Berkas rusak tidak lagi meninggalkan direktori hasil kosong.** Direktori
  keluaran baru dibuat setelah arsip terbukti valid dan seluruh entrinya lolos
  pemeriksaan Zip Slip.

## Antarmuka

Dua mode pemakaian:
- **Langsung**: `python3 apk_analyzer.py <target.apk>` — sekali jalan, tulis JSON.
- **Bermenu**: `python3 apk_cli.py` — CLI interaktif berheader hias + warna
  (analisis, riwayat hasil, jalankan uji regresi). Menu Pengujian menjalankan
  tiga uji regresi — `test_zip_slip`, `test_scoring`, `test_hermes`; pemanggilan
  `evaluate` dilepas agar antarmuka sejalan dengan metode pengujian berbasis
  MyErpskrip. Menu analisis otomatis mencari APK di folder relevan termasuk
  `PENDUKUNG/apk_input`, jadi cukup pilih nomor.
  Hanya lapisan tampilan; analisis tetap memakai fungsi publik `apk_analyzer`.

## Konvensi Kode

Kode produksi (`UTAMA/apk_analyzer.py`, `UTAMA/apk_cli.py`) **bersih total tanpa
komentar/docstring**. Penjelasan lengkap + istilah ada di salinan beranotasi
`UTAMA/docs/apk_analyzer_beranotasi.py` dan `UTAMA/docs/apk_cli_beranotasi.py`
(perilaku analyzer diverifikasi identik dengan produksi). Setiap perubahan kode:
jaga produksi tetap bersih, lalu perbarui salinan beranotasi.

Ringkasan bukti perbaikan pada MyErpskrip ada di bagian **Angka Pengukuran**
di bawah. Catatan: `risk_level` LOW kini akurat untuk kebocoran *kredensial*,
sekaligus menandai bahwa perangkat belum menilai eksposur permukaan endpoint.

Uji regresi hijau seluruhnya: evaluate, test_zip_slip, test_scoring, test_hermes
— termasuk pemicu FP Mailgun dan Base64 yang di-*port* balik dari temuan pada
MyErpskrip agar tidak dapat kambuh.

## Framing Dokumen Keluaran *(keputusan 19 Agustus 2026)*

Berkas ini adalah memori pengembangan internal dan boleh memuat riwayat apa
adanya. **Dokumen keluaran** — `README.md`, seluruh isi `UTAMA/docs/`, dan
laporan KP — memakai framing berbeda yang wajib dipatuhi:

- Perangkat disajikan sebagai **pembuatan perangkat baru**, dirancang dan
  dibangun selama KP, lalu **diterapkan** untuk menganalisis `MyErpskrip.apk`.
- **Tidak ada** narasi kondisi awal → kondisi akhir, tidak ada kata perbaikan,
  penyempurnaan, atau versi sebelumnya.
- **Tidak ada** pembandingan sebagai metode (differential analysis, pembacaan
  manual sebagai acuan) dan **tidak ada** metrik precision/recall/false
  positive — semuanya menuntut acuan benar-salah yang tidak lagi disajikan.
- Alasan keberadaan tiap fitur adalah **karakteristik artefak yang dihadapi**
  (bundel Hermes, kode ter-minify, aset gambar Base64, URL pustaka), bukan
  riwayat kekeliruan yang diperbaiki.
- Angka yang dilaporkan hanya hasil pemindaian MyErpskrip: 84 URL, 18 endpoint
  aplikasi, 1 WebSocket, 0 kredensial keras, risiko LOW.

## Laporan

Bahan laporan yang tersedia:
- `UTAMA/docs/RINGKASAN_MYERPSKRIP.md` — profil objek uji (identitas aplikasi,
  teknologi, izin & komponen, artefak, ringkasan hasil), tanpa host/endpoint.
  Dipakai sebagai Project Knowledge pada Project penulisan laporan.
- `INSTRUKSI_PROJECT_LAPORAN.md` (akar direktori, tidak dikumpulkan) — naskah
  custom instructions Project laporan: framing "dibangun dari nol selama KP",
  MyErpskrip sebagai satu-satunya objek uji, tabel angka resmi yang boleh
  dikutip, dan larangan menyebut aplikasi uji sintetis.

Berkas knowledge Project di `~/Downloads/files/` (`ALUR_KERJA.txt`,
`RINGKASAN_MYERPSKRIP.txt`, `apk_analyzer.txt`, `apk_cli.txt`) adalah salinan
mentah dari berkas di repositori — perbarui salinannya setiap kali sumbernya
berubah, jika tidak Project laporan akan memakai versi lama.

Laporan KP dikompilasi sebagai halaman web (Artifact privat), terstruktur bab
I–VI dengan kedalaman naratif+teknis, nol data endpoint nyata:
https://claude.ai/code/artifact/d9e8f932-3b73-4152-ad30-f80def3145ef
Sumber materi: `UTAMA/docs/ALUR_KERJA.md` + berkas ini. Untuk memperbarui,
republish path yang sama atau berikan URL di atas sebagai `url`.

**Pelajaran metodologis:** menguji langsung pada aplikasi produksi mengungkap
persoalan yang tidak akan pernah terpikirkan oleh pembuat polanya sendiri —
kemasan Hermes, identifier ter-minify, aset biner, dan URL dokumentasi pustaka.
Tiap temuan itu kemudian dikunci sebagai uji regresi agar tidak dapat kambuh.

---

## Angka Pengukuran (MyErpskrip)

Kondisi awal: pemindaian 31 Juli 2026. Kondisi akhir: pemindaian 13 Agustus 2026.
Objek dan berkas APK sama persis; pembanding adalah hasil analisis manual.

**Kategori tuduhan (false positive)**

| Kategori | Kondisi Awal | Sekarang | Penilaian manual |
|---|---|---|---|
| `api_keys_and_tokens` | 7 | **0** | seluruh temuan awal FP (6 Heroku, 1 Mailgun) |
| `decoded_secrets` | 9 | **0** | seluruh temuan awal FP (aset gambar PNG/WEBP) |
| `storage_keys` | 6 | **0** | seluruh temuan awal FP (nama paket npm) |
| **Total FP** | **22** | **0** | — |

Tidak ada kredensial keras yang benar-benar tertanam pada MyErpskrip, sehingga
kategori ini juga tidak memiliki false negative.

**Permukaan API aplikasi**

| Metrik | Kondisi Awal | Sekarang |
|---|---|---|
| URL bersih ter-inventaris | 60 (banyak ternoda) | **84** |
| Endpoint aplikasi terisolasi | 0 (kategori belum ada) | **18** |
| Endpoint benar (TP) | 0 | **18** |
| Salah tuduh (FP) | — | 0 |
| Endpoint manual tertangkap | 0 dari 16 | **16 dari 16** |
| Precision | — | **100,00%** |
| Recall | 0% | **100,00%** |

**Tingkat risiko**

| | Kondisi Awal | Sekarang |
|---|---|---|
| `risk_level` | CRITICAL (palsu) | LOW (akurat) |

**Catatan:** hasil pemindaian tidak pernah ditimpa — tiap kali dijalankan
ditulis ke direktori bertanggal sendiri (`MyErpskrip_analysis_<timestamp>/`),
sehingga selisih antar-versi selalu dapat ditelusuri ulang.

---

## Rencana Berikutnya (urut prioritas)

1. **Penilaian eksposur permukaan endpoint** — skor risiko masih hanya menilai
   kebocoran kredensial, sehingga MyErpskrip berstatus LOW meski seluruh
   permukaan API-nya terbaca tanpa dekompilasi. Ini temuan yang belum tercermin
   pada skor.
2. **Pengurai AXML** untuk AndroidManifest.xml — manifest MyErpskrip berformat
   binary XML sehingga permission dan komponennya praktis tidak terbaca.
3. **Membersihkan `extracted_files`** — tiap pemindaian meninggalkan ekstraksi
   penuh APK (±60 MB) di dalam direktori hasil dan tidak pernah dihapus, dan
   berisiko menyalin isi APK pihak ketiga ke dalam `UTAMA/` bila dijalankan
   dari sana.
4. Efisiensi memori dan kinerja blok Base64.
5. Pemisahan modul dan laporan berformat Markdown/HTML — **paling akhir**.

Daftar keterbatasan lengkap ada di `UTAMA/docs/ALUR_KERJA.md` bagian 9.

---

## Cara Kerja yang Disepakati

- Ukur dulu, baru perbaiki. Setiap perbaikan disertai angka sebelum dan sesudah
  dari harness, serta dibuat sebagai satu commit tersendiri agar diff-nya dapat
  dijadikan bukti pada laporan.
- Jelaskan mekanismenya sebelum mengubah kode, bukan sesudah.
- Jangan refactor besar sebelum alur kodenya dipahami pemilik proyek.
- Jangan pernah menyalin isi `PENDUKUNG/` ke dalam `UTAMA/`.

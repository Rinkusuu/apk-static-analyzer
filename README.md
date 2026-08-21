# APK Static Analyzer

Perangkat analisis statis untuk berkas APK Android. Membuka APK, menelusuri
artefak kode di dalamnya, lalu mendeteksi endpoint dan kredensial yang terekspos
— tanpa dekompilasi dan tanpa menjalankan aplikasinya.

Dikembangkan sebagai proyek akhir Kerja Praktik. Riwayat pengembangan dan angka
pengukuran tercatat di `PROGRESS.md`.

**Penerapan:** perangkat ini diterapkan untuk menganalisis aplikasi
**MyErpskrip** (`com.qnn.myerpskrip`) — aplikasi Android berbasis React
Native/Hermes berukuran 52,6 MB dengan enam artefak kode.

**Hasil pemindaian:** 84 URL ter-inventaris, 18 endpoint aplikasi terpisah dari
URL pustaka, 1 kanal WebSocket, tidak ada kredensial keras yang tertanam,
tingkat risiko `LOW` pada seluruh artefak.

---

Direktori ini dibagi menjadi dua bagian dengan aturan yang tegas:

```
FINAL/
├── UTAMA/          ← KUMPULKAN. Seluruh isinya, apa adanya.
├── PENDUKUNG/      ← JANGAN DIKUMPULKAN. Bahan kerja internal.
└── README.md       ← berkas ini (tidak perlu dikumpulkan)
```

Aturan singkatnya: **kumpulkan folder `UTAMA/` saja.** Bila ragu, jangan
tambahkan apa pun dari luar folder tersebut.

---

## UTAMA/ — yang dikumpulkan

```
UTAMA/
├── apk_analyzer.py                 mesin analisis (mode langsung)
├── apk_cli.py                      antarmuka bermenu (mode interaktif)
├── docs/
│   ├── ALUR_KERJA.md               dokumentasi alur kerja, bahan laporan
│   ├── RINGKASAN_MYERPSKRIP.md     profil objek uji (tanpa host/endpoint)
│   ├── apk_analyzer_beranotasi.py  salinan beranotasi mesin analisis
│   └── apk_cli_beranotasi.py       salinan beranotasi antarmuka
└── tests/                          uji regresi internal (alat bantu pengembangan)
    ├── test_zip_slip.py            uji penolakan arsip jahat
    ├── test_scoring.py             uji model skoring
    ├── test_hermes.py              uji ekstraksi string Hermes
    └── (berkas kerja pengujian, dibangkitkan otomatis)
```

Seluruh isinya aman dikumpulkan. Tidak ada data milik pihak lain, dan seluruh
nilai kredensial yang muncul di berkas uji adalah nilai palsu yang sengaja
dibuat agar cocok dengan pola analyzer.

Direktori `tests/` adalah **uji regresi internal**: alat bantu pengembangan yang
menjaga agar perilaku fungsi-fungsi kunci tetap sesuai rancangan. Angka pada
laporan seluruhnya berasal dari pemindaian MyErpskrip.

### Cara menjalankan

Hanya memakai pustaka standar Python. Tidak ada dependensi yang perlu dipasang.

```bash
cd UTAMA

# 1a. Analisis sebuah APK (mode langsung)
python3 apk_analyzer.py /path/ke/target.apk

# 1b. Antarmuka bermenu (mode interaktif)
python3 apk_cli.py

# 2. Menjalankan uji regresi internal (opsional)
python3 tests/test_hermes.py
python3 tests/test_scoring.py
python3 tests/test_zip_slip.py
```

Angka pada laporan dihasilkan oleh perintah nomor 1a terhadap `MyErpskrip.apk`;
perintah nomor 2 hanya menjaga perilaku fungsi kunci tetap sesuai rancangan.

### Catatan struktur

Berkas di dalam `tests/` mengimpor `apk_analyzer.py` dari direktori induknya.
Keduanya harus tetap bersebelahan di dalam `UTAMA/`; bila salah satu dipindah,
pengujian tidak akan berjalan.

---

## PENDUKUNG/ — JANGAN dikumpulkan

```
PENDUKUNG/
└── hasil_apk_nyata/
    └── MyErpskrip_analysis_20260731_141948/
        └── reverse_results.json
```

Berkas ini adalah hasil analisis terhadap **APK produksi milik pihak ketiga**.
Isinya mencakup 60 URL, di antaranya host backend internal
(`apibackend.erpskrip.id`), beserta daftar endpoint aplikasi tersebut.

**Alasan tidak dikumpulkan:** memuat host backend dan daftar endpoint internal
secara konkret. Laporan tidak memerlukannya, sebab yang dikutip hanyalah angka
agregat hasil pemindaian MyErpskrip — bukan isi endpointnya.

Hasil pemindaian MyErpskrip tetap dibahas di laporan, namun cukup dengan angka
agregatnya saja — jumlah artefak, level risiko, jumlah temuan — tanpa
melampirkan URL, host, maupun berkas JSON-nya.

Berkas ini adalah bahan kerja internal. Untuk laporan, yang dikutip cukup angka
agregat hasil pemindaian — jumlah artefak, jumlah temuan per kategori, dan
tingkat risiko.

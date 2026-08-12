# APK Static Analyzer

Perangkat analisis statis untuk berkas APK Android. Membuka APK, menelusuri
artefak kode di dalamnya, lalu mendeteksi endpoint dan kredensial yang terekspos
— tanpa dekompilasi dan tanpa menjalankan aplikasinya.

Dikembangkan sebagai proyek akhir Kerja Praktik, bertolak dari prototipe yang
ditinggalkan pengembang sebelumnya. Riwayat pengembangan dan angka pengukuran
tercatat di `PROGRESS.md`.

**Ketepatan saat ini:** precision 100%, recall 100% terhadap sampel
ber-ground-truth berisi 20 kredensial dan 41 umpan.

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
├── apk_analyzer.py                 program utama
├── docs/
│   └── ALUR_KERJA.md               dokumentasi alur kerja, bahan laporan
└── tests/
    ├── make_sample_apk.py          generator APK sampel + ground truth
    ├── evaluate.py                 harness pengukuran precision & recall
    ├── sample.apk                  APK sintetis (dibangkitkan)
    ├── expected.json               ground truth (dibangkitkan)
    ├── baseline_report.json        angka kondisi awal — dibekukan, jangan ditimpa
    └── hasil_terkini.json          hasil pengukuran terakhir (dibangkitkan)
```

Seluruh isinya aman dikumpulkan. Tidak ada data milik pihak lain, dan seluruh
kredensial pada `sample.apk` adalah nilai palsu yang sengaja dibuat agar cocok
dengan pola analyzer.

### Cara menjalankan

Hanya memakai pustaka standar Python. Tidak ada dependensi yang perlu dipasang.

```bash
cd UTAMA

# 1. Analisis sebuah APK
python3 apk_analyzer.py /path/ke/target.apk

# 2. Membangkitkan ulang APK sampel dan ground truth (opsional)
python3 tests/make_sample_apk.py

# 3. Mengukur precision & recall terhadap sampel
python3 tests/evaluate.py
```

Perintah nomor 3 adalah yang menghasilkan angka pengujian pada laporan.

### Catatan struktur

`tests/evaluate.py` mengimpor `apk_analyzer.py` dari direktori induknya.
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

**Alasan tidak dikumpulkan:** memuat data infrastruktur milik pihak lain yang
tidak selayaknya ikut tersebar dalam berkas pengumpulan. Laporan tidak
memerlukannya, sebab seluruh angka pengujian sudah bersumber dari sampel
sintetis di `UTAMA/tests/`.

Apabila hasil pada APK nyata tetap ingin dibahas di laporan, cukup kutip
angka agregatnya saja — jumlah artefak, level risiko, jumlah temuan — tanpa
melampirkan URL, host, maupun berkas JSON-nya.

Berkas ini tetap berguna sebagai bahan kerja: ia membuktikan bahwa kelemahan
detektor `Heroku API Key` juga muncul pada APK nyata, bukan hanya pada sampel
buatan. Dari 7 kredensial yang dilaporkan pada APK tersebut, seluruhnya
merupakan false positive (6 Heroku, 1 Mailgun).

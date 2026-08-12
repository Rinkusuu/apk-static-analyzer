# Catatan Progres — Proyek Akhir KP: APK Static Analyzer

Berkas ini adalah memori proyek. Sesi Claude yang baru cukup membaca berkas ini
untuk melanjutkan pekerjaan tanpa perlu menelusuri ulang seluruh direktori.

**Terakhir diperbarui:** 2026-08-12

---

## Konteks Proyek

Proyek akhir Kerja Praktik. Program `apk_analyzer.py` **bukan tulisan pemilik
proyek** — kode ini diwariskan dari `ThreatHunter-Toolkit/APK_Analyzer/`
(nama asli `indexandbundle_grep.py`) lalu ditetapkan sebagai proyek akhir yang
akan dilaporkan.

Konsekuensinya, tujuan pekerjaan bukan sekadar "membuat tool jalan", melainkan
**memahami, mengukur, dan memperbaiki** kode tersebut sampai pemiliknya sanggup
mempertanggungjawabkannya saat sidang.

## Cara Kerja Tool (ringkas)

Analisis statis, tanpa dekompilasi dan tanpa menjalankan aplikasi. Pada dasarnya
`grep` terstruktur terhadap isi APK. Empat tahap: ekstrak ZIP → pilih artefak
(`.bundle`/`.dex`/`.so`/manifest) → baca sebagai byte lalu sapu ±25 regex →
akumulasi skor risiko. Penjelasan lengkap ada di `UTAMA/docs/ALUR_KERJA.md`.

## Struktur Direktori

| Path | Status |
|---|---|
| `UTAMA/` | **Dikumpulkan.** Aman, tidak ada data pihak lain |
| `PENDUKUNG/` | **Jangan dikumpulkan.** Hasil analisis APK produksi pihak ketiga |

Aturan lengkap ada di `README.md`.

---

## Yang Sudah Selesai

- [x] Berkas relevan disalin dari `ThreatHunter-Toolkit/APK_Analyzer/` ke `KP/FINAL/`
- [x] Berkas utama diganti nama: `indexandbundle_grep.py` → `apk_analyzer.py`
- [x] Dibangun APK sampel sintetis ber-ground-truth (`UTAMA/tests/make_sample_apk.py`)
- [x] Dibangun harness pengukuran precision & recall (`UTAMA/tests/test_analyzer.py`)
- [x] Baseline "sebelum perbaikan" terkunci di `UTAMA/tests/baseline_report.json`
- [x] Dokumentasi alur kerja lengkap (`UTAMA/docs/ALUR_KERJA.md`, 10 bagian)
- [x] Direktori dipisah `UTAMA/` vs `PENDUKUNG/` agar tidak salah kumpul

## Angka Baseline (sebelum perbaikan apa pun)

Sumber: `UTAMA/tests/baseline_report.json`. Reproduksi: `cd UTAMA && python3 tests/test_analyzer.py`

| Metrik | Nilai |
|---|---|
| True Positive | 19 |
| False Negative | 0 |
| False Positive | 40 |
| Precision | 32.20% |
| Recall | 100.00% |
| Total skor risiko | 3750 |
| Skor dari false positive | 2400 (64%) |

**Seluruh 40 false positive berasal dari satu detektor: `Heroku API Key`**, yang
polanya sesungguhnya hanya UUID generik. Delapan belas detektor lain bersih.

Terkonfirmasi pula pada APK nyata (`PENDUKUNG/hasil_apk_nyata/`): dari 7
kredensial yang dilaporkan, seluruhnya false positive (6 Heroku, 1 Mailgun).

---

## Rencana Berikutnya (urut prioritas)

1. **Perketat/hapus detektor `Heroku API Key`** — satu perubahan, precision
   diperkirakan 32% → 100%. Dampak paling besar dengan usaha paling kecil.
2. **Perbaiki kerentanan Zip Slip** pada `extract_apk()` — `zipfile.extractall()`
   tanpa validasi path.
3. **Normalisasi skor risiko** — saat ini akumulatif tanpa batas atas, sehingga
   ambang 200/100/50 kehilangan daya beda pada APK besar.
4. Pertimbangkan pengurai AXML untuk AndroidManifest.xml (saat ini manifest APK
   nyata praktis tidak terbaca karena binary XML tidak memiliki tanda kutip).
5. Pemisahan modul dan laporan berformat Markdown/HTML — **paling akhir**, hanya
   setelah pemiliknya benar-benar paham alur kodenya.

Daftar keterbatasan lengkap (7 poin) ada di `UTAMA/docs/ALUR_KERJA.md` bagian 9.

---

## Cara Kerja yang Disepakati

- Setiap perbaikan dijelaskan **sebelum** dan **sesudah**, dengan angka dari
  harness pengujian. Tiap perbaikan setara satu subbab laporan.
- **Pemilik proyek yang menjalankan sendiri** `python3 tests/test_analyzer.py`
  setelah tiap perubahan — ini bagian dari proses memahami, bukan formalitas.
- Jangan refactor besar-besaran sebelum alur kodenya dipahami.
- Jangan pernah menyalin isi `PENDUKUNG/` ke dalam `UTAMA/`.

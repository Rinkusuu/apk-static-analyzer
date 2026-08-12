# Catatan Pengembangan — APK Static Analyzer

Berkas ini adalah memori proyek. Sesi Claude yang baru cukup membaca berkas ini
untuk melanjutkan pekerjaan tanpa menelusuri ulang seluruh direktori.

**Terakhir diperbarui:** 2026-08-12

---

## Tentang Proyek

Pengembangan perangkat analisis statis APK Android untuk mendeteksi endpoint dan
kredensial yang terekspos di dalam berkas aplikasi. Dikerjakan sebagai proyek
akhir Kerja Praktik.

Proyek dimulai dari sebuah prototipe yang ditinggalkan pengembang sebelumnya
(`ThreatHunter-Toolkit/APK_Analyzer/indexandbundle_grep.py`) — sebuah skrip
tunggal tanpa dokumentasi, tanpa pengujian, dan tanpa ukuran ketepatan apa pun.
Prototipe itu diambil alih sebagai titik mulai, bukan sebagai produk jadi.

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

## Fase 0 — Kondisi Awal yang Diwarisi

Prototipe berjalan dan mampu menemukan banyak hal, namun:

- tidak ada dokumentasi apa pun mengenai cara kerjanya;
- tidak ada pengujian, sehingga ketepatannya tidak diketahui;
- tidak ada version control;
- keluarannya bercampur dengan hasil analisis APK produksi pihak ketiga.

## Fase 1 — Membangun Fondasi *(selesai)*

- [x] Kode dipindahkan ke struktur proyek tersendiri di `KP/FINAL/`
- [x] Berkas utama diganti nama menjadi `apk_analyzer.py`
- [x] Alur kerja dibedah dan didokumentasikan (`UTAMA/docs/ALUR_KERJA.md`, 10 bagian)
- [x] Direktori dipisah `UTAMA/` vs `PENDUKUNG/` agar data pihak ketiga tidak
      ikut terkumpul
- [x] Repositori git diinisialisasi, di-push ke GitHub privat

## Fase 2 — Membangun Alat Ukur *(selesai)*

- [x] APK sampel sintetis ber-ground-truth (`UTAMA/tests/make_sample_apk.py`) —
      20 kredensial palsu yang wajib terdeteksi, 41 umpan yang tidak boleh
      terdeteksi
- [x] Harness pengukuran precision & recall (`UTAMA/tests/evaluate.py`)
- [x] Angka kondisi awal dibekukan di `UTAMA/tests/baseline_report.json`
- [x] Harness membandingkan otomatis hasil terkini terhadap kondisi awal

## Fase 3 — Perbaikan Ketepatan *(berjalan)*

- [x] **Detektor Heroku API Key diubah ke deteksi berbasis konteks.**
      Pola lama hanyalah pola UUID generik, sehingga setiap request-id maupun
      trace-id di dalam APK dianggap kredensial. Pola baru hanya menerima UUID
      yang didahului label bermakna "heroku". Detektor tidak dihapus, dan
      kemampuannya dibuktikan tetap utuh lewat kunci Heroku berlabel yang
      sengaja ditanam pada sampel.
- [ ] Perbaiki kerentanan Zip Slip pada `extract_apk()`
- [ ] Normalisasi skor risiko

---

## Angka Pengukuran

Reproduksi: `cd UTAMA && python3 tests/evaluate.py`

| Metrik | Kondisi Awal | Sekarang | Perubahan |
|---|---|---|---|
| True Positive | 20 | 20 | tetap |
| False Negative | 0 | 0 | tetap |
| False Positive | 40 | **0** | −40 |
| Precision | 33.33% | **100.00%** | +66.67 poin |
| Recall | 100.00% | 100.00% | tetap |
| Skor risiko | 3885 | 1485 | −2400 |

Seluruh false positive pada kondisi awal berasal dari satu detektor:
`Heroku API Key`. Delapan belas detektor lainnya bersih sejak awal.

Kelemahan yang sama terkonfirmasi pula pada APK produksi nyata
(`PENDUKUNG/hasil_apk_nyata/`): dari 7 kredensial yang dilaporkan, seluruhnya
false positive (6 Heroku, 1 Mailgun).

**Catatan:** `baseline_report.json` sengaja dibekukan dan tidak pernah ditimpa.
Hasil setiap kali dijalankan ditulis ke `hasil_terkini.json`.

---

## Rencana Berikutnya (urut prioritas)

1. **Kerentanan Zip Slip** pada `extract_apk()` — `zipfile.extractall()` tanpa
   validasi path memungkinkan arsip jahat menulis berkas di luar direktori
   tujuan. Perlu diuji dengan APK jahat buatan sendiri.
2. **Normalisasi skor risiko** — saat ini akumulatif tanpa batas atas, sehingga
   ambang 200/100/50 kehilangan daya beda pada APK besar.
3. **Pengurai AXML** untuk AndroidManifest.xml — manifest APK nyata berformat
   binary XML sehingga saat ini praktis tidak terbaca.
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
- Asal-usul prototipe awal tetap dicantumkan apa adanya. Kontribusi proyek ini
  justru menjadi terukur karena titik mulainya jelas.

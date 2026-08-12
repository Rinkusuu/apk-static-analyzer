# Instruksi Proyek — APK Static Analyzer

Pengembangan perangkat analisis statis APK, dikerjakan sebagai proyek akhir
Kerja Praktik. Perlakukan sebagai proyek yang sedang dikembangkan pemiliknya.
Jangan menyebut asal-usul kode, repositori lain, maupun pengembang lain di
berkas mana pun — termasuk pada pesan commit.

## Wajib dibaca lebih dulu

**Baca `PROGRESS.md` sebelum melakukan apa pun di direktori ini.** Berkas itu
memuat konteks proyek, angka baseline, dan rencana berikutnya.

## Wajib diperbarui

**Perbarui `PROGRESS.md` setiap kali ada kemajuan nyata** — berkas dibuat atau
diubah, angka pengujian bergeser, keputusan diambil, atau rencana berubah.
Perbarui bagian "Yang Sudah Selesai", "Angka Baseline", dan "Rencana Berikutnya"
seperlunya, serta tanggal "Terakhir diperbarui".

Yang dicatat adalah **hasil dan keputusan**, bukan riwayat percakapan. Bila satu
prompt tidak menghasilkan perubahan nyata, tidak perlu ada yang dicatat.

## Aturan direktori

- `UTAMA/` — dikumpulkan sebagai tugas. Aman, tidak memuat data pihak lain.
- `PENDUKUNG/` — **jangan pernah dikumpulkan**. Berisi hasil analisis APK
  produksi pihak ketiga (endpoint dan host internal milik orang lain).
- Jangan pernah menyalin isi `PENDUKUNG/` ke dalam `UTAMA/`.
- `UTAMA/tests/` harus tetap bersebelahan dengan `UTAMA/apk_analyzer.py`;
  harness mengimpor modul tersebut dari direktori induknya.

## Cara kerja

- Proyek ini akan dipresentasikan dan dipertanggungjawabkan pemiliknya. Prioritas
  utama adalah **pemiliknya paham**, bukan kodenya cepat selesai.
- Jelaskan setiap perubahan sebelum dan sesudah, sertai angka dari
  `tests/evaluate.py`. Setiap perbaikan setara satu subbab laporan.
- Biarkan pemilik proyek yang menjalankan sendiri pengujiannya.
- Jangan melakukan refactor besar tanpa diminta.

## Menjalankan

```bash
cd UTAMA
python3 apk_analyzer.py <target.apk>     # analisis APK
python3 tests/make_sample_apk.py         # bangkitkan sampel + ground truth
python3 tests/evaluate.py                # ukur precision & recall
```

Hanya memakai pustaka standar Python. Tidak ada dependensi.

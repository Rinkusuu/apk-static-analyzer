# Peluang Pengembangan — Estimasi & Prioritas

Daftar hal yang MASIH bisa ditingkatkan, beserta perkiraan kesulitan, dampak,
dan seberapa layak dikerjakan untuk konteks Kerja Praktik. Berguna dua arah:
(1) memilih pengembangan berikutnya, dan (2) menjawab bila penguji bertanya
"apa rencana pengembangan selanjutnya?".

Skala: **Rendah / Sedang / Tinggi**. "Layak KP" = perkiraan seberapa sepadan
usaha vs nilai tambah untuk laporan (makin tinggi %, makin disarankan).

---

## Ringkasan (urut prioritas)

| # | Peluang | Kesulitan | Dampak | Layak KP |
|---|---|---|---|---|
| 1 | Skoring eksposur endpoint | Sedang | Tinggi | ~80% |
| 2 | Pengurai AXML (manifest biner) | Sedang | Sedang-Tinggi | ~75% |
| 3 | Laporan HTML dari tool | Rendah-Sedang | Sedang | ~65% |
| 4 | Dukungan split APK (.xapk/.apks) | Sedang | Sedang | ~50% |
| 5 | Snapshot Flutter (seperti Hermes untuk Dart) | Tinggi | Sedang | ~30% |
| 6 | Efisiensi memori (baca streaming) | Sedang | Rendah-Sedang | ~35% |
| 7 | Skor kepercayaan per temuan | Sedang | Sedang | ~45% |
| 8 | Kinerja blok Base64 | Rendah-Sedang | Rendah | ~30% |
| 9 | Tambah detektor kredensial baru | Rendah | Rendah | ~40% |
| 10 | Berkas konfigurasi (allowlist host) | Rendah | Rendah | ~25% |

---

## Rincian

**1. Skoring eksposur endpoint — Sedang / Tinggi / ~80%**
Saat ini skor risiko hanya melihat kredensial. Padahal endpoint sensitif (login,
pembayaran) juga eksposur. Buat banyaknya/sensitifnya `app_endpoints` ikut
menaikkan level. *Kesulitan:* keputusan desain bobot + uji ulang model skoring
agar tidak goyah. *Kenapa layak:* menjawab langsung keterbatasan yang tertulis
di laporan, dan terasa "menyelesaikan cerita".

**2. Pengurai AXML — Sedang / Sedang-Tinggi / ~75%**
AndroidManifest.xml di APK asli berformat binary XML, jadi permission &
komponen nyaris tak terbaca. Urai formatnya agar daftar permission (lokasi,
kamera, dsb.) muncul. *Kesulitan:* parser biner baru, tapi lebih sederhana dari
Hermes. *Kenapa layak:* paling "kelihatan" saat demo; permission adalah hal yang
awam pun paham.

**3. Laporan HTML dari tool — Rendah-Sedang / Sedang / ~65%**
Selain JSON, hasilkan berkas HTML ringkas yang enak dibaca (tabel risiko,
daftar endpoint). *Kesulitan:* templating string biasa. *Kenapa layak:* nilai
presentasi tinggi, usaha kecil.

**4. Dukungan split APK (.xapk/.apks) — Sedang / Sedang / ~50%**
Aplikasi modern kadang dibagi jadi beberapa APK dalam satu paket. Deteksi &
proses tiap bagian. *Kesulitan:* penanganan arsip bersarang. *Kenapa sedang:*
berguna tapi belum tentu relevan dengan APK ujimu.

**5. Snapshot Flutter — Tinggi / Sedang / ~30%**
Analog Hermes tapi untuk Dart/Flutter: ekstraksi string dari libapp.so.
*Kesulitan:* format snapshot Flutter lebih rumit & kurang terdokumentasi.
*Kenapa rendah untuk KP:* usaha besar, hanya relevan bila targetmu Flutter.

**6. Efisiensi memori — Sedang / Rendah-Sedang / ~35%**
Kini artefak dibaca seluruhnya ke memori. Untuk berkas ratusan MB, baca
bertahap (streaming). *Kenapa rendah:* APK uji muat di memori; ini optimasi,
bukan fitur.

**7. Skor kepercayaan per temuan — Sedang / Sedang / ~45%**
Beri tiap temuan label keyakinan (tinggi/sedang/rendah), bukan cuma ada/tidak.
*Kenapa menengah:* memperkaya laporan, tapi perlu kalibrasi.

**8. Kinerja blok Base64 — Rendah-Sedang / Rendah / ~30%**
Blok paling lambat. Bisa dipercepat dengan pra-saring kandidat. *Kenapa rendah:*
tidak menambah kemampuan, hanya kecepatan.

**9. Detektor kredensial baru — Rendah / Rendah / ~40%**
Tambah pola penyedia lain (mis. OpenAI, Azure). *Kesulitan:* menyalin pola.
*Kenapa rendah:* mudah, tapi nilai tambahnya kecil & berisiko menambah FP bila
polanya longgar.

**10. Berkas konfigurasi — Rendah / Rendah / ~25%**
Pindahkan `LIBRARY_HOSTS`, ambang, dsb. ke berkas konfigurasi eksternal.
*Kenapa rendah:* kerapian, bukan kemampuan.

---

## Rekomendasi

Bila ingin **satu** pengembangan tambahan yang paling sepadan: **AXML (#2)** —
karena hasilnya kasat mata saat demo. Bila ingin yang paling "menyelesaikan
cerita laporan": **skoring eksposur endpoint (#1)**.

Bila ingin **berhenti**: kondisi sekarang sudah lebih dari cukup untuk KP.
Delapan perbaikan terbukti + parser Hermes + metodologi terukur sudah menjadi
inti laporan yang kuat.

> Catatan kejujuran untuk sidang: keterbatasan yang tersisa BUKAN kelemahan
> laporan. Menuliskannya sebagai "peluang pengembangan" justru menunjukkan kamu
> memahami batas perangkatmu — itu nilai tambah, bukan kekurangan.

# Panduan Memahami Kode — Persiapan Sidang

Dokumen ini menyiapkan kamu menghadapi pertanyaan penguji. Bukan untuk dihafal
kata per kata, tetapi agar konsepnya nempel sehingga kamu bisa menjawab dengan
tenang. Baca `ALUR_KERJA.md` untuk detail; dokumen ini fokus ke **cara
menjawab**.

---

## 1. Pitch 30 detik (buka dengan ini kalau diminta "jelaskan singkat")

> "Perangkat ini menganalisis berkas APK Android secara **statis** — tanpa
> menjalankannya — untuk menemukan endpoint dan kredensial yang terekspos di
> dalam aplikasi. Cara kerjanya seperti `grep` yang sangat terstruktur: APK
> dibuka sebagai ZIP, dipilih berkas yang memuat kode, lalu dipindai dengan
> ±25 pola. Fokus proyek saya bukan sekadar membuatnya jalan, tapi
> **mengukur ketepatannya lalu memperbaikinya** — precision naik dari 33% ke
> 100% dengan recall tetap 100%, dan tiap perbaikan saya buktikan dengan angka."

Kalau cuma satu kalimat ini yang nempel, kamu sudah selamat.

---

## 2. Tiga hal yang WAJIB nempel

1. **Precision 33% → 100%, recall tetap 100%.** Artinya: dulu 2 dari 3 alarm
   palsu; sekarang setiap alarm benar, tanpa ada ancaman yang lolos.
2. **Tool ini `grep` terstruktur, bukan decompiler.** Ia mencocokkan pola teks,
   tidak memahami makna kode. Itu sebabnya cepat, dan juga sebabnya bisa keliru.
3. **Ukur dulu, baru perbaiki.** Saya bangun alat ukur (sampel ber-ground-truth)
   sebelum menyentuh perbaikan, supaya tiap perubahan terbukti, bukan diklaim.

---

## 3. Alur kode dalam 4 langkah (kalau diminta "jelaskan alurnya")

```
1. extract_apk()      APK dibuka sebagai ZIP, diekstrak
2. find_artifacts()   pilih berkas pemuat kode (.bundle/.dex/.so/manifest)
3. analyze_artifact() baca sebagai BYTE, sapu ±25 pola regex
4. (skoring)          temuan -> skor -> level LOW..CRITICAL
```

Tunjuk saja ke empat fungsi ini. Semua ada di `apk_analyzer.py`, dan versi
ber-penjelasan di `apk_analyzer_beranotasi.py`.

---

## 4. Konsep kunci + analogi (biar mudah dijelaskan)

| Konsep | Cara menjelaskannya |
|---|---|
| **Analisis statis** | "Memeriksa aplikasi tanpa menjalankannya. Lawannya analisis dinamis." |
| **Kenapa baca byte, bukan teks** | "Berkas .dex dan .so itu biner. Kalau dipaksa dibaca sebagai teks bisa rusak. Dengan byte, satu mesin yang sama bisa menangani React Native, Kotlin, dan Flutter sekaligus." |
| **Precision vs Recall** | Analogi mesin pemindai bandara. Recall = dari semua benda bahaya berapa yang tertangkap. Precision = dari semua alarm berapa yang benar. |
| **Alert fatigue** | "Kalau alarm palsu terlalu banyak, analis berhenti percaya alarm, dan justru ancaman nyata bisa terabaikan. Makanya precision penting." |
| **Entropi Shannon** | "Ukuran keacakan. Kredensial asli itu acak (entropi tinggi); placeholder seperti 'aaaa' entropinya nol. Dipakai untuk menyaring." |
| **Hermes bytecode** | "Aplikasi React Native modern dikompilasi jadi biner Hermes. Stringnya disimpan berjejalan tanpa pemisah, jadi saya harus baca tabel string internalnya agar tiap string terpotong benar." |
| **Severity + breadth** | "Skor = seberapa berbahaya temuan terparah, ditambah bonus kecil kalau temuan beragam. Jadi satu kunci AWS bocor langsung dianggap kritis, bukan menunggu banyak temuan." |

---

## 5. Bank pertanyaan penguji + jawaban singkat

**T: Kenapa analisis statis, bukan pakai decompiler?**
J: Statis lebih cepat, tidak butuh menjalankan aplikasi, dan cukup untuk
menemukan string yang terekspos (URL, kunci). Decompiler jauh lebih berat dan di
luar lingkup. Keterbatasannya saya sadari dan saya tulis di laporan.

**T: Kenapa precision awalnya hanya 33%?**
J: Satu detektor — "Heroku API Key" — polanya sebenarnya cuma pola UUID biasa,
sehingga setiap request-id dianggap kredensial. Seluruh 40 false positive berasal
dari situ. 18 detektor lain bersih sejak awal.

**T: Bagaimana kamu membuktikan perbaikannya berhasil?**
J: Saya buat APK sampel buatan sendiri yang isinya saya ketahui persis — 20
kredensial yang wajib terdeteksi, 43 umpan yang tidak boleh. Karena jawabannya
diketahui, precision dan recall bisa dihitung objektif sebelum dan sesudah.

**T: Apa itu false positive dan false negative?**
J: False positive = alarm palsu (dilaporkan padahal bukan ancaman). False
negative = ancaman yang lolos (nyata tapi tak terdeteksi). Recall 100% berarti
nol false negative.

**T: Kenapa satu kunci AWS lebih kritis dari empat sertifikat?**
J: Karena skor berbasis temuan TERPARAH, bukan jumlah. Kunci AWS bocor dampaknya
besar; sertifikat sering wajar. Model lama salah — empat sertifikat malah
dianggap lebih kritis dari satu kunci AWS. Model baru memperbaikinya.

**T: Apa itu Hermes dan kenapa perlu penanganan khusus?**
J: Format biner hasil kompilasi React Native. Stringnya berjejalan tanpa
pemisah, jadi regex biasa menangkap sebuah endpoint beserta ekor string
berikutnya. Saya baca tabel string Hermes (daftar offset+panjang) untuk memotong
tiap string tepat pada batasnya. Ini bagian paling teknis dari proyek.

**T: Katanya ada bug Zip Slip, tapi ternyata tidak?**
J: Benar. Saya menduga fungsi ekstraksi rentan Zip Slip, lalu saya uji dengan
APK jahat buatan sendiri. Hasilnya membantah dugaan — pustaka Python sudah aman.
Meski begitu saya tetap tambahkan pemeriksaan eksplisit sebagai lapisan
keamanan tambahan. Intinya: klaim keamanan saya uji, bukan saya percaya
begitu saja.

**T: Bagaimana kamu tahu tool-nya benar? Ada pengujian?**
J: Ada empat uji otomatis: pengukuran precision/recall, uji Zip Slip, uji model
skoring, dan uji ekstraksi Hermes. Ditambah regression untuk false positive yang
pernah muncul. Semua bisa dijalankan lewat menu CLI.

**T: Apa beda `urls` dan `app_endpoints`?**
J: `urls` semua URL apa adanya, termasuk tautan dokumentasi library. `app_endpoints`
hanya endpoint milik aplikasi — host bukan situs library terkenal DAN jalurnya
ber-penanda API. Ini memisahkan permukaan serang asli dari kebisingan.

**T: Kenapa tanpa library eksternal?**
J: Agar mudah dijalankan di mana saja tanpa instalasi, dan agar seluruh logika
transparan — tidak ada "kotak hitam" pihak ketiga. Semua pakai pustaka standar
Python.

**T: Apa keterbatasan tool ini?**
J: (1) Endpoint yang dirakit saat runtime tidak terlihat — ini batas analisis
statis. (2) AndroidManifest.xml biner belum diurai penuh. (3) Skor masih fokus
kredensial, belum menilai eksposur endpoint. Semua saya tulis jujur di bab
keterbatasan.

**T: Apa kontribusi utamamu di proyek ini?**
J: Mengubahnya dari perangkat tanpa ukuran ketepatan menjadi terukur:
membangun pengujian ber-ground-truth, tujuh perbaikan yang tiap satunya
dibuktikan angka, parser Hermes bytecode, dan antarmuka bermenu. Yang paling
menonjol: parser Hermes dan metodologi ukur-lalu-perbaiki.

---

## 6. Kalau ditanya hal yang tidak kamu tahu

Jangan panik dan jangan mengarang. Pola aman:

> "Untuk detail itu saya perlu buka kodenya sebentar — tapi konsepnya begini…"

lalu jelaskan yang kamu paham. Menunjukkan kamu tahu ARAH jawabannya lebih baik
daripada menebak angka/istilah yang salah. Penguji menghargai kejujuran.

Contoh nyata yang bisa kamu pakai: "Saya sempat menduga ada bug Zip Slip, ternyata
setelah diuji tidak — jadi saya terbiasa mengecek dulu, bukan berasumsi."

---

## 7. Peta kode (biar bisa langsung menunjuk saat ditanya)

| Kalau ditanya soal… | Tunjuk ke… |
|---|---|
| Ekstraksi & Zip Slip | `extract_apk()` |
| Hermes bytecode | `extract_hermes_strings()` |
| Pemilihan artefak | `find_artifacts()` |
| Deteksi kredensial | `TOKEN_PATTERNS` + blok E di `analyze_artifact()` |
| Entropi | `calculate_shannon_entropy()` |
| Skoring | blok N di `analyze_artifact()` (severity + breadth) |
| Pemisahan endpoint | `classify_app_endpoint()` + `LIBRARY_HOSTS` |
| Pengujian | folder `tests/` (evaluate, test_zip_slip, test_scoring, test_hermes) |

Versi ber-penjelasan lengkap: `apk_analyzer_beranotasi.py`.

---

## 8. Latihan mandiri (biar makin yakin)

1. Jalankan `python3 apk_cli.py`, pilih menu 3 (Pengujian) — lihat semua lulus.
2. Pilih menu 1, analisis APK, amati tabel risiko dan daftar endpoint.
3. Buka `tests/expected.json` — di situ ada 20 "kredensial ditanam" dan daftar
   "umpan". Cocokkan dengan hasil `evaluate` untuk paham dari mana angka
   precision/recall berasal.
4. Buka `apk_analyzer_beranotasi.py`, baca blok A sampai N sekali. Cukup paham
   GARIS BESARnya, tidak perlu hafal regex.

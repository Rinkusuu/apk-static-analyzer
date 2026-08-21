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
> ±25 pola. Perangkat ini saya rancang dan bangun sendiri selama KP, lalu saya
> terapkan untuk menganalisis aplikasi MyErpskrip — hasilnya 84 URL, 18 endpoint
> aplikasi, dan tidak ada kredensial keras yang tertanam, sehingga risikonya
> LOW."

Kalau cuma satu kalimat ini yang nempel, kamu sudah selamat.

---

## 2. Tiga hal yang WAJIB nempel

1. **Hasil pada MyErpskrip: tidak ada kredensial keras, risiko LOW — tetapi
   seluruh permukaan antarmuka peladen terbaca.** 84 URL, 18 endpoint aplikasi,
   1 WebSocket. Itu temuan utamanya, dan itu yang perlu kamu jelaskan maknanya.
2. **Tool ini `grep` terstruktur, bukan decompiler.** Ia mencocokkan pola teks,
   tidak memahami makna kode. Itu sebabnya cepat, dan juga sebabnya bisa keliru.
3. **Tiap fitur lahir dari karakteristik artefak yang dihadapi.** Bundel Hermes
   menyimpan untai teks berdempetan, kode ter-minify menyerupai kunci API, aset
   gambar tertanam sebagai Base64, dan URL pustaka bercampur dengan alamat
   aplikasi. Empat hal itu yang menuntut pengurai Hermes, deteksi berbasis
   konteks, penolakan magic byte, dan `classify_app_endpoint()`.

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
| **Deteksi berbasis konteks** | "Kunci Heroku bentuknya UUID biasa, sama persis dengan request-id. Jadi tidak bisa dinilai dari bentuknya; harus dilihat labelnya — hanya UUID yang didahului kata 'heroku' yang dianggap kredensial." |
| **Alert fatigue** | "Kalau alarm palsu terlalu banyak, analis berhenti percaya alarm, dan justru ancaman nyata bisa terabaikan. Makanya pola dibuat ketat, bukan asal menangkap." |
| **Entropi Shannon** | "Ukuran keacakan. Kredensial asli itu acak (entropi tinggi); placeholder seperti 'aaaa' entropinya nol. Dipakai untuk menyaring." |
| **Hermes bytecode** | "Aplikasi React Native modern dikompilasi jadi biner Hermes. Stringnya disimpan berjejalan tanpa pemisah, jadi saya harus baca tabel string internalnya agar tiap string terpotong benar." |
| **Severity + breadth** | "Skor = seberapa berbahaya temuan terparah, ditambah bonus kecil kalau temuan beragam. Jadi satu kunci AWS bocor langsung dianggap kritis, bukan menunggu banyak temuan." |

---

## 5. Bank pertanyaan penguji + jawaban singkat

**T: Kenapa analisis statis, bukan pakai decompiler?**
J: Statis lebih cepat, tidak butuh menjalankan aplikasi, dan cukup untuk
menemukan string yang terekspos (URL, kunci). Decompiler jauh lebih berat dan di
luar lingkup. Keterbatasannya saya sadari dan saya tulis di laporan.

**T: Bagaimana kamu memastikan yang dilaporkan itu benar-benar kredensial?**
J: Dengan membuat polanya seketat mungkin. Sebagian besar kunci punya awalan
khas — `AKIA`, `AIza`, `ghp_` — jadi cukup dikenali dari bentuknya. Yang tidak
punya awalan khas, seperti Heroku yang bentuknya UUID biasa, saya nilai dari
konteksnya: hanya diterima kalau didahului label yang menyebut layanannya. Untuk
pola generik saya tambahkan penyaring entropi Shannon supaya placeholder tidak
ikut tertangkap.

**T: Apa itu false positive dan false negative?**
J: False positive = alarm palsu (dilaporkan padahal bukan ancaman). False
negative = ancaman nyata yang justru lolos. Keduanya yang saya tekan lewat
perancangan pola: pola terlalu longgar menghasilkan alarm palsu, pola terlalu
sempit membuat ancaman lolos.

**T: Kenapa satu kunci AWS lebih kritis dari empat sertifikat?**
J: Karena skor saya rancang berbasis temuan TERPARAH, bukan jumlah. Kunci AWS
bocor dampaknya besar; blok sertifikat sering wajar ada. Kalau skor dijumlahkan
begitu saja, empat sertifikat justru akan terlihat lebih kritis daripada satu
kunci AWS — dan itu terbalik dari risiko sebenarnya.

**T: Apa itu Hermes dan kenapa perlu penanganan khusus?**
J: Format biner hasil kompilasi React Native. Stringnya berjejalan tanpa
pemisah, jadi regex biasa menangkap sebuah endpoint beserta ekor string
berikutnya. Saya baca tabel string Hermes (daftar offset+panjang) untuk memotong
tiap string tepat pada batasnya. Ini bagian paling teknis dari proyek.

**T: Perangkat ini membuka arsip dari luar. Apa tidak berbahaya?**
J: Itu justru saya antisipasi. Ada kerentanan bernama Zip Slip — entri arsip
bernama `../../berkas` bisa menulis di luar direktori tujuan. Fungsi ekstraksi
saya memeriksa jalur tiap entri secara eksplisit dan menolak arsip semacam itu,
jadi keamanannya tidak bergantung pada perilaku internal pustaka.

**T: Bagaimana kamu tahu tool-nya berperilaku benar?**
J: Ada tiga uji otomatis untuk fungsi-fungsi kuncinya: penolakan arsip jahat,
model skoring, dan pengurai untai teks Hermes. Semua bisa dijalankan lewat menu
CLI. Selain itu keluaran pemindaian saya periksa kembali terhadap artefaknya.

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
J: Merancang dan membangun perangkatnya dari nol — mesin pemindai 13 blok
deteksi, pengurai untai teks Hermes, model skoring severity + breadth,
pemisahan endpoint aplikasi dari URL pustaka, dan antarmuka bermenu — lalu
menerapkannya untuk menganalisis MyErpskrip. Yang paling menonjol: pengurai
Hermes, karena tanpa itu alamat yang terbaca tidak utuh.

---

## 6. Kalau ditanya hal yang tidak kamu tahu

Jangan panik dan jangan mengarang. Pola aman:

> "Untuk detail itu saya perlu buka kodenya sebentar — tapi konsepnya begini…"

lalu jelaskan yang kamu paham. Menunjukkan kamu tahu ARAH jawabannya lebih baik
daripada menebak angka/istilah yang salah. Penguji menghargai kejujuran.

Contoh nyata yang bisa kamu pakai: "Saya tidak berasumsi pustaka standar sudah
aman terhadap Zip Slip — saya periksa jalur tiap entri sendiri, supaya
jaminannya tersurat di kode saya."

---

## 7. Peta kode (biar bisa langsung menunjuk saat ditanya)

| Kalau ditanya soal… | Tunjuk ke… |
|---|---|
| Alur analisis satu APK | `analyze_apk()` (dipakai bersama CLI & mode langsung) |
| Ekstraksi & Zip Slip | `extract_apk()` |
| Hermes bytecode | `extract_hermes_strings()` |
| Pemilihan artefak | `find_artifacts()` |
| Deteksi kredensial | `TOKEN_PATTERNS` + blok E di `analyze_artifact()` |
| Entropi | `calculate_shannon_entropy()` |
| Skoring | blok N di `analyze_artifact()` (severity + breadth) |
| Pemisahan endpoint | `classify_app_endpoint()` + `LIBRARY_HOSTS` |
| Pengujian | folder `tests/` (test_zip_slip, test_scoring, test_hermes) |

Versi ber-penjelasan lengkap: `apk_analyzer_beranotasi.py`.

---

## 8. Latihan mandiri (biar makin yakin)

1. Jalankan `python3 apk_cli.py`, pilih menu 3 (Pengujian) — lihat semua lulus.
2. Pilih menu 1, analisis `MyErpskrip.apk`, amati tabel risiko dan daftar
   endpoint.
3. Buka `MyErpskrip_analysis_<tanggal>/reverse_results.json`, baca bagian
   `summary` tiap artefak. Dari situlah angka pada laporan berasal — pastikan
   kamu bisa menunjuk angkanya langsung kalau ditanya.
4. Buka `apk_analyzer_beranotasi.py`, baca blok A sampai N sekali. Cukup paham
   GARIS BESARnya, tidak perlu hafal regex.

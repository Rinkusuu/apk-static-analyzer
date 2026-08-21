# Latihan Pilihan Ganda — Uji Pemahaman

Kerjakan SEBELUM mendalami kode, lalu ulang SESUDAH membaca
`apk_analyzer_beranotasi.py`. Bandingkan skormu — kenaikannya menunjukkan
pemahamanmu bertambah. Kunci jawaban + penjelasan ada di bagian akhir; jangan
diintip dulu.

Target: bisa menjawab ≥ 16 dari 20 dengan yakin sebelum sidang.

---

### 1. Apa yang dilakukan "analisis statis" pada perangkat ini?
- A. Menjalankan APK di emulator lalu mengamati perilakunya
- B. Memeriksa isi APK tanpa menjalankan aplikasinya
- C. Mendekompilasi APK menjadi kode Java yang terbaca
- D. Memantau lalu lintas jaringan aplikasi saat dipakai

### 2. Sebuah berkas APK pada dasarnya adalah…
- A. Berkas biner khusus Android yang hanya bisa dibuka Android Studio
- B. Basis data terenkripsi
- C. Arsip ZIP dengan struktur direktori baku
- D. Berkas teks berisi kode sumber

### 3. Mengapa artefak dibaca sebagai BYTE, bukan teks?
- A. Agar lebih cepat dibaca
- B. Karena Python tidak bisa membaca teks
- C. Agar satu mesin pola yang sama bisa menangani berkas teks maupun biner
- D. Agar hasilnya terenkripsi

### 4. Hasil pemindaian MyErpskrip menunjukkan risiko `LOW`. Artinya…
- A. Aplikasi sudah pasti aman sepenuhnya
- B. Tidak ditemukan kredensial keras yang tertanam; skor memang menilai kebocoran kredensial
- C. Perangkat gagal membaca artefaknya
- D. Aplikasi tidak memakai jaringan

### 5. Meski risikonya `LOW`, temuan yang tetap perlu disorot pada MyErpskrip adalah…
- A. Ukuran APK yang besar
- B. Permukaan antarmuka peladen terbaca sepenuhnya — 18 endpoint aplikasi dan 1 WebSocket
- C. Jumlah berkas dex yang banyak
- D. Versi Android yang didukung

### 6. Mengapa alamat endpoint yang terbaca itu tetap penting dilaporkan?
- A. Karena aplikasi seharusnya menyembunyikan alamatnya
- B. Karena keamanan tidak boleh bertumpu pada anggapan alamatnya tidak diketahui orang
- C. Karena alamat itu bisa dihapus dari aplikasi
- D. Karena jumlahnya banyak

### 7. Entropi Shannon dipakai untuk…
- A. Mengukur ukuran berkas
- B. Membedakan nilai acak (kredensial asli) dari yang berulang (placeholder)
- C. Mengenkripsi hasil
- D. Menghitung jumlah URL

### 8. Mengapa bundle Hermes perlu penanganan khusus?
- A. Karena terenkripsi
- B. Karena string-nya disimpan berjejalan tanpa pemisah antar-string
- C. Karena berukuran sangat besar
- D. Karena memakai format JSON

### 9. Solusi untuk masalah Hermes adalah…
- A. Mendekompilasi bytecode-nya
- B. Membaca tabel string (offset + panjang) untuk memotong tiap string di batasnya
- C. Mengabaikan berkas Hermes
- D. Menjalankan aplikasinya

### 10. Pada model skoring baru, satu kunci AWS dibandingkan empat sertifikat…
- A. Empat sertifikat lebih kritis (jumlah lebih banyak)
- B. Keduanya sama
- C. Satu kunci AWS lebih kritis (skor berbasis temuan terparah)
- D. Keduanya diabaikan

### 11. Apa itu "false positive"?
- A. Ancaman nyata yang lolos
- B. Alarm yang dilaporkan padahal bukan ancaman
- C. Berkas yang gagal dibaca
- D. Skor yang terlalu rendah

### 12. Apa itu "false negative"?
- A. Alarm palsu
- B. Ancaman nyata yang justru terlewat
- C. Hasil yang benar
- D. Duplikat temuan

### 13. Mengapa false positive yang banyak berbahaya, meski tak ada ancaman yang lolos?
- A. Membuat perangkat lambat
- B. Membuat analis mengabaikan alarm (alert fatigue), sehingga ancaman nyata bisa terlewat
- C. Menghabiskan memori
- D. Tidak berbahaya sama sekali

### 14. Beda `urls` dan `app_endpoints`?
- A. Tidak ada beda
- B. `app_endpoints` hanya endpoint milik aplikasi (host non-library + jalur ber-penanda API)
- C. `urls` hanya untuk Flutter
- D. `app_endpoints` adalah URL yang terenkripsi

### 15. Penanganan Zip Slip pada fungsi ekstraksi adalah…
- A. Membiarkannya, karena pustaka Python dianggap sudah aman
- B. Memeriksa jalur tiap entri secara eksplisit dan menolak arsip yang menulis di luar direktori tujuan
- C. Mengenkripsi hasil ekstraksi
- D. Melewati berkas berukuran besar

### 16. Kategori seperti URL dan permission bersifat "inventarisasi", artinya…
- A. Menaikkan skor risiko
- B. Memperkaya laporan tetapi tidak dianggap tuduhan (tidak menaikkan skor)
- C. Diabaikan sepenuhnya
- D. Hanya untuk React Native

### 17. Mengapa perangkat tidak memakai pustaka eksternal?
- A. Karena Python melarangnya
- B. Agar mudah dijalankan di mana saja dan seluruh logika transparan
- C. Agar lebih lambat
- D. Karena tidak ada pustaka yang cocok

### 18. Keterbatasan yang MELEKAT pada analisis statis adalah…
- A. Tidak bisa membaca file besar
- B. Endpoint yang dirakit saat runtime tidak akan terlihat
- C. Tidak bisa membuka ZIP
- D. Selalu salah mendeteksi

### 19. Pola `key-[0-9a-f]{32}` dipilih, bukan `key-[0-9a-zA-Z]{32}`, karena…
- A. Lebih pendek ditulis
- B. Mengikuti format heksadesimal yang sesungguhnya, agar identifier JavaScript ter-minify tidak ikut tertangkap
- C. Huruf besar tidak didukung Python
- D. Agar pemindaian lebih cepat

### 20. Fungsi uji regresi pada folder `tests/` adalah…
- A. Mempercepat perangkat
- B. Memastikan fungsi kunci tetap berperilaku sesuai rancangan saat kode berubah
- C. Menambah fitur baru
- D. Mengurangi ukuran kode

---

## Kunci Jawaban & Penjelasan

1. **B** — Statis = tanpa menjalankan. (Bukan C: perangkat TIDAK mendekompilasi.)
2. **C** — APK = arsip ZIP; itu sebabnya cukup modul `zipfile`.
3. **C** — Byte membuat satu mesin pola menangani teks (.bundle) & biner (.dex/.so).
4. **B** — `LOW` = tidak ada kredensial keras. Bukan A: skor tidak menilai
   seluruh aspek keamanan aplikasi.
5. **B** — 84 URL, 18 endpoint aplikasi, 1 WebSocket terbaca dari berkas yang
   didistribusikan, tanpa dekompilasi.
6. **B** — Alamat endpoint memang harus tertulis agar dapat dihubungi; karena
   itu tiap endpoint wajib punya pengamanan sendiri di sisi peladen.
7. **B** — Acak → entropi tinggi (kredensial); berulang → rendah (placeholder).
8. **B** — String berjejalan tanpa pemisah → regex menangkap ekor string tetangga.
9. **B** — Baca tabel string Hermes (offset+panjang), potong di batas asli.
10. **C** — Skor = severity (temuan terparah); AWS berbobot lebih tinggi.
11. **B** — False positive = alarm palsu.
12. **B** — False negative = ancaman yang lolos.
13. **B** — Alert fatigue: analis berhenti percaya alarm → ancaman nyata terlewat.
14. **B** — `app_endpoints` menyaring host library & mensyaratkan jalur API.
15. **B** — Jaminan keamanan dibuat tersurat di kode sendiri, tidak dititipkan
    pada perilaku internal pustaka.
16. **B** — Inventarisasi memperkaya laporan tetapi bukan tuduhan → tak menaikkan skor.
17. **B** — Mudah dijalankan, transparan, tanpa "kotak hitam" pihak ketiga.
18. **B** — Endpoint yang baru terbentuk saat runtime tak terlihat oleh analisis statis.
19. **B** — Format asli Mailgun heksadesimal; pola longgar akan menangkap
    identifier JavaScript ter-minify.
20. **B** — Uji regresi menjaga perilaku fungsi kunci tetap sesuai rancangan.

**Skor:**
- 16–20 benar: sangat siap. Fokus latih menjelaskan lisan.
- 11–15 benar: paham garis besar; ulang bagian yang salah + baca anotasi terkait.
- ≤ 10 benar: baca dulu `PANDUAN_MEMAHAMI_KODE.md` bagian 2 & 4, lalu ulangi.

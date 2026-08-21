# Ringkasan Aplikasi MyErpskrip (Aplikasi yang Dianalisis)

Dokumen ini merangkum profil teknis aplikasi **MyErpskrip** — aplikasi yang
dianalisis menggunakan Static APK Analyzer pada Kerja Praktik ini. Disusun untuk
dipakai sebagai Project Knowledge saat penulisan laporan.

Seluruh isi dokumen ini berasal dari analisis statis terhadap berkas APK
(`AndroidManifest.xml`, `assets/app.config`, `assets/index.android.bundle`, dan
berkas `.dex`). **Tidak ada nama host maupun jalur endpoint internal yang
dicantumkan di sini**; detail konkret tersebut hanya berada di `PENDUKUNG/` dan
tidak boleh masuk laporan.

---

## 1. Identitas Aplikasi

| Atribut | Nilai |
|---|---|
| Nama aplikasi | MyErpskrip |
| Nama paket | `com.qnn.myerpskrip` |
| Versi | 1.0.0 |
| Pemilik proyek (konfigurasi Expo) | `queen-network` (PT Queen Network Nusantara) |
| Platform target | Android (konfigurasi juga menyertakan iOS dan web) |
| Ukuran berkas APK | 52,6 MB (± 60 MB setelah diekstrak) |
| Aktivitas utama | `com.qnn.myerpskrip.MainActivity` |
| Orientasi | Portrait, tema mengikuti sistem |

**Fungsi aplikasi (disimpulkan dari penamaan endpoint dan komponen):** aplikasi
layanan pelanggan untuk penyedia jasa internet — mencakup autentikasi berbasis
OTP, penagihan dan pembayaran (tagihan, paket internet, transaksi), pengajuan
tiket gangguan, notifikasi, serta data teknis pelanggan. Kesimpulan fungsi ini
bersifat inferensi dari artefak; bila laporan menuliskannya sebagai fakta,
sebaiknya dikonfirmasi lebih dulu ke pembimbing lapangan.

## 2. Teknologi yang Dipakai

| Lapisan | Teknologi terdeteksi |
|---|---|
| Kerangka kerja | React Native dengan **Expo SDK 54**, `expo-router` (typed routes) |
| Arsitektur | *New Architecture* aktif, *React Compiler* aktif |
| Mesin JavaScript | **Hermes** — kode dikemas sebagai *bytecode* (versi 96), bukan JS teks |
| Notifikasi | Firebase Cloud Messaging + `expo-notifications` |
| Modul Expo lain | `expo-media-library`, `expo-splash-screen`, `expo-task-manager`, `expo-updates`, `expo-file-system` |
| Pustaka Android | AndroidX, Kotlin Coroutines, OkHttp, Glide, `react-native-webview`, SoLoader |
| Proteksi distribusi | Pembungkus lisensi Play (`com.pairip.*`), penandaan `STAMP_TYPE_DISTRIBUTION_APK` |

Implikasi terpenting bagi perangkat analisis: **seluruh logika aplikasi berada
di dalam bundel Hermes**, bukan di `classes*.dex`. Bundel Hermes adalah berkas
biner yang menyimpan seluruh string secara berjejalan tanpa pemisah, sehingga
pemindaian byte mentah tidak dapat mengetahui batas antar-string.

## 3. Izin dan Komponen pada AndroidManifest

**Izin utama:** `INTERNET`, `ACCESS_NETWORK_STATE`, `POST_NOTIFICATIONS`,
`READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `READ_MEDIA_IMAGES`,
`READ_MEDIA_VISUAL_USER_SELECTED`, `ACCESS_MEDIA_LOCATION`,
`RECEIVE_BOOT_COMPLETED`, `SYSTEM_ALERT_WINDOW`, `VIBRATE`, `WAKE_LOCK`,
`BIND_JOB_SERVICE`, `DUMP`, serta sejumlah izin *badge* khusus peluncur
(Samsung, Huawei, Oppo, HTC, Sony).

**Komponen utama:** `MainActivity`; penyedia berkas
(`FileSystemFileProvider`, `fileprovider`, `RNCWebViewFileProvider`); layanan
pesan Firebase dan Expo (`FirebaseMessagingService`,
`ExpoFirebaseMessagingService`); penerima siaran tugas latar
(`TaskBroadcastReceiver`, `TaskJobService`); `ProfileInstallReceiver`; serta
`LicenseActivity` dari pembungkus lisensi.

Catatan: manifest tersimpan dalam format **binary XML (AXML)**, bukan XML teks.
Perangkat analisis belum memiliki pengurai AXML, sehingga isinya hanya terbaca
sebagian melalui pemindaian string.

## 4. Artefak yang Dianalisis

Enam artefak diidentifikasi dan dipindai:

| Artefak | Ukuran | Keterangan |
|---|---|---|
| `assets/index.android.bundle` | 10,86 MB | Bundel **Hermes bytecode** — artefak paling padat informasi |
| `classes.dex` | 9,27 MB | Kode Java/Kotlin pustaka pendukung |
| `classes3.dex` | 8,35 MB | idem |
| `classes4.dex` | 7,60 MB | idem |
| `classes2.dex` | 32,8 KB | idem |
| `AndroidManifest.xml` | 26,0 KB | Binary XML |

## 5. Ringkasan Hasil Analisis

Angka agregat dari `reverse_results.json` hasil pemindaian:

| Kategori | Jumlah |
|---|---|
| URL ter-inventaris (bersih) | 84 |
| Endpoint aplikasi terisolasi | 18 (seluruhnya pada host backend aplikasi) |
| WebSocket | 1 |
| Jalur API standalone | 1 |
| Kata kunci sensitif pada bundel | 24 |
| Kredensial keras (`api_keys_and_tokens`) | 0 |
| Rahasia hasil dekode Base64 | 0 |
| Kunci penyimpanan lokal | 0 |
| Tingkat risiko | LOW |

Tafsir yang benar untuk laporan: **tidak ditemukan kredensial keras yang
tertanam pada MyErpskrip.** Tingkat risiko `LOW` menyatakan tidak adanya
kebocoran kredensial, bukan berarti aplikasi tanpa catatan — permukaan antarmuka
peladen tetap terbaca sepenuhnya dari berkas yang didistribusikan tanpa perlu
mendekompilasi maupun menjalankan aplikasi, dan hal itu adalah temuan
tersendiri.

## 6. Karakteristik yang Membentuk Rancangan Perangkat

Empat karakteristik aplikasi ini yang secara langsung menentukan bagaimana
perangkat analisis harus bekerja:

1. **Bundel Hermes.** Menuntut pembacaan tabel untai teks Hermes; tanpa itu
   alamat terekstrak dalam keadaan bersambung dengan untai tetangga.
2. **Kode JavaScript ter-*minify*.** Identifier acak hasil minifikasi mudah
   menyerupai bentuk kunci API, sehingga menuntut pola deteksi berbasis konteks.
3. **Aset biner tertanam.** Gambar PNG/WEBP di dalam bundel mudah tertuduh
   sebagai rahasia terenkode Base64, sehingga menuntut penolakan berbasis
   *magic byte*.
4. **Ratusan URL dokumentasi pustaka.** Menuntut pemisahan antara endpoint milik
   aplikasi dan URL milik pustaka pihak ketiga.

Keempat karakteristik itu adalah ciri umum aplikasi React Native modern,
sehingga penanganan yang dirancang untuk menjawabnya berlaku pula bagi aplikasi
sejenis, bukan hanya untuk satu aplikasi.

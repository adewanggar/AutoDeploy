# AutoDeploy for Windows Server

AutoDeploy adalah aplikasi continuous deployment (CI/CD) otomatis untuk Windows Server (cocok untuk VPS yang diakses via RDP). Aplikasi ini memastikan repository Git di VPS otomatis di-*pull* dan aplikasi di-*restart* setiap kali ada commit baru di GitHub, sekaligus menjaga proses deploy tetap berjalan di background meskipun sesi RDP di-*disconnect* atau di-*sign out*.

Dibangun dengan prinsip **/ponytail** (minimal, efisien, zero bloatware, engine 100% Python standard library) dan **/antislop-ui** (UI PySide6 yang bersih, fungsional, kontras tinggi, bebas dari elemen kosmetik AI generik).

---

## 1. Arsitektur

AutoDeploy membagi tanggung jawab menjadi dua mode melalui satu entry point `main.py`:

```
+-----------------------------------------------------------------------+
|                             main.py                                   |
+-----------------------------------+-----------------------------------+
                                    |
          (tanpa argumen)           |          (--engine)
                 v                  |               v
+---------------------------------+ | +---------------------------------+
|       GUI Monitor (PySide6)     | | |     Headless Deploy Engine      |
|---------------------------------| | |---------------------------------|
| - Manajemen Proyek              | | | - Webhook HTTP Server (stdlib)  |
| - Trigger Deploy Manual         | | | - Background Git Poller         |
| - Riwayat & Drilldown Log       | | | - Eksekusi Step & Auto Rollback |
| - Kontrol Engine (Start/Stop)   | | | - Notifikasi Telegram           |
| - Konfigurasi Global & Preset   | | | - Berjalan di Background VPS    |
+---------------------------------+ | +---------------------------------+
                 \                  |                  /
                  \                 v                 /
             +---------------------------------------------+
             |   %ProgramData%\AutoDeploy\                 |
             |   - config.json    (pengaturan proyek)      |
             |   - history.jsonl  (riwayat 500 deploy)     |
             |   - engine.log     (log sistem engine)      |
             |   - engine.pid     (PID proses background)  |
             +---------------------------------------------+
```

1. **Engine (Headless)**:
   - Dijalankan via `python main.py --engine` atau lewat Windows Task Scheduler saat sistem *boot*.
   - Menggunakan 100% Python Standard Library (`http.server`, `subprocess`, `threading`, `hmac`, `urllib`, `json`, `hashlib`).
   - Memantau perubahan `config.json` secara *real-time* (cek mtime tiap 3 detik), memuat ulang otomatis tanpa perlu restart.
   - Mengelola Webhook listener dan worker thread Git Polling.

2. **GUI (PySide6)**:
   - Dijalankan via `python main.py`.
   - Mengatur semua konfigurasi, memantau status engine, melihat riwayat eksekusi langkah per langkah.
   - Semua operasi berat (tes Git, tes Telegram, manual deploy) dijalankan di background thread (`QThreadPool`), UI dijamin tidak pernah freeze.
   - **Menutup GUI TIDAK menghentikan Engine.**

---

## 2. Cara Menjalankan

### Persyaratan
- Windows 10/11 atau Windows Server 2016/2019/2022/2025.
- Python 3.10+
- Git for Windows terpasang di system PATH.
- Dependensi GUI: `PySide6` (`pip install PySide6`). *(Engine headless tidak membutuhkan PySide6).*

### Menjalankan GUI Pengaturan
```powershell
python main.py
```

### Menjalankan Engine Headless Manual
```powershell
python main.py --engine
```

---

## 3. Setup Persistence di Windows Server (Task Scheduler)

Agar Engine otomatis berjalan saat Windows Server menyala dan **tetap berjalan saat Anda disconnect atau sign out dari RDP**, daftarkan Engine ke Windows Task Scheduler:

### Cara 1: Menggunakan Perintah `schtasks` (Rekomendasi)
Buka Command Prompt atau PowerShell sebagai **Administrator**:

```cmd
schtasks /create /tn "AutoDeployEngine" /tr "\"C:\Users\<User>\AppData\Local\Programs\Python\Python310\pythonw.exe\" \"D:\Other\AutoDeploy\main.py\" --engine" /sc onstart /ru SYSTEM /rl HIGHEST /f
```
*(Catatan: Anda juga bisa menyalin perintah exact yang sudah otomatis terisi path sistem Anda langsung dari tab **Global Settings** di GUI).*

### Cara 2: Dari GUI AutoDeploy
1. Buka GUI `python main.py`.
2. Klik tombol **Start Engine** di bar bagian atas.
3. Buka tab **Global Settings**, klik **Copy schtasks Command**, lalu jalankan di terminal Administrator.

---

## 4. Dua Jenis Trigger Per Project

Setiap project dapat diatur untuk merespons salah satu atau kedua pemicu:

### A. Webhook (GitHub)
- HTTP Server (`ThreadingHTTPServer`) berjalan pada host dan port yang bisa diatur (default `0.0.0.0:9876`).
- Endpoint: `POST http://<IP-VPS>:9876/hook/<project_id>`
- **Verifikasi Keamanan HMAC SHA256**: Engine memeriksa header `X-Hub-Signature-256`. Jika secret salah atau absen, engine mengembalikan `403 Forbidden`.
- **Payload Limit**: Body request dibatasi maksimal 1 MB (payload di atas 1MB ditolak dengan `413 Payload Too Large`).
- **Branch Matching**: Memeriksa `ref` payload push. Hanya branch yang cocok (misal `refs/heads/main`) yang akan memicu deploy.
- **Ping Handler**: Event `ping` dari GitHub langsung direspons dengan `200 OK (pong)`.

### B. Polling
- Cocok jika VPS berada di belakang NAT, firewall ketat, atau sulit membuka port masuk.
- Engine secara berkala (default tiap 60 detik) menjalankan `git ls-remote origin <branch>` di folder repo VPS.
- Membandingkan commit hash remote dengan `git rev-parse HEAD` lokal. Jika ada commit baru, deploy otomatis dipicu.

---

## 5. Alur Deployment & Keamanan

1. **Per-Project Lock**:
   - Hanya 1 deployment berjalan per proyek dalam satu waktu.
   - Jika ada commit baru masuk saat deploy sedang berjalan, engine mengantrekan maksimal 1 deployment berikutnya (`pending`).
2. **Commit Snapshot**:
   - Engine mencatat commit SHA lokal sebelum langkah deploy dijalankan.
3. **Eksekusi Steps Berurutan**:
   - Menjalankan setiap perintah shell yang dikonfigurasi di folder repo project.
   - Default: `git fetch origin main` lalu `git reset --hard origin/main`.
   - Dapat ditambah langkah build: `pip install -r requirements.txt`, `npm ci`, `npm run build`, dll.
4. **Restart Command**:
   - Jika seluruh steps berhasil (exit code 0), engine mengeksekusi `restart_command`.
5. **Rollback Otomatis Saat Gagal**:
   - Jika salah satu step gagal (exit code != 0 atau timeout): eksekusi dihentikan.
   - Jika opsi `rollback_on_failure` aktif: engine menjalankan `git reset --hard <old_commit>` lalu menjalankan ulang `restart_command`. Status dicatat sebagai `rolled_back`.
6. **Keamanan Eksekusi Shell**:
   - Isi payload GitHub **tidak pernah dimasukkan ke baris perintah shell**. Perintah hanya berasal dari `config.json` yang diatur admin.
7. **Pencatatan Riwayat (JSONL)**:
   - Disimpan di `%ProgramData%\AutoDeploy\history.jsonl`.
   - Menyimpan maksimal 500 riwayat terakhir (waktu, durasi, trigger, commit lama/baru, pesan commit, author, log output tiap langkah).
8. **Notifikasi Telegram**:
   - Mengirim notifikasi HTML otomatis saat deploy sukses, gagal, atau di-rollback via Telegram Bot API (menggunakan `urllib.request` standard library).

---

## 6. Preset Restart Command untuk Windows

Di dalam form project GUI, disediakan dropdown preset restart yang langsung mengisi perintah yang siap disesuaikan:

| Tipe Aplikasi | Contoh Perintah Preset |
|---|---|
| **Windows Service** | `net stop "NamaService" & net start "NamaService"` |
| **NSSM** | `nssm restart NamaService` |
| **PM2 (Node.js)** | `pm2 restart nama-app` |
| **Docker Compose** | `docker compose up -d --build` |
| **IIS App Pool** | `%windir%\system32\inetsrv\appcmd recycle apppool /apppool.name:"NamaPool"` |
| **Proses Standalone** | `taskkill /F /IM nama.exe & start "" /D "C:\apps\path" "nama.exe"` |
| **Custom** | Bebas mengisi perintah apa pun |

---

## 7. Keputusan Desain & Resolusi Hal Ambigu

Sesuai instruksi *"kalau ada yang ambigu, ambil keputusan yang masuk akal dan catat di README"*, berikut adalah keputusan arsitektur yang diambil:

1. **Lokasi Penyimpanan Data (`%ProgramData%\AutoDeploy`)**:
   - `%ProgramData%` dipilih karena dapat diakses secara global oleh semua akun Windows Server dan service `SYSTEM`. Jika permissions terbatasi pada environment tertentu, AutoDeploy otomatis fallback ke `~/.autodeploy` di folder profil user.
2. **Deteksi Proses Engine (`engine.pid`)**:
   - Menggunakan Win32 API (`OpenProcess` dan `GetExitCodeProcess` via `ctypes` stdlib). Jika proses crash atau mati tidak normal, file PID basi otomatis dibersihkan saat dicek tanpa perlu intervensi manual.
3. **Eksekutor Python untuk Engine (`pythonw.exe`)**:
   - Helper Task Scheduler dan Start Engine memprioritaskan `pythonw.exe` daripada `python.exe`. Hal ini mencegah munculnya jendela konsol hitam yang mengganggu saat server menyala atau login RDP.
4. **Quoting Shell pada Windows (`cmd.exe`)**:
   - Pada Windows, `cmd.exe /s /c "<command>"` digunakan untuk mencegah `subprocess.list2cmdline` merusak tanda kutip ganda internal pada perintah bertingkat (misalnya perintah Python one-liner atau chaining `&`).
5. **Mekanisme Antrean Deploy**:
   - Jika commit baru masuk saat deploy sedang berlangsung, status `pending` diaktifkan (maksimal 1 antrean per project). Begitu deploy selesai, antrean akan langsung dieksekusi satu kali untuk memastikan VPS selalu sinkron dengan commit paling mutakhir tanpa menumpuk puluhan proses bertumpuk.
6. **Limit Riwayat 500 Entri**:
   - Pemotongan berkas `history.jsonl` dilakukan secara atomik melalui file sementara (`.tmp`) dengan mekanisme lock thread sehingga riwayat aman dari korupsi data saat diakses bersamaan oleh GUI dan Engine.

---

## 8. Verifikasi & Pengujian

Tersedia rangkaian pengujian bawaan tanpa dependensi pihak ketiga:
```powershell
# Uji unit modul inti (config, HMAC, shell runner, history)
python tests/test_core.py

# Uji end-to-end deploy (git steps, fail & auto-rollback)
python tests/test_deploy_e2e.py

# Uji end-to-end Webhook (signature HMAC, ping, ref filter, payload limit)
python tests/test_webhook_e2e.py

# Uji kelayakan GUI (PySide6 offscreen mode)
python tests/test_gui.py
```
Semua pengujian lolos 100% dan terverifikasi di environment Windows.

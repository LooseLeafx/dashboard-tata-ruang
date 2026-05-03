# 📋 PANDUAN DEPLOYMENT, MAINTENANCE & KEAMANAN
## Dashboard Tata Ruang - Daerah Istimewa Yogyakarta

---

## 📌 DAFTAR ISI
1. [Opsi Deployment](#opsi-deployment)
2. [Langkah-Langkah Deployment](#langkah-langkah-deployment)
3. [Workflow Update & Maintenance](#workflow-update--maintenance)
4. [Best Practices Keamanan](#best-practices-keamanan)
5. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## 🚀 OPSI DEPLOYMENT

### Opsi 1: **Streamlit Cloud** (RECOMMENDED - Termudah)
**Pros:**
- ✅ Gratis untuk public repository
- ✅ Deployment otomatis dari GitHub
- ✅ SSL/HTTPS included
- ✅ Scaling otomatis
- ✅ Maintenance minimal

**Cons:**
- ❌ Free tier ada batasan resource
- ❌ Perlu repository publik (atau upgrade berbayar)
- ❌ Data disimpan di cloud

**Cost:** Free (untuk repo publik) atau $5-$99/bulan untuk private

---

### Opsi 2: **Heroku** (Alternatif Populer)
**Pros:**
- ✅ Mudah setup dengan Git push
- ✅ Free tier tersedia (tapi dibatasi)
- ✅ Support berbagai bahasa

**Cons:**
- ❌ Free tier sudah tidak tersedia (November 2022)
- ❌ Minimal $7/bulan untuk dynos

**Cost:** $7+/bulan

---

### Opsi 3: **VPS/Server Sendiri** (Control Penuh)
**Providers:** Linode, DigitalOcean, AWS, Azure, GCP

**Pros:**
- ✅ Kontrol penuh
- ✅ Data stay in your server
- ✅ Custom configuration
- ✅ Scaling flexible

**Cons:**
- ❌ Perlu expertise DevOps
- ❌ Maintenance lebih kompleks
- ❌ Cost bervariasi ($5-100+/bulan)

**Cost:** $5-100+/bulan tergantung provider & spec

---

### Opsi 4: **Docker + Kubernetes** (Enterprise)
**Pros:**
- ✅ Portable & scalable
- ✅ Dapat deploy di berbagai platform

**Cons:**
- ❌ Setup lebih kompleks
- ❌ Perlu expertise Kubernetes

---

### 📊 REKOMENDASI UNTUK ANDA
**Tahap 1 (Sekarang):** **Streamlit Cloud**
- Cepat online dalam hitungan menit
- Gratis untuk public repo
- Perfect untuk testing & production small-scale

**Tahap 2 (Jika sudah besar):** **VPS (DigitalOcean/Linode)**
- Kontrol penuh
- Data aman di server sendiri
- Biaya terjangkau

---

## 📝 LANGKAH-LANGKAH DEPLOYMENT

### **METODE 1: STREAMLIT CLOUD (RECOMMENDED)**

#### Step 1: Persiapkan GitHub Repository
```bash
# 1. Buat folder untuk git (jika belum)
cd "e:\CODING\DASHBOARD TATA RUANG"

# 2. Inisialisasi git repository
git init

# 3. Tambahkan semua file
git add .

# 4. Initial commit
git commit -m "Initial commit: Dashboard Tata Ruang"

# 5. Tambahkan remote GitHub
git remote add origin https://github.com/USERNAME/dashboard-tata-ruang.git
git branch -M main
git push -u origin main
```

#### Step 2: Persiapkan File Konfigurasi
Buat file `.streamlit/config.toml` di project root:

```toml
[theme]
primaryColor = "#27ae60"
backgroundColor = "#eef2f0"
secondaryBackgroundColor = "#ffffff"
textColor = "#0b3327"
font = "sans serif"

[client]
showErrorDetails = false
toolbarMode = "minimal"

[server]
maxUploadSize = 200
enableCORS = false
enableXsrfProtection = true
```

#### Step 3: Persiapkan File requirements.txt
```bash
# Generate requirements dari environment Anda
pip freeze > requirements.txt
```

Edit `requirements.txt` dan pastikan hanya package yang diperlukan:
```
streamlit>=1.28.0
pandas>=1.5.0
geopandas>=0.13.0
folium>=0.14.0
streamlit-folium>=0.15.0
plotly>=5.0.0
gspread>=5.10.0
oauth2client>=4.1.3
google-auth-oauthlib>=1.1.0
google-auth-httplib2>=0.2.0
google-api-python-client>=2.100.0
requests>=2.31.0
fiona>=1.9.0
```

#### Step 4: Daftar ke Streamlit Cloud
1. Buka https://share.streamlit.io
2. Klik "Sign up"
3. Login dengan GitHub account
4. Authorize Streamlit

#### Step 5: Deploy aplikasi
1. Klik "New app"
2. Pilih repository: `dashboard-tata-ruang`
3. Branch: `main`
4. File path: `app.py`
5. Klik "Deploy"

**Tunggu 3-5 menit** sampai aplikasi selesai di-deploy.

#### Step 6: Share URL
URL akan seperti: `https://dashboard-tata-ruang.streamlit.app`

---

### **METODE 2: VPS (DigitalOcean/Linode)**

#### Step 1: Buat Droplet/Linode
- OS: Ubuntu 22.04 LTS
- Size: $6/bulan (1GB RAM) untuk start

#### Step 2: Setup Server
```bash
# SSH ke server
ssh root@YOUR_SERVER_IP

# Update system
apt update && apt upgrade -y

# Install Python & dependencies
apt install -y python3 python3-pip python3-venv git nginx

# Clone repository
cd /home && git clone https://github.com/USERNAME/dashboard-tata-ruang.git
cd dashboard-tata-ruang

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Test run
streamlit run app.py
```

#### Step 3: Setup Nginx Reverse Proxy
```bash
# Edit /etc/nginx/sites-available/default
sudo nano /etc/nginx/sites-available/default
```

Tambahkan:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Streamlit websocket
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

#### Step 4: Setup Systemd Service
```bash
# Buat file service
sudo nano /etc/systemd/system/streamlit.service
```

Isi:
```ini
[Unit]
Description=Streamlit Tata Ruang
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/dashboard-tata-ruang
Environment="PATH=/home/dashboard-tata-ruang/venv/bin"
ExecStart=/home/dashboard-tata-ruang/venv/bin/streamlit run app.py --server.port=8501 --server.address=localhost
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Jalankan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable streamlit
sudo systemctl start streamlit
sudo systemctl status streamlit
```

#### Step 5: SSL/HTTPS (dengan Let's Encrypt)
```bash
apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 🔄 WORKFLOW UPDATE & MAINTENANCE

### Workflow Pengembangan & Deployment

#### **Saat Ada Update Fitur:**

```
1. Development (Lokal di VS Code)
   ├─ Buat fitur baru
   ├─ Test di lokal: streamlit run app.py
   ├─ Pastikan tidak ada error
   └─ Commit: git add . && git commit -m "Fitur: ..."

2. Push ke GitHub
   └─ git push origin main

3. Automatic Deployment (Streamlit Cloud)
   └─ Streamlit Cloud otomatis re-deploy dalam 2-3 menit

4. Testing di Production
   └─ Buka https://dashboard-tata-ruang.streamlit.app
   └─ Verifikasi fitur berjalan dengan baik

5. If Error
   ├─ Kembali ke VS Code
   ├─ Fix bug
   ├─ Commit: git add . && git commit -m "Fix: ..."
   └─ git push origin main (Streamlit akan re-deploy)
```

#### **Checklist Sebelum Deploy:**

```
☐ Semua fitur sudah di-test di lokal
☐ Tidak ada error di console
☐ requirements.txt sudah update
☐ credentials.json sudah di-.gitignore
☐ API keys/tokens sudah aman (di-hardcode? JANGAN!)
☐ Code sudah di-commit dengan pesan yang jelas
☐ Push ke GitHub branch main
☐ Tunggu deploy selesai (check status di Streamlit Cloud)
☐ Test fitur di production URL
```

---

### Git Commands Yang Sering Digunakan

```bash
# 1. Check status file
git status

# 2. Tambah file spesifik
git add app.py
git add .streamlit/config.toml

# 3. Commit dengan pesan deskriptif
git commit -m "Fitur: Tambah pencarian lokasi di peta"
git commit -m "Fix: Tabel mini SRS sekarang tampilkan semua data"
git commit -m "Update: Upgrade Streamlit ke v1.30"

# 4. Push ke GitHub
git push origin main

# 5. Lihat commit history
git log --oneline

# 6. Kembali ke versi sebelumnya (jika error)
git revert HEAD
# atau
git reset --hard HEAD~1
```

---

### Git Flow (Untuk Team Development - Optional)

Jika nanti akan ada team:

```bash
# 1. Buat branch untuk fitur baru
git checkout -b feature/nama-fitur

# 2. Kerja di branch itu
# ... edit code ...
git add .
git commit -m "Fitur: ..."

# 3. Push branch
git push origin feature/nama-fitur

# 4. Buat Pull Request di GitHub (untuk review)

# 5. Merge ke main (setelah di-review)
# Automatic deploy di Streamlit Cloud
```

---

## 🔐 BEST PRACTICES KEAMANAN

### 1️⃣ CREDENTIAL MANAGEMENT

#### ❌ JANGAN LAKUKAN INI:
```python
# WRONG - API Key di hardcode!
API_KEY = "123456789abcdef"
GOOGLE_CREDS = {
    "type": "service_account",
    "project_id": "my-project",
    ...
}
```

#### ✅ LAKUKAN INI:
```python
# RIGHT - Gunakan environment variables
import os

API_KEY = os.getenv("API_KEY")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "credentials.json")

# Load dari file (yang di-.gitignore)
with open(GOOGLE_CREDS_PATH) as f:
    GOOGLE_CREDS = json.load(f)
```

#### Setup di Streamlit Cloud:
1. Dashboard > Settings > Secrets
2. Tambahkan secrets:
```
GOOGLE_CREDS = {
  "type": "service_account",
  "project_id": "...",
  ...
}

API_KEY = "your-api-key"
MYSQL_PASSWORD = "..."
```

Access di code:
```python
import streamlit as st

google_creds = st.secrets["GOOGLE_CREDS"]
api_key = st.secrets["API_KEY"]
```

---

### 2️⃣ FILE .gitignore

Buat `.gitignore` di root folder:
```
# Credentials & API Keys
credentials.json
drive_config.json
kunci_akses.json
secrets.toml
.env
.env.local

# Cache
__pycache__/
*.pyc
.pytest_cache/
.streamlit/
*.db

# Data sensitif
*.xlsx
*.xls
*.csv
*.kmz
data_*.json

# Dependencies
venv/
env/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
```

---

### 3️⃣ DATABASE & DATA SECURITY

#### Jika menggunakan database:
```python
# WRONG
connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="12345",  # ❌ Hardcoded!
    database="tata_ruang"
)

# RIGHT
import os
connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)
```

#### Backup Data
```bash
# Backup database (monthly)
mysqldump -u user -p database_name > backup_$(date +%Y%m%d).sql

# Restore jika diperlukan
mysql -u user -p database_name < backup_20240503.sql

# Simpan backup di multiple locations
# - Local storage
# - Google Drive
# - Backup service (AWS S3, Backblaze, dll)
```

---

### 4️⃣ ACCESS CONTROL

#### Jika hanya untuk internal (DIY):

**Option A: HTTP Basic Auth (Simple)**
```python
import streamlit as st

# Check password
password = st.text_input("Password:", type="password", key="login_pass")

if password != st.secrets.get("DASHBOARD_PASSWORD", ""):
    st.error("❌ Password salah")
    st.stop()

# Jika password benar, tampilkan dashboard
st.success("✅ Login sukses")
# ... rest of app
```

**Option B: Custom Auth dengan Google**
```python
# Buat service account di Google Cloud Console
# Hanya izinkan email tertentu
ALLOWED_USERS = [
    "user1@dikistimewa.go.id",
    "user2@dikistimewa.go.id"
]

# Implementasi Google OAuth (lebih kompleks)
# Atau gunakan library: streamlit-authenticator
```

#### Jika untuk publik (terbuka):
- Anonimkan data sensitif
- Tidak tampilkan alamat/lokasi detail
- Rate limiting untuk prevent abuse
- Monitoring access logs

---

### 5️⃣ HTTPS & ENCRYPTION

#### Streamlit Cloud
- ✅ Otomatis HTTPS (https://dashboard-tata-ruang.streamlit.app)
- ✅ SSL certificate dari Let's Encrypt

#### VPS Sendiri
```bash
# Install Let's Encrypt
sudo certbot --nginx -d dashboard.dikistimewa.go.id

# Auto-renew
sudo systemctl enable certbot.timer
```

---

### 6️⃣ MONITORING & LOGGING

#### Log Access
```python
# Di app.py, tambahkan logging
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dashboard.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Log setiap kali ada user akses
logger.info(f"User accessed dashboard at {datetime.now()}")

# Log setiap kali ada query/filter
logger.info(f"User filtered by SRS: {selected_srs}")
```

#### Check Logs (VPS)
```bash
# Real-time logs
tail -f /home/dashboard-tata-ruang/dashboard.log

# Last 100 lines
tail -n 100 dashboard.log

# Search specific message
grep "error" dashboard.log
```

---

### 7️⃣ RATE LIMITING

```python
import time
from collections import defaultdict

# Prevent abuse
request_times = defaultdict.defaultdict(list)
MAX_REQUESTS_PER_HOUR = 100

def check_rate_limit(user_id="public"):
    now = time.time()
    one_hour_ago = now - 3600
    
    # Hapus request yang lebih dari 1 jam lalu
    request_times[user_id] = [
        t for t in request_times[user_id] 
        if t > one_hour_ago
    ]
    
    if len(request_times[user_id]) >= MAX_REQUESTS_PER_HOUR:
        return False
    
    request_times[user_id].append(now)
    return True

# Gunakan di app
if not check_rate_limit():
    st.error("❌ Terlalu banyak request. Coba lagi nanti.")
    st.stop()
```

---

## 📊 MONITORING & TROUBLESHOOTING

### Monitoring di Streamlit Cloud

1. **Buka Dashboard:** https://share.streamlit.io
2. **Pilih app Anda**
3. **Tab "Manage":**
   - ✅ View logs
   - ✅ Check resource usage
   - ✅ View recent deploys

### Common Issues & Solusi

#### Issue 1: "ModuleNotFoundError: No module named 'xyz'"
```bash
# Solusi:
# 1. Install di lokal
pip install xyz

# 2. Update requirements.txt
pip freeze > requirements.txt

# 3. Commit & push
git add requirements.txt
git commit -m "Update: Add xyz package"
git push

# 4. Streamlit Cloud akan auto-install
```

#### Issue 2: "Credentials not found" error
```bash
# Solusi:
# 1. Check .gitignore (jangan ada di repo)
# 2. Upload ke Streamlit Cloud secrets:
#    Settings > Secrets
# 3. Akses via st.secrets["GOOGLE_CREDS"]
```

#### Issue 3: "Permission denied" saat akses file
```python
# Streamlit Cloud tidak punya write permission ke /tmp
# Solusi: Gunakan st.session_state untuk temporary data

if "temp_data" not in st.session_state:
    st.session_state.temp_data = []

# atau simpan ke database/cloud storage
```

#### Issue 4: Aplikasi lambat/timeout
```python
# Solusi:
# 1. Cache query results
@st.cache_data(ttl=3600)  # Cache 1 jam
def load_data():
    return pd.read_csv("data.csv")

# 2. Limit data yang ditampilkan
df_display = df.head(1000)  # Tampilkan max 1000 rows

# 3. Use columns yang penting saja
df = df[['important_col1', 'important_col2']]
```

---

## ✅ MAINTENANCE CHECKLIST

### Daily
- [ ] Monitor error logs
- [ ] Check if app is running (status page)

### Weekly
- [ ] Test fitur utama
- [ ] Backup database
- [ ] Check Streamlit Cloud logs

### Monthly
- [ ] Update dependencies
  ```bash
  pip list --outdated
  pip install --upgrade streamlit pandas geopandas
  pip freeze > requirements.txt
  ```
- [ ] Review access logs
- [ ] Backup database to external storage
- [ ] Test recovery dari backup

### Quarterly
- [ ] Security audit
- [ ] Performance optimization
- [ ] Code review

### Annually
- [ ] Update SSL certificate (auto-renew if using Let's Encrypt)
- [ ] Upgrade OS packages
- [ ] Database optimization/cleanup

---

## 📞 GETTING HELP

### Useful Resources
- Streamlit Docs: https://docs.streamlit.io
- Streamlit Community: https://discuss.streamlit.io
- Stack Overflow: Tag `streamlit`

### If Something Breaks
1. Check logs (Streamlit Cloud atau VPS)
2. Search error message di Google
3. Test di lokal terlebih dahulu
4. Ask di Streamlit Community Forum
5. Revert ke commit sebelumnya jika perlu

```bash
# Revert last commit
git revert HEAD
git push
```

---

**Last Updated:** May 3, 2026
**Version:** 1.0

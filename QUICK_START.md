# 🚀 QUICK START - PANDUAN CEPAT

Ikuti langkah-langkah ini untuk deploy dashboard dalam 15 menit!

---

## 📋 Yang Anda Butuhkan

- ✅ GitHub Account (gratis di https://github.com)
- ✅ Project folder (sudah ada: `e:\CODING\DASHBOARD TATA RUANG`)
- ✅ `credentials.json` (sudah ada)
- ✅ 15 menit waktu

---

## 🎯 TIMELINE

```
0-2 min   : Setup GitHub repository
2-5 min   : Push code ke GitHub
5-10 min  : Setup Streamlit Cloud
10-15 min : Deploy & test
```

---

## ✅ STEP-BY-STEP GUIDE

### STEP 1: Create GitHub Repository (2 menit)

Buka https://github.com/new

**Isi form:**
```
Repository name: dashboard-tata-ruang
Description: Dashboard tata ruang DIY
Visibility: Public (jika gratis) atau Private
Add .gitignore: Python
```

Click **"Create repository"**

Sekarang Anda akan lihat halaman repo yang kosong dengan instruksi.

### STEP 2: Push Code ke GitHub (3 menit)

Buka VS Code Terminal:

```
Ctrl+` (backtick)
```

Copy & paste commands ini satu per satu:

```bash
# 1. Ganti "USERNAME" dengan username GitHub Anda
cd "e:\CODING\DASHBOARD TATA RUANG"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/dashboard-tata-ruang.git
git branch -M main
git push -u origin main
```

**Hasil yang diharapkan:**
```
Enumerating objects: ...
Counting objects: ...
Compressing objects: ...
Writing objects: ... done
Total ... (...)
...
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

✅ **Code Anda sekarang di GitHub!**

### STEP 3: Setup Streamlit Cloud (5 menit)

1. Buka https://share.streamlit.io
2. Click **"Sign up"**
3. Click **"Continue with GitHub"**
4. Authorize Streamlit
5. Tunggu sebentar, kemudian Anda akan redirect ke dashboard

### STEP 4: Deploy App (3 menit)

Di Streamlit Cloud dashboard:

1. Click **"New app"**
2. Isi form:
   ```
   Repository: USERNAME/dashboard-tata-ruang
   Branch: main
   File path: app.py
   ```
3. Click **"Deploy"**

Sekarang aplikasi sedang di-deploy. Tunggu sampai berubah dari:
- 🟡 Running → 🟢 Done

**Selesai! 🎉**

Streamlit akan memberi Anda URL:
```
https://dashboard-tata-ruang.streamlit.app
```

Bagikan URL ini ke orang lain!

---

## 📝 SETELAH DEPLOY - WORKFLOW

### Jika ingin update fitur:

**Workflow singkat:**
```
1. Edit code di VS Code
2. Test lokal: streamlit run app.py
3. Ctrl+Shift+G → Stage changes
4. Ketik message → Commit
5. Click "Push"
6. Tunggu 2-3 menit auto-deploy
```

### Jika ada error:

```
1. Check error di https://share.streamlit.io > app > "Manage" > logs
2. Fix di VS Code
3. Commit & push
4. Streamlit auto-deploy ulang
```

---

## 🚫 PENTING: JANGAN LUPA INI!

### ❌ Jangan push credentials!

**Sebelum push, verifikasi:**

```
Ctrl+Shift+G (Source Control)
```

Pastikan TIDAK ada file:
- `credentials.json` ❌
- `drive_config.json` ❌  
- `kunci_akses.json` ❌

Jika ada, hapus dari staging:
```
Right-click file → "Discard Changes"
```

### ✅ Upload credentials ke Streamlit Cloud

**Jangan di-hardcode, upload sebagai Secret:**

1. https://share.streamlit.io > app > Settings
2. Tab **"Secrets"**
3. Paste isi `credentials.json`:

```
GOOGLE_CREDS = {
  "type": "service_account",
  "project_id": "...",
  ...
}
```

4. Click **"Save"**

Di code, akses:
```python
import streamlit as st
google_creds = st.secrets["GOOGLE_CREDS"]
```

---

## 📊 MONITORING

### Check if app is online:

Buka: https://dashboard-tata-ruang.streamlit.app

Jika loading, buka logs:
```
https://share.streamlit.io 
→ Click app Anda
→ Tab "Manage"
→ "Recent deploys" 
→ Click latest → "Logs"
```

### Common errors:

| Error | Solution |
|-------|----------|
| "ModuleNotFoundError" | Update `requirements.txt` dan push |
| "Credentials not found" | Upload ke Settings > Secrets |
| "App takes forever to load" | Data terlalu besar, optimize |
| "Permission denied" | Check credentials format |

---

## 🎓 NEXT STEPS

### Baca dokumentasi lengkap:
- `README.md` - Fitur & usage
- `DEPLOYMENT_GUIDE.md` - Detail deployment & maintenance
- `VS_CODE_GIT_WORKFLOW.md` - Git workflow detail
- `SECURITY_CHECKLIST.md` - Keamanan data

### Bikin fitur baru:

```bash
# 1. Create feature branch
git checkout -b feature/nama-fitur

# 2. Edit code di VS Code
# 3. Test: streamlit run app.py
# 4. Commit & push
git add .
git commit -m "Feature: ..."
git push origin feature/nama-fitur

# 5. Merge ke main (via GitHub)
# 6. Auto-deploy
```

### Monitor & maintain:

- Daily: Cek app status
- Weekly: Check logs
- Monthly: Update dependencies
- Backup database regularly

---

## ❓ TROUBLESHOOTING

### App tidak muncul?

```
1. Check internet connection
2. Refresh browser
3. Check URL: https://dashboard-tata-ruang.streamlit.app
4. Check logs di Streamlit Cloud
5. If error, check requirements.txt
```

### Mau reset/restart?

```
Streamlit Cloud > App > Manage > Reboot
```

### Mau hapus app?

```
Streamlit Cloud > App > Manage > Settings > Dangerous Zone > Delete
```

---

## 💬 PERLU BANTUAN?

### Resources:
- **Streamlit Docs:** https://docs.streamlit.io
- **Streamlit Forum:** https://discuss.streamlit.io
- **Stack Overflow:** Tag `streamlit`
- **GitHub Issues:** Buka issue di repository

### Checklist jika ada error:

- [ ] Internet connection OK?
- [ ] Cek logs di Streamlit Cloud?
- [ ] Credentials ter-upload ke Secrets?
- [ ] `requirements.txt` updated?
- [ ] Push ke GitHub success?
- [ ] Tunggu 5 menit untuk deploy?

---

## 🎉 SELAMAT!

Anda sekarang punya dashboard online yang bisa diakses siapa saja!

**URL untuk share:**
```
https://dashboard-tata-ruang.streamlit.app
```

---

**Next:** Baca `DEPLOYMENT_GUIDE.md` untuk understanding lebih dalam  
**Questions?** Check `README.md` atau search di Google  
**Last Updated:** May 3, 2026

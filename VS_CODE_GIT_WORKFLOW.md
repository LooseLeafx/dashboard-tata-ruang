# 💻 VS CODE WORKFLOW & GIT INTEGRATION GUIDE

Panduan praktis menggunakan VS Code untuk develop dan deploy dashboard Streamlit.

---

## 🎯 SETUP VS CODE EXTENSIONS (Recommended)

### Install Extensions Ini:

1. **Git Graph** (melihat git history secara visual)
   - Extension ID: `mhutchie.git-graph`
   - Gunakan: View commit history, branch management

2. **GitLens** (advanced git info)
   - Extension ID: `eamodio.gitlens`
   - Gunakan: Blame, history per file, commit info

3. **Python**
   - Extension ID: `ms-python.python`
   - Gunakan: Code formatting, debugging

4. **Pylance** (Python language server)
   - Extension ID: `ms-python.vscode-pylance`
   - Gunakan: Autocomplete, type checking

5. **Streamlit** (syntax highlighting)
   - Extension ID: `devsense.streamlit-support`
   - Gunakan: Streamlit-specific snippets

6. **Thunder Client** (API testing)
   - Extension ID: `rangav.vscode-thunder-client`
   - Gunakan: Test API endpoints

7. **Markdown Preview Enhanced** (markdown preview)
   - Extension ID: `shd101wyy.markdown-preview-enhanced`
   - Gunakan: Preview documentation

### Install via VS Code:
```
Ctrl+Shift+X (Extensions)
Cari extension → Click Install
```

---

## 📁 SETUP WORKSPACE

### Langkah 1: Buka Folder Project

```
File > Open Folder
→ Pilih: e:\CODING\DASHBOARD TATA RUANG
→ Click "Select Folder"
```

### Langkah 2: Setup Python Environment

```
Ctrl+Shift+P (Command Palette)
→ Type: "Python: Select Interpreter"
→ Choose: ./env/Scripts/python.exe (atau ./venv/Scripts/python.exe)
```

### Langkah 3: Setup Git

```
Ctrl+Shift+G (Open Source Control)
→ Atau: View > Source Control
```

Sekarang Anda bisa melihat Git panel di sidebar kiri.

---

## 🔄 GIT WORKFLOW - STEP BY STEP

### SCENARIO 1: Pertama Kali Setup Git

#### Step 1: Inisialisasi Repository

```
Ctrl+` (Open Terminal)
Ketik:

cd e:\CODING\DASHBOARD TATA RUANG
git init
git add .
git commit -m "Initial commit: Dashboard Tata Ruang v1.0"
```

#### Step 2: Add Remote GitHub

```
git remote add origin https://github.com/USERNAME/dashboard-tata-ruang.git
git branch -M main
git push -u origin main
```

**ATAU Lewat VS Code:**

```
Ctrl+Shift+P
→ Type: "Git: Add Remote"
→ Masukkan URL: https://github.com/USERNAME/dashboard-tata-ruang.git
→ Masukkan nama: origin
```

---

### SCENARIO 2: Bikin Fitur Baru & Push

#### Workflow:

```
┌─────────────────────────────┐
│ 1. Create Feature Branch    │
├─────────────────────────────┤
│ 2. Edit Code di VS Code     │
├─────────────────────────────┤
│ 3. Test Locally             │
├─────────────────────────────┤
│ 4. Commit Changes           │
├─────────────────────────────┤
│ 5. Push ke GitHub           │
├─────────────────────────────┤
│ 6. Auto Deploy (Streamlit)  │
└─────────────────────────────┘
```

#### Langkah Detail:

**1️⃣ CREATE BRANCH**

```
Ctrl+Shift+P
→ Type: "Git: Create Branch"
→ Masukkan nama: feature/tambah-fitur-xy
```

Atau di Terminal:
```bash
git checkout -b feature/tambah-fitur-xy
```

**2️⃣ EDIT CODE**

Di VS Code, edit `app.py` atau file lainnya seperti biasa.

**3️⃣ TEST LOCALLY**

```
Ctrl+` (Terminal)
streamlit run app.py
```

- Browser terbuka di `http://localhost:8501`
- Test fitur yang baru
- Jika error, fix di VS Code
- Streamlit akan auto-reload

**4️⃣ COMMIT CHANGES**

Via VS Code (Recommended):

```
Ctrl+Shift+G (Source Control panel)
├─ CHANGES section
│  ├─ Click "+" untuk stage semua atau
│  └─ Click "+" per file untuk stage selective
├─ Scroll ke atas ke "Message" box
├─ Ketik commit message: "Feature: Tambah fitur xy"
└─ Click ✓ (Commit button)
```

Via Terminal:

```bash
git add .
git commit -m "Feature: Tambah fitur xy"
```

**5️⃣ PUSH KE GITHUB**

Via VS Code:

```
Ctrl+Shift+G (Source Control)
→ Click "Publish Branch" atau "Push"
```

Via Terminal:

```bash
git push origin feature/tambah-fitur-xy
```

**6️⃣ MERGE KE MAIN (Create Pull Request)**

**Option A: Via GitHub.com**

1. Buka https://github.com/USERNAME/dashboard-tata-ruang
2. Click "Compare & pull request" (biasanya auto-muncul)
3. Buat PR, review sendiri, klik "Merge pull request"
4. Streamlit Cloud otomatis deploy

**Option B: Via Terminal (Direct Merge)**

```bash
# Switch ke main branch
git checkout main

# Pull latest main
git pull origin main

# Merge feature branch
git merge feature/tambah-fitur-xy

# Push ke GitHub
git push origin main

# Streamlit Cloud otomatis deploy
# Tunggu 2-5 menit
```

---

### SCENARIO 3: Bug Fix (Hot Fix)

#### Workflow:

```
Production Error
    ↓
Create hotfix branch
    ↓
Fix bug di VS Code
    ↓
Test lokal
    ↓
Commit & push
    ↓
Merge ke main
    ↓
Auto-deploy
```

#### Langkah:

```bash
# Buat hotfix branch
git checkout -b hotfix/bug-xy

# ... fix code ...
# Test: streamlit run app.py

# Commit
git add .
git commit -m "Fix: Bug xy di tabel SRS"

# Push
git push origin hotfix/bug-xy

# Merge ke main (langsung via GitHub atau terminal)
git checkout main
git merge hotfix/bug-xy
git push origin main
```

---

## 📝 COMMIT MESSAGE BEST PRACTICES

### Format:
```
<type>: <subject>

<body (optional)>
```

### Types:
- `Feature:` Fitur baru
- `Fix:` Bug fix
- `Update:` Update dependencies/dokumentasi
- `Refactor:` Improve code quality
- `Docs:` Dokumentasi
- `Style:` Formatting, tidak ada logic change
- `Performance:` Performance improvements

### Examples:

✅ BAIK:
```
Feature: Tambah pencarian lokasi di peta
Fix: Tabel mini SRS sekarang tampilkan semua data
Update: Upgrade Streamlit ke v1.30
Refactor: Improve geocoding function
Docs: Tambah deployment guide
```

❌ TIDAK BAIK:
```
update
fix stuff
wip
asdf
todo
```

---

## 🔍 USEFUL VS CODE SHORTCUTS

| Shortcut | Action |
|----------|--------|
| `Ctrl+K Ctrl+W` | Close current tab |
| `Ctrl+Shift+P` | Command Palette (paling penting!) |
| `Ctrl+F` | Find di file |
| `Ctrl+H` | Find & Replace |
| `Ctrl+/` | Comment/uncomment |
| `Ctrl+D` | Select next occurrence |
| `Alt+↑/↓` | Move line up/down |
| `Ctrl+X` | Delete line |
| `Ctrl+Shift+K` | Delete line |
| `F5` | Debug mode |
| `Ctrl+`` | Toggle terminal |

---

## 📊 GIT STATUS CHECK

### Melihat Status:

```
Ctrl+Shift+G (Source Control)
```

Anda akan lihat:
```
CHANGES: 3
├─ modified: app.py
├─ new file: .streamlit/config.toml
└─ new file: .gitignore

STAGED CHANGES: 2
├─ modified: app.py
└─ new file: .streamlit/config.toml
```

Atau via Terminal:
```bash
git status
git diff            # Lihat perubahan detail
git diff --cached   # Lihat staged changes
```

---

## 🔙 UNDO CHANGES

### Scenario 1: Belum di-stage

```bash
# Lihat perubahan
git diff app.py

# Undo (revert ke versi sebelumnya)
git checkout -- app.py
# atau
git restore app.py
```

### Scenario 2: Sudah di-stage

```bash
# Unstage file
git reset app.py

# Undo changes
git checkout -- app.py
```

### Scenario 3: Sudah di-commit

```bash
# Undo last commit (keep changes)
git revert HEAD

# Atau: reset to previous commit (hard)
git reset --hard HEAD~1
```

**⚠️ WARNING:** `--hard` akan menghapus semua changes. Gunakan dengan hati-hati!

---

## 📡 SYNC DENGAN REMOTE

### Pull dari GitHub

Jika ada changes di GitHub (dari device lain atau merge PR):

```bash
git pull origin main
```

Via VS Code:
```
Ctrl+Shift+G
→ Click "Pull" (simbol download)
```

### Push ke GitHub

```bash
git push origin main
```

Via VS Code:
```
Ctrl+Shift+G
→ Click "Push" (simbol upload)
```

### Check Remote Status

```bash
# Lihat branch tracking
git branch -vv

# Lihat remote info
git remote -v
```

---

## 🌿 BRANCH MANAGEMENT

### Lihat Branches

```bash
# Local branches
git branch

# Remote branches
git branch -r

# Semua branches
git branch -a
```

### Switch Branch

```bash
# Via terminal
git checkout main
git checkout feature/xy

# Via VS Code
Ctrl+Shift+P
→ Type: "Git: Checkout to..."
→ Pilih branch
```

### Delete Branch

```bash
# Local
git branch -d feature/xy

# Remote
git push origin --delete feature/xy
```

---

## 📊 VIEW COMMIT HISTORY

### Via Git Graph Extension

```
Ctrl+Shift+G (atau View > Source Control)
→ Click "Git Graph" (gambar timeline)
```

Anda akan lihat:
- Visual commit history
- Branch tree
- Merge points
- Click commit untuk lihat detail

### Via Terminal

```bash
# Simple log
git log --oneline

# Detailed log
git log --oneline --graph --all

# By author
git log --author="John"

# Last 5 commits
git log -5
```

---

## 🚀 STREAMLIT CLOUD AUTO-DEPLOY

### Setelah push ke GitHub (main branch):

1. **Deploy otomatis mulai**
   - Streamlit Cloud detect push baru
   - Check `requirements.txt`
   - Install dependencies
   - Start aplikasi

2. **Monitor di Streamlit Cloud**
   ```
   https://share.streamlit.io
   → Pilih app Anda
   → Tab "Manage"
   → Lihat "Recent deploys"
   ```

3. **Status deploy**
   - 🟡 "Running" = Sedang deploy
   - 🟢 "Done" = Deploy sukses
   - 🔴 "Failed" = Ada error

4. **Jika error**
   - Click deploy yang error
   - Lihat logs
   - Fix di VS Code
   - Commit & push lagi

---

## ✅ CHECKLIST SEBELUM PUSH

Sebelum `git push`, pastikan:

- [ ] Semua test lokal PASS
- [ ] Tidak ada error di console/terminal
- [ ] `requirements.txt` sudah update (jika install package baru)
- [ ] `.gitignore` proper (jangan ada credentials)
- [ ] Commit message jelas dan deskriptif
- [ ] Code sudah di-review (baca ulang)
- [ ] Tidak ada file yang tidak sengaja di-add

---

## 🆘 COMMON ISSUES & SOLUTIONS

### Issue 1: "fatal: not a git repository"

```bash
# Solusi:
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/repo.git
git push -u origin main
```

### Issue 2: "Your branch is behind origin/main"

```bash
# Solusi (update ke latest):
git pull origin main
```

### Issue 3: "CONFLICT: Merge conflict in file.py"

```bash
# Open file tersebut di VS Code
# Edit conflict markers (<<<<<<, ======, >>>>>>)
# Save
git add file.py
git commit -m "Resolve merge conflict"
git push
```

### Issue 4: "Permission denied (publickey)"

Biasanya karena GitHub SSH key belum di-setup. Solusi:

```bash
# Buat SSH key
ssh-keygen -t ed25519 -C "your@email.com"

# Add key ke ssh-agent
eval $(ssh-agent -s)
ssh-add ~/.ssh/id_ed25519

# Copy public key dan add ke GitHub Settings
cat ~/.ssh/id_ed25519.pub

# Test connection
ssh -T git@github.com
```

Atau gunakan HTTPS + PAT (Personal Access Token) lebih mudah.

---

## 📚 REFERENCE COMMANDS

### Essential Git Commands

```bash
# Cek status
git status

# Stage files
git add .              # semua file
git add app.py         # file spesifik

# Commit
git commit -m "message"

# Push
git push origin main

# Pull
git pull origin main

# View history
git log --oneline

# Undo last commit
git revert HEAD

# Switch branch
git checkout -b feature/xy

# Merge branch
git merge feature/xy
```

---

**Last Updated:** May 3, 2026  
**Version:** 1.0

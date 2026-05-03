# 🌿 Dashboard Tata Ruang - Daerah Istimewa Yogyakarta

Aplikasi Streamlit untuk visualisasi dan analisis data kegiatan keistimewaan urusan tata ruang tahun 2020-2025 di Daerah Istimewa Yogyakarta.

## 📋 Fitur Utama

- **📊 Rekapitulasi Data**: Dashboard interaktif dengan metrik dan visualisasi
- **🗺️ Peta Interaktif**: Peta choropleth SRS dengan layer tambahan dan pencarian lokasi
- **📄 Data Lengkap**: Tabel data dengan filter dan pencarian
- **📁 Data Pendukung**: Manajemen data dan metadata
- **🎨 Upload Custom Layer**: Tambah layer KMZ/KML/SHP sendiri
- **🔍 Pencarian Lokasi**: Cari lokasi di peta dengan Nominatim API

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- pip atau conda
- Git (untuk deployment)

### Installation

```bash
# Clone repository
git clone https://github.com/USERNAME/dashboard-tata-ruang.git
cd dashboard-tata-ruang

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\env\Scripts\activate
# atau (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
streamlit run app.py
```

Aplikasi akan terbuka di `http://localhost:8501`

## 📁 Project Structure

```
dashboard-tata-ruang/
├── app.py                      # Main application
├── requirements.txt            # Dependencies
├── credentials.json            # Google service account (JANGAN PUSH!)
├── drive_config.json          # Google Drive config
├── data_srs.kmz               # SRS shapefile
├── layers_metadata.json       # Layer metadata
├── .gitignore                 # Git ignore file
├── .streamlit/
│   └── config.toml            # Streamlit configuration
├── layers/                    # Custom layers directory
├── DEPLOYMENT_GUIDE.md        # Deployment & maintenance guide
└── README.md                  # This file
```

## 🔐 Configuration

### Google Credentials

1. Buat service account di [Google Cloud Console](https://console.cloud.google.com)
2. Download JSON key file
3. Rename menjadi `credentials.json`
4. Jangan commit ke GitHub (sudah di .gitignore)

### Environment Variables (untuk Production)

```bash
# Create .env file (local development only)
GOOGLE_CREDS_PATH=credentials.json
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=***
```

### Streamlit Cloud Secrets

Untuk deployment di Streamlit Cloud, tambahkan secrets di Settings:

```
GOOGLE_CREDS = {
  "type": "service_account",
  "project_id": "...",
  ...
}
```

## 📖 Usage

### Fitur Rekapitulasi
- Pilih tahun anggaran, OPD, dan fokus kegiatan
- Lihat distribusi pagu dan metrik utama
- Export data ke CSV

### Fitur Peta
- Klik SRS untuk highlight di peta
- Upload custom layer (KMZ/KML/SHP)
- Cari lokasi dengan "🔍 Cari lokasi"
- Switch antara Street dan Satelit basemap

### Fitur Data Lengkap
- Cari dan filter data
- Sesuaikan lebar kolom
- Export ke CSV

## 🔄 Development Workflow

### Membuat Fitur Baru

```bash
# 1. Create feature branch
git checkout -b feature/nama-fitur

# 2. Edit code di VS Code
# ... edit app.py ...

# 3. Test locally
streamlit run app.py

# 4. Commit changes
git add .
git commit -m "Feature: Deskripsi fitur"

# 5. Push to GitHub
git push origin feature/nama-fitur

# 6. Create Pull Request (optional)
```

### Merging ke Production

```bash
# Merge feature branch ke main
git checkout main
git merge feature/nama-fitur
git push origin main

# Streamlit Cloud akan auto-deploy
```

## 🐛 Troubleshooting

### Error: "ModuleNotFoundError"
```bash
pip install <module-name>
pip freeze > requirements.txt
git add requirements.txt && git commit -m "Update: Add new dependency"
git push
```

### Error: "Credentials not found"
- Pastikan `credentials.json` ada di root folder
- File ini harus di `.gitignore` (jangan push ke GitHub)
- Untuk Streamlit Cloud, upload via Settings > Secrets

### Aplikasi lambat
- Clear cache: `.streamlit/` folder
- Optimize data queries dengan caching
- Reduce data size (filter kolom yang tidak perlu)

## 📊 Data Schema

### Required Columns
- Tahun (Year column)
- OPD (Organization unit)
- Kegiatan (Activity name)
- Pagu Anggaran (Budget amount)
- SRS (Satuan Ruang Spasial)
- Pelayanan (Service type)

### Optional Columns
- Detail (Additional details)
- Fokus (Focus area)
- Jenis (Type)
- Daerah (Region)

## 🔐 Security Best Practices

1. **Never commit credentials**
   - Use `.gitignore` untuk credentials
   - Upload ke Streamlit Cloud secrets, bukan repository

2. **Use environment variables**
   - API keys dari `.env` atau `st.secrets`
   - Database passwords dari environment variables

3. **Database security**
   - Use strong passwords
   - Encrypt sensitive data
   - Regular backups

4. **Access control** (untuk production)
   - Implement authentication
   - Rate limiting
   - Audit logging

Lihat [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) untuk detail lengkap.

## 📦 Deployment

### Option 1: Streamlit Cloud (Recommended)
1. Push code ke GitHub
2. Daftar di [share.streamlit.io](https://share.streamlit.io)
3. Connect GitHub repository
4. Deploy in 1 click!

Lihat [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) untuk step-by-step.

### Option 2: VPS (DigitalOcean, Linode, AWS)
- Setup custom server
- Full control
- Manage own database & backups

Lihat [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) untuk setup instructions.

## 📞 Support & Resources

- **Streamlit Docs**: https://docs.streamlit.io
- **Streamlit Community**: https://discuss.streamlit.io
- **GitHub Issues**: Report bugs di repository
- **Documentation**: Lihat `DEPLOYMENT_GUIDE.md`

## 📝 License

[Specify your license - e.g., MIT, GPL, etc.]

## 👥 Contributors

- **Lead Developer**: [Your Name]
- **Domain Expert**: [Names]

## 📅 Version History

### v1.1 (May 3, 2026)
- ✨ Fix: Tombol "Lihat Semua Data Lengkap" sekarang berfungsi
- ✨ Feature: Tabel mini SRS menampilkan kolom tahun anggaran
- ✨ Feature: Tabel mini menampilkan semua data tanpa limit
- ✨ Feature: Input pencarian lokasi di peta interaktif

### v1.0 (Initial Release)
- 📊 Dashboard rekapitulasi
- 🗺️ Peta interaktif dengan SRS choropleth
- 📄 Data lengkap dengan filter
- 🎨 Upload custom layer

---

**Last Updated**: May 3, 2026  
**Status**: ✅ Production Ready

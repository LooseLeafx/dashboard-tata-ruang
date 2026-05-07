# 🌿 Dashboard Tata Ruang - Daerah Istimewa Yogyakarta

Aplikasi Streamlit untuk visualisasi dan analisis data kegiatan keistimewaan urusan tata ruang tahun 2020-2025 di Daerah Istimewa Yogyakarta.

## 📋 Fitur Utama

- **📊 Rekapitulasi Data**: Dashboard interaktif dengan metrik dan visualisasi
- **🗺️ Peta Interaktif**: Peta choropleth SRS dengan layer tambahan dan pencarian lokasi
- **📄 Data Lengkap**: Tabel data dengan filter dan pencarian
- **📁 Data Pendukung**: Manajemen data dan metadata
- **🎨 Upload Custom Layer**: Tambah layer KMZ/KML/SHP sendiri
- **🔍 Pencarian Lokasi**: Cari lokasi di peta dengan Nominatim API



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
# 🎨 Panduan Kustomisasi Halaman Login

Halaman login Anda sekarang memiliki styling profesional yang dapat dikustomisasi. Ikuti panduan berikut untuk mengubah warna, background, dan elemen lainnya.

---

## 1. 🎨 Mengubah Background Color

### Opsi A: Background Warna Solid
Di dalam fungsi `show_login_page()`, cari bagian CSS dan ubah gradient menjadi warna solid:

```css
/* DARI: */
background: linear-gradient(135deg, #0b3327 0%, #0f3d2e 50%, #1a5d3a 100%);

/* KE: */
background: #0b3327;  /* Ubah kode warna sesuai keinginan */
```

**Contoh warna:**
- `#0b3327` - Hijau gelap (warna default)
- `#1e40af` - Biru gelap
- `#7c3aed` - Ungu
- `#dc2626` - Merah
- `#ffffff` - Putih

---

## 2. 🌈 Mengubah Background Gradient

Ubah warna pada gradient untuk efek lebih menarik:

```css
background: linear-gradient(135deg, #COLOR1 0%, #COLOR2 50%, #COLOR3 100%);
```

**Contoh gradient bagus:**
- Hijau tua ke terang: `linear-gradient(135deg, #0b3327 0%, #27ae60 100%)`
- Biru modern: `linear-gradient(135deg, #1e40af 0%, #3b82f6 100%)`
- Ungu elegan: `linear-gradient(135deg, #6b21a8 0%, #a855f7 100%)`
- Orange energik: `linear-gradient(135deg, #d97706 0%, #f59e0b 100%)`

---

## 3. 🖼️ Mengubah Background Image

Jika ingin menambahkan gambar background:

```css
/* Uncomment bagian ini dan ubah URL */
background-image: url('https://www.transparenttextures.com/patterns/asfalt-light.png');
background-color: #0b3327;
background-size: auto;
background-attachment: fixed;
```

**Sumber gambar gratis:**
- Transparent Textures: https://www.transparenttextures.com
- Unsplash: https://unsplash.com
- Pexels: https://www.pexels.com

---

## 4. 🔘 Mengubah Warna Tombol Login

Cari bagian `.login-button` dan ubah warna gradient:

```css
/* DARI: */
background: linear-gradient(135deg, #27ae60 0%, #229954 100%) !important;

/* KE: */
background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%) !important;
```

---

## 5. ✏️ Mengubah Warna Input Fields

Ubah warna border saat fokus:

```css
/* Border color saat fokus (DARI): */
border-color: #27ae60 !important;

/* KE: */
border-color: #1e40af !important;
```

---

## 6. 📝 Mengubah Teks dan Ikon

Untuk mengubah teks di halaman login:

1. **Emoji/Icon Login:** `🔒` → ubah menjadi icon lain seperti `🏛️`, `🎯`, `📊`, dll
2. **Judul:** `Taru-Istimewa` → ubah nama aplikasi Anda
3. **Subtitle:** `Dashboard Tata Ruang DIY` → ubah deskripsi
4. **Placeholder:** `admin`, `password123` → ubah teks di input field

---

## 7. 🎭 Contoh Kustomisasi Lengkap

### Contoh 1: Tema Biru Modern
```css
.login-container {
    background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
}

.login-button {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%) !important;
}

.login-form input:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
}
```

### Contoh 2: Tema Ungu Elegan
```css
.login-container {
    background: linear-gradient(135deg, #6b21a8 0%, #a855f7 100%);
}

.login-button {
    background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%) !important;
}

.login-form input:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1) !important;
}
```

### Contoh 3: Tema Dark Mode
```css
.login-card {
    background: #1f2937;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.login-container {
    background: #111827;
}

.login-title {
    color: #f3f4f6;
}

.login-form input {
    background: #374151;
    color: #f3f4f6;
    border: 1.5px solid #4b5563 !important;
}
```

---

## 8. 🔧 Mengubah Ukuran & Spacing

**Font size:**
```css
.login-title {
    font-size: 1.6rem;  /* Ubah nilai */
}
```

**Padding card:**
```css
.login-card {
    padding: 48px 40px;  /* vertikal horizontal */
}
```

**Border radius (sudut melengkung):**
```css
.login-card {
    border-radius: 16px;  /* Lebih besar = sudut lebih bulat */
}

.login-button {
    border-radius: 8px;  /* Ubah sesuai keinginan */
}
```

---

## 9. 💡 Tips Umum

1. **Harmoni Warna:** Gunakan https://coolors.co untuk menemukan kombinasi warna yang bagus
2. **Opacity (Transparansi):** Ubah `rgba(39, 174, 96, 0.3)` menjadi `rgba(39, 174, 96, 0.5)` untuk lebih gelap
3. **Shadow Effect:** Ubah nilai di `box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3)` untuk mengubah efek bayangan
4. **Animation:** Ubah `animation: slideUp 0.5s` menjadi `0.3s` untuk animasi lebih cepat

---

## 10. 📱 Preview Perubahan

Setelah mengubah CSS:
1. Simpan file `app.py`
2. Refresh halaman browser (F5)
3. Lihat perubahan di halaman login

**Tips:** Jika perubahan tidak terlihat, coba `Ctrl+Shift+Delete` untuk clear cache browser.

---

**Selamat mendesain! 🎨**

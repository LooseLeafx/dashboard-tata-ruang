import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
import geopandas as gpd
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import fiona
import os
import json
import math
import base64
import time
import hashlib
import requests
from pathlib import Path

# ============================================================
# 0. FUNGSI HELPER - PERMANENT LAYER STORAGE (GOOGLE DRIVE)
# ============================================================
LAYERS_DIR = "layers"
LAYERS_METADATA_FILE = "layers_metadata.json"
DRIVE_FOLDER_ID = None
DRIVE_SERVICE = None

def setup_google_drive():
    """Setup Google Drive API untuk penyimpanan layer permanen"""
    global DRIVE_FOLDER_ID, DRIVE_SERVICE
    import sys
    try:
        # Load folder ID dari Streamlit Secrets
        DRIVE_FOLDER_ID = st.secrets["drive_config"]["folder_id"]
        print(f"[DRIVE] folder_id: {DRIVE_FOLDER_ID}", file=sys.stderr)

        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        sa_info = {k: v for k, v in st.secrets["gcp_service_account"].items()}
        pk = sa_info.get("private_key", "")
        if "\\n" in pk:
            pk = pk.replace("\\n", "\n")
        sa_info["private_key"] = pk

        print(f"[DRIVE] client_email: {sa_info.get('client_email')}", file=sys.stderr)

        creds = Credentials.from_service_account_info(
            sa_info,
            scopes=[
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/drive.file'
            ]
        )
        DRIVE_SERVICE = build('drive', 'v3', credentials=creds)
        # Test koneksi
        DRIVE_SERVICE.files().list(pageSize=1, fields="files(id)").execute()
        print(f"[DRIVE] setup SUCCESS", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[DRIVE] setup FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return False

def upload_layer_to_drive(filename, file_content):
    """Upload file KMZ ke Google Drive"""
    if not DRIVE_SERVICE or not DRIVE_FOLDER_ID:
        return None
    
    try:
        from googleapiclient.http import MediaFileUpload
        from io import BytesIO
        import tempfile
        
        # Tulis konten ke file sementara untuk di-upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.kmz') as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        
        # Upload ke Google Drive
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID],
            'mimeType': 'application/vnd.google-earth.kmz'
        }
        media = MediaFileUpload(tmp_path, mimetype='application/vnd.google-earth.kmz')
        file_result = DRIVE_SERVICE.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        os.remove(tmp_path)
        return file_result.get('id')
    except Exception as e:
        return None

def download_layer_from_drive(file_id):
    """Download file KMZ dari Google Drive"""
    if not DRIVE_SERVICE:
        return None
    
    try:
        from io import BytesIO
        
        request = DRIVE_SERVICE.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        return None

def delete_layer_from_drive(file_id):
    """Hapus file KMZ dari Google Drive"""
    if not DRIVE_SERVICE:
        return False
    
    try:
        DRIVE_SERVICE.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        return False

def init_layers_storage():
    """Inisialisasi penyimpanan layer (Google Drive atau lokal)"""
    global DRIVE_SERVICE, DRIVE_FOLDER_ID
    
    # Coba setup Google Drive
    drive_ok = setup_google_drive()
    
    if not drive_ok:
        # Fallback ke lokal
        if not os.path.exists(LAYERS_DIR):
            os.makedirs(LAYERS_DIR)
        if not os.path.exists(LAYERS_METADATA_FILE):
            with open(LAYERS_METADATA_FILE, "w") as f:
                json.dump([], f)

def load_layers_from_storage():
    """Load metadata semua layer dari storage (Google Drive atau lokal)"""
    if DRIVE_SERVICE and DRIVE_FOLDER_ID:
        # Load dari cache local jika ada (untuk performa)
        if os.path.exists(LAYERS_METADATA_FILE):
            try:
                with open(LAYERS_METADATA_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
    
    # Fallback ke lokal
    try:
        with open(LAYERS_METADATA_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_layers_to_storage(layers):
    """Simpan metadata semua layer ke storage"""
    # Simpan ke local cache
    with open(LAYERS_METADATA_FILE, "w") as f:
        json.dump(layers, f, indent=2)

def add_layer_to_storage(name, uploaded_file, color_config, file_type='kmz'):
    """Tambahkan layer baru ke penyimpanan permanen (KMZ, KML, atau SHP zip)"""
    init_layers_storage()
    layers = load_layers_from_storage()
    
    # Cek apakah layer dengan nama yang sama sudah ada
    existing_idx = next((i for i, l in enumerate(layers) if l['name'] == name), None)
    
    # Upload ke Google Drive jika tersedia, jika tidak simpan lokal
    file_content = uploaded_file.read()
    ext = file_type  # 'kmz', 'kml', atau 'shp'
    
    if DRIVE_SERVICE and DRIVE_FOLDER_ID:
        # Upload ke Google Drive
        file_id = upload_layer_to_drive(f"taru_layer_{name}.{ext}", file_content)
        if file_id:
            entry = {
                'name': name,
                'file_id': file_id,
                'drive_url': f'https://drive.google.com/file/d/{file_id}',
                'color_config': color_config,
                'visible': True,
                'type': file_type,
                'storage': 'drive',
                'created_at': time.time()
            }
        else:
            # Fallback ke lokal jika upload Drive gagal
            file_id = hashlib.md5(name.encode()).hexdigest()[:8]
            filename = f"{file_id}_{int(time.time())}.{ext}"
            filepath = os.path.join(LAYERS_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(file_content)
            entry = {
                'name': name,
                'filename': filename,
                'color_config': color_config,
                'visible': True,
                'type': file_type,
                'storage': 'local',
                'created_at': time.time()
            }
    else:
        # Simpan lokal
        file_id = hashlib.md5(name.encode()).hexdigest()[:8]
        filename = f"{file_id}_{int(time.time())}.{ext}"
        filepath = os.path.join(LAYERS_DIR, filename)
        os.makedirs(LAYERS_DIR, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(file_content)
        entry = {
            'name': name,
            'filename': filename,
            'color_config': color_config,
            'visible': True,
            'type': file_type,
            'storage': 'local',
            'created_at': time.time()
        }
    
    if existing_idx is not None:
        # Hapus file lama jika ada
        old_layer = layers[existing_idx]
        if old_layer.get('storage') == 'drive' and DRIVE_SERVICE:
            delete_layer_from_drive(old_layer.get('file_id'))
        elif old_layer.get('storage') == 'local':
            old_file = os.path.join(LAYERS_DIR, old_layer.get('filename', ''))
            if os.path.exists(old_file):
                os.remove(old_file)
        layers[existing_idx] = entry
    else:
        layers.append(entry)
    
    save_layers_to_storage(layers)
    return entry

def delete_layer_from_storage(name):
    """Hapus layer dari penyimpanan permanen"""
    layers = load_layers_from_storage()
    existing = [l for l in layers if l['name'] == name]
    
    if existing:
        layer = existing[0]
        if layer.get('storage') == 'drive' and DRIVE_SERVICE:
            delete_layer_from_drive(layer.get('file_id'))
        elif layer.get('storage') == 'local':
            filepath = os.path.join(LAYERS_DIR, layer.get('filename', ''))
            if os.path.exists(filepath):
                os.remove(filepath)
        
        layers = [l for l in layers if l['name'] != name]
        save_layers_to_storage(layers)
        return True
    return False

def get_layer_file_path(layer):
    """Dapatkan path file layer (lokal atau dari Drive)"""
    ltype = layer.get('type', 'kmz')
    ext = 'zip' if ltype == 'shp' else ltype
    
    if layer.get('storage') == 'drive' and DRIVE_SERVICE:
        file_content = download_layer_from_drive(layer.get('file_id'))
        if file_content:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
                tmp.write(file_content)
                return tmp.name
    else:
        filepath = os.path.join(LAYERS_DIR, layer.get('filename', ''))
        if os.path.exists(filepath):
            return filepath
    return None


def read_layer_geodataframe(layer_path, layer_type):
    """Baca file layer menjadi GeoDataFrame sesuai tipenya.
    Untuk KMZ/KML dari ArcMap, atribut sering tersimpan di dalam
    field 'description' sebagai tabel HTML — fungsi ini mem-parse-nya
    menjadi kolom terpisah.
    """
    import zipfile, tempfile, re
    ltype = layer_type or 'kmz'

    if ltype == 'shp':
        with zipfile.ZipFile(layer_path, 'r') as z:
            tmpdir = tempfile.mkdtemp()
            z.extractall(tmpdir)
            shp_files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
                         if f.lower().endswith('.shp')]
            if not shp_files:
                raise ValueError("File ZIP tidak mengandung .shp")
            gdf = gpd.read_file(shp_files[0])
            if gdf.crs and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
            return gdf
    else:
        fiona.drvsupport.supported_drivers['KML']    = 'rw'
        fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
        gdf = gpd.read_file(layer_path, driver='KML')

        # Cek apakah kolom 'description' ada dan kolom atribut asli tidak terbaca
        # (ArcMap menyimpan atribut sebagai tabel HTML di dalam description)
        if 'description' in gdf.columns:
            # Coba parse satu baris untuk deteksi apakah ada tabel HTML
            sample = str(gdf['description'].dropna().iloc[0]) if not gdf['description'].dropna().empty else ''
            has_table = '<table' in sample.lower() or '<td' in sample.lower()

            if has_table:
                # Parse semua baris
                parsed_rows = []
                for desc in gdf['description']:
                    row_dict = {}
                    desc_str = str(desc) if desc else ''
                    # Cari semua pasangan <td>key</td><td>value</td>
                    # Format ArcMap: <tr><td>FIELD</td><td>VALUE</td></tr>
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', desc_str,
                                     re.IGNORECASE | re.DOTALL)
                    # tds berupa list: [key1, val1, key2, val2, ...]
                    for i in range(0, len(tds) - 1, 2):
                        key = re.sub(r'<[^>]+>', '', tds[i]).strip()
                        val = re.sub(r'<[^>]+>', '', tds[i+1]).strip()
                        if key:
                            row_dict[key] = val
                    parsed_rows.append(row_dict)

                if parsed_rows and any(parsed_rows):
                    df_attrs = pd.DataFrame(parsed_rows)
                    # Gabungkan ke GeoDataFrame (drop description agar tidak dobel)
                    gdf = gdf.drop(columns=['description'], errors='ignore')
                    for col in df_attrs.columns:
                        if col not in gdf.columns:
                            gdf[col] = df_attrs[col].values

        return gdf

def geocode_location(query):
    """Geocode lokasi menggunakan Nominatim API (OpenStreetMap)"""
    try:
        # Prioritas pencarian: Indonesia
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': f"{query}, Indonesia",
            'format': 'json',
            'limit': 1
        }
        headers = {'User-Agent': 'TaruIstimewaApp/1.0'}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200 and response.json():
            result = response.json()[0]
            return {
                'lat': float(result['lat']),
                'lon': float(result['lon']),
                'name': result.get('display_name', query),
                'success': True
            }
        return {'success': False, 'error': 'Lokasi tidak ditemukan'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ============================================================
# 1. KONFIGURASI HALAMAN
# ============================================================
st.set_page_config(
    page_title="Taru-Istimewa",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 2. CSS GLOBAL
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Google+Sans:ital,opsz,wght@0,17..18,400..700;1,17..18,400..700&display=swap');

html, body, [class*="css"] {
    font-family: 'Google Sans', sans-serif !important;
}

.stApp { background-color: #eef2f0; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding: 1.4rem 2rem 2rem 2rem !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b3327 0%, #0f3d2e 100%) !important;
    min-width: 235px !important;
    max-width: 235px !important;
}
[data-testid="stSidebar"] > div:first-child {
    background: transparent !important;
    padding-top: 1rem !important;
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] .stExpander summary p {
    color: rgba(255,255,255,0.9) !important;
}
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div,
[data-testid="stSidebar"] .stTextInput input {
    background-color: white !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 7px !important;
    height: 36px !important;
    padding: 8px 12px !important;
    font-size: 0.9rem !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
[data-testid="stSidebar"] .stMultiSelect > div,
[data-testid="stSidebar"] .stSelectbox > div {
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .stMultiSelect,
[data-testid="stSidebar"] .stSelectbox,
[data-testid="stSidebar"] .stTextInput {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .stButton {
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
}
[data-testid="stSidebar"] .stButton > div {
    width: 100% !important;
    display: flex !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > div > button {
    background: rgba(255,255,255,0.15) !important;
    color: #fff !important;
    border: 1px solid rgba(255,255,255,0.3) !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    padding: 8px 12px !important;
    margin-top: 6px !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
    height: 36px !important;
    min-width: 200px !important;
    width: auto !important;
    box-sizing: border-box !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
}
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] .stButton > div > button:hover { 
    background: rgba(255,255,255,0.28) !important; 
}
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] {
    background-color: #27ae60 !important;
}
[data-testid="stSidebar"] .stExpander {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] ::-webkit-scrollbar { width: 3px; }
[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
    background: #27ae60; border-radius: 4px;
}

/* ── Metric Cards ── */
[data-testid="metric-container"] {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 20px 14px 20px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    border: 1px solid #dce8e2;
    border-left: 4px solid #27ae60;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 800 !important;
    color: #0b3327 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.07em !important;
    color: #6a9080 !important;
    text-transform: uppercase !important;
}

/* ── White Card ── */
.card {
    background: #ffffff;
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
    border: 1px solid #dce8e2;
    margin-bottom: 16px;
}
.card-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #0b3327;
    margin-bottom: 14px;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 4px;
    border-bottom: 2px solid #ddeadf !important;
}
[data-testid="stTabs"] button[role="tab"] {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: #6a9080 !important;
    padding: 8px 18px !important;
    border-radius: 8px 8px 0 0 !important;
    border: none !important;
    background: transparent !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #0b3327 !important;
    background: #ffffff !important;
    border-bottom: 2px solid #27ae60 !important;
}

/* ── Button apply ── */
.stButton > button {
    border: none !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    padding: 8px 12px !important;
    margin-top: 6px !important;
    display: block !important;
    background: #34495e !important;
    color: #fff !important;
    height: 36px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
.stButton > button:hover { background: #2c3e50 !important; }

/* ── Button pagination (next/prev) ── */
.page-nav .stButton > button {
    background: #7f8c8d !important;
    color: #fff !important;
    width: auto !important;
    padding: 6px 14px !important;
    height: 32px !important;
    font-size: 0.85rem !important;
}
.page-nav .stButton > button:hover { background: #6b7a7f !important; }
.page-nav .stButton > button:disabled {
    background: #bdc3c7 !important;
    cursor: not-allowed !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: #0b3327 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    padding: 8px 16px !important;
}

/* ── Progress bar ── */
.prog-wrap {
    background: #e8f5e9;
    border-radius: 5px;
    height: 7px;
    overflow: hidden;
    margin-top: 3px;
}
.prog-fill { height: 100%; border-radius: 5px; }

/* ── Pagination nav ── */
.page-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
    justify-content: flex-end;
}
.page-info {
    font-size: 0.7rem;
    color: #6a9080;
}

hr {
    border: none !important;
    border-top: 1px solid #ddeadf !important;
    margin: 10px 0 !important;
}
iframe { border-radius: 10px; }

/* ── Sidebar Toggle & Hidden State ── */
body.sidebar-hidden [data-testid="stSidebar"] {
    display: none !important;
}
body.sidebar-hidden .block-container {
    max-width: 100% !important;
    padding: 1.4rem 2rem 2rem 2rem !important;
}
body.sidebar-shown [data-testid="stSidebar"] {
    display: flex !important;
}

/* ── Donut legend scrollable container ── */
.legend-scroll {
    max-height: 240px;
    overflow-y: auto;
    padding-right: 4px;
}
.legend-scroll::-webkit-scrollbar { width: 3px; }
.legend-scroll::-webkit-scrollbar-thumb {
    background: #27ae60; border-radius: 4px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# 3. HELPERS
# ============================================================
COLORS = [
    "#27ae60", "#f39c12", "#e74c3c", "#3498db",
    "#9b59b6", "#1abc9c", "#e67e22", "#2ecc71",
    "#16a085", "#d35400", "#2980b9", "#8e44ad",
    "#c0392b", "#f1c40f", "#34495e", "#7f8c8d"
]
PAGE_SIZE = 5

# 19 kategori SRS yang valid (18 SRS + Non SRS)
SRS_KATEGORI = [
    "Non SRS",
    "SRS Karaton",
    "SRS Makam Raja-Raja Mataram di Imogiri",
    "SRS Masjid dan Makam Raja Mataram di Kotagede",
    "SRS Masjid Pathok Nagoro",
    "SRS Gunung Merapi",
    "SRS Pantai Samas Parangtritis",
    "SRS Kerto-Pleret",
    "SRS Kotabaru",
    "SRS Puro Pakualaman",
    "SRS Sumbu Filosofis",
    "SRS Perbukitan Menoreh",
    "SRS Karst Gunungsewu",
    "SRS Pantai Selatan Gunungkidul",
    "SRS Pusat Kota Wates",
    "SRS Pantai Selatan Kulon Progo",
    "SRS Candi Prambanan-Candi Ijo",
    "SRS Sokoliman",
    "SRS Makam Girigondo",
]


def fmt_rp_full(val):
    """Format lengkap: Rp 1.234.567.890"""
    try:
        return "Rp {:,}".format(int(float(val))).replace(",", ".")
    except Exception:
        return "Rp 0"


def bar_html(label, val, max_val, color, rank=None):
    """Render satu baris progress bar sebagai HTML string."""
    pct = (val / max_val * 100) if max_val > 0 else 0
    rp  = fmt_rp_full(val)
    lbl = str(label)[:52] + ("…" if len(str(label)) > 52 else "")
    badge = (
        f"<span style='font-size:0.6rem;font-weight:700;color:#fff;"
        f"background:{color};border-radius:4px;padding:1px 5px;"
        f"margin-right:6px;flex-shrink:0;'>{rank}</span>"
    ) if rank is not None else ""
    return f"""
<div style="margin-bottom:11px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
    <div style="display:flex;align-items:center;flex:1;min-width:0;">
      {badge}
      <span style="font-size:0.72rem;color:#1a3a2a;overflow:hidden;
            text-overflow:ellipsis;white-space:nowrap;">{lbl}</span>
    </div>
    <span style="font-size:0.7rem;font-weight:700;color:#0b3327;
          margin-left:8px;flex-shrink:0;">{rp}</span>
  </div>
  <div class="prog-wrap">
    <div class="prog-fill" style="width:{pct:.1f}%;background:{color};"></div>
  </div>
</div>"""


def render_paged(df_agg, col_name, color_offset=0, page_key="page"):
    """
    Tampilkan data agregasi dengan paginasi 5 item per halaman.
    df_agg: DataFrame dengan kolom [col_name, 'Pagu Anggaran']
    """
    total_rows = len(df_agg)
    total_pages = max(1, math.ceil(total_rows / PAGE_SIZE))

    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    page = st.session_state[page_key]
    page = min(page, total_pages - 1)
    st.session_state[page_key] = page

    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    df_page = df_agg.iloc[start:end]
    max_val = df_agg['Pagu Anggaran'].max() or 1

    for i, row in df_page.iterrows():
        rank  = start + list(df_page.index).index(i) + 1
        color = COLORS[(rank - 1 + color_offset) % len(COLORS)]
        st.markdown(
            bar_html(row[col_name], row['Pagu Anggaran'], max_val, color, rank=rank),
            unsafe_allow_html=True
        )

    # Fix 5 – Navigasi halaman: tombol ▶ selalu mepet ke kanan konten card
    # Gunakan container HTML murni agar tidak terpotong oleh kolom Streamlit
    prev_disabled = "disabled" if page == 0 else ""
    next_disabled = "disabled" if page >= total_pages - 1 else ""

    # Render navigasi via st.columns dengan rasio yang presisi
    spacer, nav_prev, nav_info, nav_next = st.columns([6, 1, 2, 1])
    with nav_prev:
        if st.button("◀", key=f"{page_key}_prev", disabled=(page == 0)):
            st.session_state[page_key] = page - 1
            st.rerun()
    with nav_info:
        st.markdown(
            f"<div style='text-align:center;font-size:0.7rem;color:#6a9080;"
            f"padding-top:6px;'>Hal {page+1} / {total_pages} "
            f"({total_rows} total)</div>",
            unsafe_allow_html=True
        )
    with nav_next:
        if st.button("▶", key=f"{page_key}_next", disabled=(page >= total_pages - 1)):
            st.session_state[page_key] = page + 1
            st.rerun()


def clean_currency(v):
    if not v or str(v).strip() in {'None', 'nan', '0', ''}:
        return 0
    s = str(v).replace('Rp', '').replace(' ', '').strip()
    if ',' in s:
        s = s.split(',')[0]
    s = s.replace('.', '')
    return pd.to_numeric(s, errors='coerce') or 0


def find_col(cols, *keywords):
    for kw in keywords:
        for c in cols:
            if kw.lower() in c.lower():
                return c
    return None


def kategorisasi_srs(nilai_srs):
    """
    Memetakan nilai SRS ke dalam 19 kategori resmi.
    Mengembalikan list kategori yang cocok (bisa lebih dari 1 jika multi-SRS).
    Strategi: exact match → normalized match → keyword match → as-is.
    """
    if not nilai_srs or str(nilai_srs).strip() in {'None', 'nan', ''}:
        return ["Non SRS"]

    items = [s.strip() for s in str(nilai_srs).split(',')]
    hasil = []

    for item in items:
        if not item:
            continue
        item_lower = item.lower()
        cocok = False

        # 1. Exact match (case-insensitive)
        for kat in SRS_KATEGORI:
            if kat.lower() == item_lower:
                if kat not in hasil:
                    hasil.append(kat)
                cocok = True
                break

        # 2. Item ada di dalam nama kategori atau sebaliknya
        if not cocok:
            for kat in SRS_KATEGORI:
                if item_lower in kat.lower() or kat.lower() in item_lower:
                    if kat not in hasil:
                        hasil.append(kat)
                    cocok = True
                    break

        # 3. Keyword matching — cek kata-kata penting dari nama kategori
        if not cocok:
            # Buat keyword list dari masing-masing kategori
            keyword_map = {
                "SRS Karaton":                                  ["karaton", "kraton", "keraton"],
                "SRS Makam Raja-Raja Mataram di Imogiri":       ["imogiri"],
                "SRS Masjid dan Makam Raja Mataram di Kotagede":["kotagede"],
                "SRS Masjid Pathok Nagoro":                     ["pathok", "nagoro"],
                "SRS Gunung Merapi":                            ["merapi"],
                "SRS Pantai Samas Parangtritis":                ["parangtritis", "samas"],
                "SRS Kerto-Pleret":                             ["kerto", "pleret"],
                "SRS Kotabaru":                                 ["kotabaru"],
                "SRS Puro Pakualaman":                          ["pakualaman", "puro"],
                "SRS Sumbu Filosofis":                          ["sumbu", "filosofis"],
                "SRS Perbukitan Menoreh":                       ["menoreh"],
                "SRS Karst Gunungsewu":                         ["gunungsewu", "karst"],
                "SRS Pantai Selatan Gunungkidul":               ["gunungkidul"],
                "SRS Pusat Kota Wates":                         ["wates"],
                "SRS Pantai Selatan Kulon Progo":               ["kulon progo", "kulonprogo"],
                "SRS Candi Prambanan-Candi Ijo":                ["prambanan", "candi ijo"],
                "SRS Sokoliman":                                ["sokoliman"],
                "SRS Makam Girigondo":                          ["girigondo"],
                "Non SRS":                                      ["non srs", "non-srs"],
            }
            for kat, keywords in keyword_map.items():
                if any(kw in item_lower for kw in keywords):
                    if kat not in hasil:
                        hasil.append(kat)
                    cocok = True
                    break

        # 4. Tidak cocok sama sekali – simpan apa adanya
        if not cocok and item not in hasil:
            hasil.append(item)

    return hasil if hasil else ["Non SRS"]


def buat_rekapitulasi_srs(df, C_SRS, C_PAGU, df_base=None):
    """
    Membuat rekapitulasi SRS dengan 19 kategori.
    df_base: jika diberikan, selalu tampilkan semua kategori dari df_base
             (digunakan agar SRS dengan pagu=0 tetap muncul saat difilter).
    Mengembalikan: (df_srs_rekap, total_pagu_asli, total_pagu_srs, pagu_double)
    """
    if not C_SRS:
        return pd.DataFrame(), 0, 0, 0

    total_pagu_asli = df[C_PAGU].sum()

    # Explode berdasarkan 19 kategori dari data yang difilter
    rows = []
    for _, row in df.iterrows():
        kategori_list = kategorisasi_srs(row[C_SRS])
        for kat in kategori_list:
            rows.append({
                'SRS': kat,
                'Pagu': row[C_PAGU],
                'Kegiatan': 1
            })

    if not rows:
        # Tetap kembalikan semua 19 kategori dengan nilai 0
        df_rekap = pd.DataFrame({
            'SRS': SRS_KATEGORI,
            'Jumlah_Kegiatan': 0,
            'Total_Pagu': 0.0
        })
        return df_rekap, total_pagu_asli, 0, 0

    df_exploded = pd.DataFrame(rows)
    df_rekap = df_exploded.groupby('SRS').agg(
        Jumlah_Kegiatan=('Kegiatan', 'sum'),
        Total_Pagu=('Pagu', 'sum')
    ).reset_index()

    # Pastikan semua 19 kategori selalu muncul (yang tidak ada → 0)
    df_all_kat = pd.DataFrame({'SRS': SRS_KATEGORI})
    df_rekap = df_all_kat.merge(df_rekap, on='SRS', how='left')
    df_rekap['Jumlah_Kegiatan'] = df_rekap['Jumlah_Kegiatan'].fillna(0).astype(int)
    df_rekap['Total_Pagu'] = df_rekap['Total_Pagu'].fillna(0)

    total_pagu_srs = df_rekap['Total_Pagu'].sum()
    pagu_double = total_pagu_srs - total_pagu_asli

    # Urutkan: yang ada nilai dulu, lalu 0
    df_rekap = df_rekap.sort_values('Total_Pagu', ascending=False)

    return df_rekap, total_pagu_asli, total_pagu_srs, pagu_double


# ============================================================
# 3A. SISTEM LOGIN
# ============================================================
def load_credentials():
    """Memuat kredensial dari Streamlit Secrets"""
    try:
        users = st.secrets["credentials"]["users"]
        return {"users": [dict(u) for u in users]}
    except Exception:
        st.error("Kredensial tidak ditemukan di Streamlit Secrets!")
        return None


def check_login(username, password, credentials):
    """Mengecek apakah username dan password benar"""
    if not credentials:
        return False
    
    for user in credentials.get("users", []):
        if user["username"] == username and user["password"] == password:
            return True
    return False


def get_logo_base64():
    """Convert logo.png to base64 data URI"""
    try:
        with open("logo.png", "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{logo_data}"
    except FileNotFoundError:
        # Jika file tidak ada, gunakan emoji sebagai fallback
        return None


def initialize_session_state():
    """Initialize session state dengan login timing"""
    # PENTING: Initialize sebelum apapun untuk ensure session persisten
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "username" not in st.session_state:
        st.session_state.username = None
    if "login_time" not in st.session_state:
        st.session_state.login_time = None
    if "last_activity_time" not in st.session_state:
        st.session_state.last_activity_time = None
    
    # Try to restore session from file if exists
    restore_session_from_file()
    
    # Debug: log initialization
    import sys
    print(f"[DEBUG] initialize_session_state() called: logged_in={st.session_state.logged_in}, username={st.session_state.username}", file=sys.stderr)


def get_session_file():
    """Get path to session file"""
    return Path(".streamlit_session.json")


def save_session_to_file():
    """Save current session to file untuk persist across refresh"""
    try:
        session_data = {
            "logged_in": st.session_state.logged_in,
            "username": st.session_state.username,
            "login_time": st.session_state.login_time,
            "last_activity_time": st.session_state.last_activity_time
        }
        with open(get_session_file(), "w") as f:
            json.dump(session_data, f)
        import sys
        print(f"[DEBUG] save_session_to_file() SUCCESS: {session_data}", file=sys.stderr)
    except Exception as e:
        import sys
        print(f"[DEBUG] save_session_to_file() ERROR: {e}", file=sys.stderr)


def restore_session_from_file():
    """Restore session from file jika ada"""
    try:
        session_file = get_session_file()
        if session_file.exists():
            with open(session_file, "r") as f:
                session_data = json.load(f)
            
            # Restore session hanya kalau timeout belum lewat
            if session_data.get("logged_in") and session_data.get("last_activity_time"):
                elapsed = time.time() - session_data["last_activity_time"]
                if elapsed < 3600:  # 1 hour
                    st.session_state.logged_in = session_data["logged_in"]
                    st.session_state.username = session_data["username"]
                    st.session_state.login_time = session_data["login_time"]
                    st.session_state.last_activity_time = session_data["last_activity_time"]
                    import sys
                    print(f"[DEBUG] restore_session_from_file() SUCCESS: username={session_data['username']}, elapsed={elapsed:.1f}s", file=sys.stderr)
                else:
                    # Timeout, hapus file
                    session_file.unlink()
                    import sys
                    print(f"[DEBUG] restore_session_from_file() TIMEOUT: {elapsed:.1f}s > 3600s", file=sys.stderr)
            else:
                session_file.unlink()
    except Exception as e:
        import sys
        print(f"[DEBUG] restore_session_from_file() ERROR: {e}", file=sys.stderr)


def update_activity():
    """Update last activity timestamp dan save ke file"""
    import sys
    st.session_state.last_activity_time = time.time()
    save_session_to_file()  # Simpan ke file setiap update activity
    print(f"[DEBUG] update_activity() called: last_activity_time={st.session_state.last_activity_time}", file=sys.stderr)


def check_session_timeout(timeout_seconds=3600):
    """
    Check if session has timed out (default: 1 hour = 3600 seconds)
    Jika timeout, force logout dan tampilkan pesan
    """
    import sys
    
    if not st.session_state.logged_in:
        print(f"[DEBUG] check_session_timeout: not logged in, returning False", file=sys.stderr)
        return False
    
    if st.session_state.last_activity_time is None:
        print(f"[DEBUG] check_session_timeout: last_activity_time is None, returning False", file=sys.stderr)
        return False
    
    current_time = time.time()
    elapsed_time = current_time - st.session_state.last_activity_time
    
    print(f"[DEBUG] check_session_timeout: elapsed={elapsed_time:.1f}s, timeout={timeout_seconds}s, will_timeout={elapsed_time > timeout_seconds}", file=sys.stderr)
    
    if elapsed_time > timeout_seconds:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.login_time = None
        st.session_state.last_activity_time = None
        print(f"[DEBUG] SESSION TIMEOUT TRIGGERED!", file=sys.stderr)
        return True  # Timeout terjadi
    
    return False  # Masih aktif


def show_login_page():
    """
    Menampilkan halaman login dengan styling yang dapat dikustomisasi.
    
    OPSI STYLING:
    1. Background color solid: ubah warna di 'background: #eef2f0;'
    2. Background gradient: ubah 'background: linear-gradient(...)'
    3. Background image: ubah 'background-image: url(...)'
    """
    
    # ─────────────────────────────────────────────────────────
    # CSS STYLING HALAMAN LOGIN (Dapat dikustomisasi)
    # ─────────────────────────────────────────────────────────
    login_css = """
    <style>
    /* Background halaman login */
    .login-container {
        background: linear-gradient(135deg, #0b3327 0%, #0f3d2e 50%, #1a5d3a 100%);
        /* Alternatif background warna solid:
           background: #0b3327;
        */
        /* Alternatif background image:
           background-image: url('https://www.transparenttextures.com/patterns/asfalt-light.png');
           background-color: #0b3327;
        */
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Google Sans', sans-serif;
    }
    
    /* Card form login */
    .login-card {
        background: white;
        border-radius: 16px;
        padding: 48px 40px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        max-width: 380px;
        width: 100%;
        animation: slideUp 0.5s ease-out;
    }
    
    /* Animasi masuk */
    @keyframes slideUp {
        from {
            opacity: 0;
            transform: translateY(40px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Header login */
    .login-header {
        text-align: center;
        margin-bottom: 32px;
    }
    
    .login-logo {
        font-size: 2.5rem;
        margin-bottom: 12px;
        display: block;
    }
    
    .login-title {
        font-size: 1.2rem;
        font-weight: 800;
        color: #0b3327;
        margin: 0;
        margin-bottom: 8px;
    }
    
    .login-subtitle {
        font-size: 0.85rem;
        color: #7a9a8a;
        margin: 0;
        margin-bottom: 4px;
    }
    
    .login-tagline {
        font-size: 0.75rem;
        color: #a0b8ac;
        margin: 0;
    }
    
    /* Input styling */
    .login-form input {
        width: 100%;
        padding: 12px 14px !important;
        margin-bottom: 16px;
        border: 1.5px solid #dce8e2 !important;
        border-radius: 8px !important;
        font-size: 0.9rem !important;
        transition: all 0.3s ease !important;
    }
    
    .login-form input:focus {
        border-color: #27ae60 !important;
        box-shadow: 0 0 0 3px rgba(39, 174, 96, 0.1) !important;
        outline: none !important;
    }
    
    .login-form input::placeholder {
        color: #a0b8ac !important;
    }
    
    /* Tombol login */
    .login-button {
        width: 100% !important;
        padding: 12px !important;
        margin-top: 8px !important;
        background: linear-gradient(135deg, #27ae60 0%, #229954 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(39, 174, 96, 0.3) !important;
    }
    
    .login-button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 25px rgba(39, 174, 96, 0.4) !important;
    }
    
    .login-button:active {
        transform: translateY(0) !important;
    }
    
    /* Footer */
    .login-footer {
        text-align: center;
        margin-top: 24px;
        font-size: 0.7rem;
        color: #a0b8ac;
    }
    
    /* Responsive */
    @media (max-width: 480px) {
        .login-card {
            padding: 32px 24px;
        }
        .login-title {
            font-size: 1.6rem;
        }
    }
    </style>
    """
    
    st.markdown(login_css, unsafe_allow_html=True)
    
    # ─────────────────────────────────────────────────────────
    # HTML HALAMAN LOGIN
    # ─────────────────────────────────────────────────────────
    logo_src = get_logo_base64()
    if logo_src:
        logo_html = f'<img src="{logo_src}" alt="Logo" class="login-logo">'
    else:
        logo_html = '<span class="login-logo">🌿</span>'
    
    st.markdown(f"""
    <div class="login-container">
        <div class="login-card">
            <div class="login-header">
                {logo_html}
                <h1 class="login-title">TARU-ISTIMEWA</h1>
                <p class="login-subtitle">Dashboard Urusan Keistimewaan Tata Ruang</p>
                <p class="login-tagline">Daerah Istimewa Yogyakarta</p>
            </div>
    """, unsafe_allow_html=True)
    
    # ─────────────────────────────────────────────────────────
    # INPUT FORM
    # ─────────────────────────────────────────────────────────
    st.markdown('<div class="login-form">', unsafe_allow_html=True)
    
    username = st.text_input(
        "Username",
        placeholder="Username",
        label_visibility="collapsed"
    )
    password = st.text_input(
        "Password",
        type="password",
        placeholder="Password",
        label_visibility="collapsed"
    )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ─────────────────────────────────────────────────────────
    # TOMBOL LOGIN
    # ─────────────────────────────────────────────────────────
    st.markdown('<div class="login-form">', unsafe_allow_html=True)
    
    if st.button("Login", use_container_width=True, key="login_btn"):
        credentials = load_credentials()
        
        if check_login(username, password, credentials):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.login_time = time.time()
            st.session_state.last_activity_time = time.time()
            save_session_to_file()  # Simpan session ke file
            import sys
            print(f"[DEBUG] LOGIN SUCCESSFUL: username={username}, login_time={st.session_state.login_time}", file=sys.stderr)
            st.success("✅ Login berhasil!")
            st.rerun()
        else:
            st.error("❌ Username atau password salah!")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # ─────────────────────────────────────────────────────────
    # FOOTER
    # ─────────────────────────────────────────────────────────
    st.markdown("""
            <div class="login-footer">
                © 2026 Bidang Tata Ruang · Paniradya Kaistimewan
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 4. LOAD DATA
# ============================================================
@st.cache_data(ttl=300, show_spinner="Memuat data dari Google Sheets…")
def load_data():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    sa_info = dict(st.secrets["gcp_service_account"])
    sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
    creds  = ServiceAccountCredentials.from_json_keyfile_dict(sa_info, scope)
    client = gspread.authorize(creds)
    url    = "https://docs.google.com/spreadsheets/d/1cmrPSupCKyj43RqXSWHfQY22gIo8RwX_Oj-uoF0Fdj0/edit#gid=0"
    sheet  = client.open_by_url(url).sheet1
    raw    = sheet.get_all_values()

    hi = 0
    for i, row in enumerate(raw):
        if any(k in row for k in ["Tahun", "OPD", "Pagu"]):
            hi = i
            break

    df = pd.DataFrame(raw[hi + 1:], columns=raw[hi])
    df = df.loc[:, df.columns != ''].replace('', None).dropna(how='all')
    df.columns = df.columns.str.strip()
    
    # ─────────────────────────────────────────────────────────
    # Bersihkan data string: hapus spasi depan/belakang + multiple spaces
    # ─────────────────────────────────────────────────────────
    for col in df.columns:
        if df[col].dtype == 'object':  # Kolom string/object
            # Hapus spasi depan/belakang, lalu normalisasi multiple spaces menjadi 1 space
            df[col] = df[col].str.strip().str.replace(r'\s+', ' ', regex=True)
    
    return df


# ============================================================
# 5. APLIKASI UTAMA
# ============================================================
try:
    # ─────────────────────────────────────────────────────────
    # Initialize login state dengan session timeout tracking
    # ─────────────────────────────────────────────────────────
    initialize_session_state()
    
    # Update activity timestamp setiap kali page di-render (SEBELUM timeout check)
    if st.session_state.logged_in and st.session_state.last_activity_time is not None:
        update_activity()
    
    # Check if session has timed out (setelah activity update)
    if check_session_timeout(timeout_seconds=3600):  # 1 hour = 3600 seconds
        st.warning("⏰ Sesi Anda telah berakhir karena tidak ada aktivitas selama 1 jam. Silakan login kembali.")
        st.rerun()
    
    # Jika belum login, tampilkan halaman login
    if not st.session_state.logged_in:
        show_login_page()
        st.stop()
    
    # ─────────────────────────────────────────────────────────
    # Initialize sidebar visibility state
    # ─────────────────────────────────────────────────────────
    if "sidebar_hidden" not in st.session_state:
        st.session_state.sidebar_hidden = False
    
    sidebar_state = "sidebar-hidden" if st.session_state.sidebar_hidden else "sidebar-shown"

    # Fix 1 – Sidebar hidden: tampilan benar-benar full width tanpa sisa putih
    if st.session_state.sidebar_hidden:
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] { display: none !important; width: 0 !important; }
            section[data-testid="stSidebarUserContent"] { display: none !important; }
            .stAppViewContainer > .main { margin-left: 0 !important; }
            .block-container { 
                max-width: 100% !important; 
                margin-left: 0 !important;
                margin-right: 0 !important;
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }
            /* Hapus offset bawaan Streamlit saat sidebar terbuka */
            .stApp [data-testid="stAppViewContainer"] {
                padding-left: 0 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(f"""
    <script>
    document.body.classList.remove('sidebar-hidden', 'sidebar-shown');
    document.body.classList.add('{sidebar_state}');

    setTimeout(() => {{
        const sidebarButtons = document.querySelectorAll('[data-testid="stSidebar"] button');
        sidebarButtons.forEach(btn => {{
            const text = (btn.textContent || '').trim();
            if (text === '✖') {{
                btn.style.position = 'absolute';
                btn.style.top = '8px';
                btn.style.right = '8px';
                btn.style.width = '36px';
                btn.style.height = '36px';
                btn.style.padding = '0';
                btn.style.borderRadius = '50%';
                btn.style.background = '#0b3327';
                btn.style.color = '#fff';
                btn.style.fontSize = '1.1rem';
                btn.style.display = 'flex';
                btn.style.alignItems = 'center';
                btn.style.justifyContent = 'center';
                btn.style.border = 'none';
                btn.style.cursor = 'pointer';
            }}
        }});

        const allButtons = document.querySelectorAll('button');
        allButtons.forEach(btn => {{
            const t = (btn.textContent || '').trim();
            if (t === '≡') {{
                btn.style.position = 'fixed';
                btn.style.left = '20px';
                btn.style.bottom = '30px';
                btn.style.zIndex = '9999';
                btn.style.width = '50px';
                btn.style.height = '50px';
                btn.style.borderRadius = '50%';
                btn.style.background = '#0b3327';
                btn.style.color = '#fff';
                btn.style.fontSize = '1.5rem';
                btn.style.display = 'flex';
                btn.style.alignItems = 'center';
                btn.style.justifyContent = 'center';
                btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
                btn.style.border = 'none';
                btn.style.cursor = 'pointer';
                btn.style.transition = 'all 0.3s ease';
                btn.onmouseover = () => {{
                    btn.style.background = '#0f4535';
                    btn.style.transform = 'scale(1.1)';
                }};
                btn.onmouseout = () => {{
                    btn.style.background = '#0b3327';
                    btn.style.transform = 'scale(1)';
                }};
            }}
        }});
    }}, 120);
    </script>
    """, unsafe_allow_html=True)
    
    # Floating toggle button when sidebar is hidden
    if st.session_state.sidebar_hidden:
        col_float = st.columns([1, 10, 1])[0]
        with col_float:
            if st.button("≡", key="btn_toggle_sidebar_float", help="Buka panel filter"):
                st.session_state.sidebar_hidden = False
                st.rerun()
    
    df_raw = load_data()
    df_raw['Pagu Anggaran'] = df_raw['Pagu Anggaran'].apply(clean_currency).fillna(0)
    COLS = df_raw.columns.tolist()

    C_TAHUN   = find_col(COLS, 'tahun')
    C_OPD     = find_col(COLS, 'opd')
    C_DAERAH  = find_col(COLS, 'daerah', 'pemda', 'pemerintah')
    C_PAGU    = 'Pagu Anggaran'
    C_PELAYAN = find_col(COLS, 'pelayan')
    C_FOKUS   = find_col(COLS, 'fokus')
    C_DETAIL  = find_col(COLS, 'detail')
    C_JENIS   = find_col(COLS, 'jenis')
    C_SRS     = find_col(COLS, 'satuan', 'srs')

    # ─────────────────────────────────────────────────────────
    # SESSION STATE – Layer Peta Tambahan
    # ─────────────────────────────────────────────────────────
    if "extra_layers" not in st.session_state:
        # Load layers dari storage (Google Drive atau lokal)
        init_layers_storage()
        st.session_state.extra_layers = load_layers_from_storage()
    if "selected_srs_map" not in st.session_state:
        st.session_state.selected_srs_map = None

    # ─────────────────────────────────────────────────────────
    # SIDEBAR
    # ─────────────────────────────────────────────────────────
    with st.sidebar:
        st.image("logo.png", width=44)
        st.markdown(
            "<div style='margin-top:4px;margin-bottom:2px;"
            "font-size:1rem;font-weight:800;color:#fff;'>Taru-Istimewa</div>"
            "<div style='font-size:0.6rem;color:rgba(255,255,255,0.4);'>"
            "Data Urusan Keistimewaa Tata Ruang </div>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<hr style='border-color:rgba(255,255,255,0.12);margin:10px 0;'>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='font-size:0.58rem;color:rgba(255,255,255,0.35);"
            "letter-spacing:0.1em;margin:0 0 8px 0;'>FILTER DATA</p>",
            unsafe_allow_html=True
        )

        sel_tahun = (
            st.multiselect("📅 Tahun Anggaran",
                           sorted(df_raw[C_TAHUN].dropna().unique()),
                           placeholder="Semua tahun")
            if C_TAHUN else []
        )
        sel_daerah = (
            st.multiselect("🏙️ Pemerintah Daerah",
                           sorted(df_raw[C_DAERAH].dropna().unique()),
                           placeholder="Semua daerah")
            if C_DAERAH else []
        )
        
        # ─────────────────────────────────────────────────────────
        # FILTER BERTINGKAT: OPD berdasarkan Pemerintah Daerah
        # ─────────────────────────────────────────────────────────
        if C_OPD:
            # Jika ada pemilihan daerah, filter OPD berdasarkan daerah
            if sel_daerah:
                df_opd_filtered = df_raw[df_raw[C_DAERAH].isin(sel_daerah)]
                opd_options = sorted(df_opd_filtered[C_OPD].dropna().unique())
            else:
                # Jika tidak ada pemilihan daerah, tampilkan semua OPD
                opd_options = sorted(df_raw[C_OPD].dropna().unique())
            
            sel_opd = st.multiselect(
                "🏢 OPD",
                opd_options,
                placeholder="Semua OPD"
            )
        else:
            sel_opd = []

        with st.expander("⚙️Filter Lanjutan"):
            # ─────────────────────────────────────────────────────────
            # FILTER BERTINGKAT: Pelayanan → Fokus → Detail
            # ─────────────────────────────────────────────────────────
            sel_pelayan = (
                st.multiselect("🎯 Pelayanan",
                               sorted(df_raw[C_PELAYAN].dropna().unique()),
                               placeholder="Semua")
                if C_PELAYAN else []
            )
            
            # Filter Fokus berdasarkan Pelayanan
            if C_FOKUS:
                if sel_pelayan:
                    df_fokus_filtered = df_raw[df_raw[C_PELAYAN].isin(sel_pelayan)]
                    fokus_options = sorted(df_fokus_filtered[C_FOKUS].dropna().unique())
                else:
                    fokus_options = sorted(df_raw[C_FOKUS].dropna().unique())
                
                sel_fokus = st.multiselect(
                    "📍 Fokus",
                    fokus_options,
                    placeholder="Semua"
                )
            else:
                sel_fokus = []
            
            # Filter Detail berdasarkan Fokus
            if C_DETAIL:
                if sel_fokus:
                    # Filter berdasarkan Fokus yang dipilih (dan Pelayanan jika ada)
                    df_detail_filtered = df_raw[df_raw[C_FOKUS].isin(sel_fokus)]
                    detail_options = sorted(df_detail_filtered[C_DETAIL].dropna().unique())
                else:
                    # Jika tidak ada Fokus dipilih, gunakan data dari Pelayanan (jika ada)
                    if sel_pelayan:
                        df_detail_filtered = df_raw[df_raw[C_PELAYAN].isin(sel_pelayan)]
                    else:
                        df_detail_filtered = df_raw
                    detail_options = sorted(df_detail_filtered[C_DETAIL].dropna().unique())
                
                sel_detail = st.multiselect(
                    "📌 Detail",
                    detail_options,
                    placeholder="Semua"
                )
            else:
                sel_detail = []
            
            sel_jenis = (
                st.multiselect("🔖 Jenis Kegiatan",
                               sorted(df_raw[C_JENIS].dropna().unique()),
                               placeholder="Semua")
                if C_JENIS else []
            )
            sel_srs = (
                st.multiselect("🗺️ Satuan Ruang Strategis",
                               sorted(df_raw[C_SRS].dropna().unique()),
                               placeholder="Semua")
                if C_SRS else []
            )

        btn_apply = st.button("Filter")

        st.markdown(
            "<hr style='border-color:rgba(255,255,255,0.1);margin:14px 0 12px 0;'>",
            unsafe_allow_html=True
        )
        
        # ─────────────────────────────────────────────────────────
        # USER INFO & LOGOUT
        # ─────────────────────────────────────────────────────────
        st.markdown(
            f"<div style='font-size:0.7rem;color:rgba(255,255,255,0.6);margin-bottom:8px;'>"
            f"👤 Pengguna: <b>{st.session_state.username}</b></div>",
            unsafe_allow_html=True
        )
        
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.login_time = None
            st.session_state.last_activity_time = None
            # Hapus session file
            try:
                get_session_file().unlink(missing_ok=True)
            except:
                pass
            st.success("Logout berhasil! Silakan refresh halaman.")
            st.rerun()

        st.markdown(
            "<hr style='border-color:rgba(255,255,255,0.1);margin:8px 0 8px 0;'>",
            unsafe_allow_html=True
        )
        
        # ─────────────────────────────────────────────────────────
        # DEBUG INFO
        # ─────────────────────────────────────────────────────────
        with st.expander("🔍 Debug Info"):
            current_time = time.time()
            last_activity = st.session_state.last_activity_time
            elapsed_seconds = current_time - last_activity if last_activity else 0
            
            st.write(f"**Logged in:** {st.session_state.logged_in}")
            st.write(f"**Username:** {st.session_state.username}")
            st.write(f"**Login time:** {st.session_state.login_time}")
            st.write(f"**Last activity:** {last_activity}")
            st.write(f"**Current time:** {current_time}")
            st.write(f"**Elapsed (s):** {elapsed_seconds:.1f}")
            st.write(f"**Timeout limit (s):** 3600 (1 hour)")
            st.write(f"**Will timeout:** {elapsed_seconds > 3600}")

        st.markdown(
            "<hr style='border-color:rgba(255,255,255,0.1);margin:8px 0 8px 0;'>",
            unsafe_allow_html=True
        )

        st.markdown(
            "<p style='font-size:0.56rem;color:rgba(255,255,255,0.22);"
            "text-align:center;margin-top:12px;'>© 2026 Bidang Tata Ruang · Paniradya Kaistimewan</p>",
            unsafe_allow_html=True
        )

    # ─────────────────────────────────────────────────────────
    # SESSION STATE
    # ─────────────────────────────────────────────────────────
    if "df_active" not in st.session_state:
        st.session_state.df_active = df_raw.copy()

    if btn_apply:
        df_f = df_raw.copy()
        if sel_tahun   and C_TAHUN:   df_f = df_f[df_f[C_TAHUN].isin(sel_tahun)]
        if sel_daerah  and C_DAERAH:  df_f = df_f[df_f[C_DAERAH].isin(sel_daerah)]
        if sel_opd     and C_OPD:     df_f = df_f[df_f[C_OPD].isin(sel_opd)]
        if sel_pelayan and C_PELAYAN: df_f = df_f[df_f[C_PELAYAN].isin(sel_pelayan)]
        if sel_fokus   and C_FOKUS:   df_f = df_f[df_f[C_FOKUS].isin(sel_fokus)]
        if sel_detail  and C_DETAIL:  df_f = df_f[df_f[C_DETAIL].isin(sel_detail)]
        if sel_jenis   and C_JENIS:   df_f = df_f[df_f[C_JENIS].isin(sel_jenis)]
        if sel_srs     and C_SRS:     df_f = df_f[df_f[C_SRS].isin(sel_srs)]
        st.session_state.df_active = df_f
        for key in list(st.session_state.keys()):
            if key.endswith("_page"):
                st.session_state[key] = 0

    df = st.session_state.df_active

    # ─────────────────────────────────────────────────────────
    # PAGE HEADER
    # ─────────────────────────────────────────────────────────
    st.markdown("""
<div style="margin-bottom:18px;">
  <div style="font-size:1.45rem;font-weight:800;color:#0b3327;">Dashboard</div>
  <div style="font-size:0.77rem;color:#7a9a8a;margin-top:2px;">
    Analisis Data Kegiatan Keistimewaan Urusan Tata Ruang Tahun 2020 - 2025
  </div>
</div>""", unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────
    # METRIK ROW
    # ─────────────────────────────────────────────────────────
    total_pagu     = df[C_PAGU].sum()
    total_kegiatan = len(df)
    total_opd      = df[C_OPD].nunique() if C_OPD else "–"

    m1, m2, m3 = st.columns(3)
    m1.metric("TOTAL KEGIATAN",      f"{total_kegiatan:,}")
    m2.metric("TOTAL PAGU ANGGARAN", fmt_rp_full(total_pagu))
    m3.metric("JUMLAH OPD",          str(total_opd))

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # ─────────────────────────────────────────────────────────
    # TABS
    # ─────────────────────────────────────────────────────────
    _active_tab = st.session_state.pop("active_tab", 0)
    tab_rekap, tab_peta, tab_data, tab_pendukung = st.tabs([
        "📊  Rekapitulasi",
        "🗺️  Peta Interaktif",
        "📄  Data Lengkap",
        "📁  Data Pendukung",
    ])

    # ══════════════════════════════════════════════════════════
    # TAB 1 · REKAPITULASI
    # ══════════════════════════════════════════════════════════
    with tab_rekap:

        # ── B.3 Baris 1: Donut Pelayanan (berdiri sendiri, full width) ──
        donut_by = C_PELAYAN or C_FOKUS or C_OPD
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='card-title'>Distribusi Pagu · {donut_by or '–'}</div>",
            unsafe_allow_html=True
        )
        if donut_by:
            dn = (
                df.groupby(donut_by)[C_PAGU].sum()
                .reset_index()
                .query(f"`{C_PAGU}` > 0")
                .sort_values(C_PAGU, ascending=False)
            )
            total_dn = dn[C_PAGU].sum()

            # B.2 – Donut sejajar dengan keterangan (scrollable legend)
            col_donut_chart, col_donut_legend = st.columns([1, 1])

            with col_donut_chart:
                fig_donut = go.Figure(data=[go.Pie(
                    labels=dn[donut_by],
                    values=dn[C_PAGU],
                    hole=0.62,
                    marker=dict(colors=COLORS[:len(dn)]),
                    textinfo='none',
                    hovertemplate="<b>%{label}</b><br>%{customdata}<br>%{percent}<extra></extra>",
                    customdata=[fmt_rp_full(v) for v in dn[C_PAGU]],
                )])
                fig_donut.update_layout(
                    showlegend=False,
                    height=280,
                    margin=dict(t=5, b=5, l=5, r=5),
                    paper_bgcolor='rgba(0,0,0,0)',
                    annotations=[dict(
                        text=f"<b>{fmt_rp_full(total_dn)}</b>",
                        x=0.5, y=0.5,
                        font=dict(size=11, color="#0b3327"),
                        showarrow=False
                    )]
                )
                st.plotly_chart(fig_donut, use_container_width=True,
                                config={'displayModeBar': False})

            with col_donut_legend:
                # B.2 – Keterangan bisa discroll, tinggi menyesuaikan diagram
                legend_items = ""
                for idx, row in dn.iterrows():
                    pos   = list(dn.index).index(idx)
                    color = COLORS[pos % len(COLORS)]
                    pct   = row[C_PAGU] / total_dn * 100 if total_dn else 0
                    lbl   = str(row[donut_by])[:48]
                    legend_items += f"""
<div style="display:flex;justify-content:space-between;align-items:center;
     padding:5px 0;border-bottom:1px solid #f0f4f2;">
  <div style="display:flex;align-items:center;gap:7px;flex:1;min-width:0;">
    <div style="width:9px;height:9px;border-radius:50%;background:{color};flex-shrink:0;"></div>
    <span style="font-size:0.71rem;color:#1a3a2a;overflow:hidden;
          text-overflow:ellipsis;white-space:nowrap;">{lbl}</span>
  </div>
  <div style="text-align:right;flex-shrink:0;margin-left:8px;">
    <div style="font-size:0.7rem;font-weight:700;color:#0b3327;">
      {fmt_rp_full(row[C_PAGU])}</div>
    <div style="font-size:0.62rem;color:#7a9a8a;">{pct:.1f}%</div>
  </div>
</div>"""
                st.markdown(
                    f"<div style='margin-top:12px;'>"
                    f"<div class='legend-scroll' style='max-height:260px;overflow-y:auto;"
                    f"padding-right:6px;border:1px solid #eef2f0;border-radius:8px;padding:8px;'>"
                    f"{legend_items}</div></div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("Kolom Pelayanan/Fokus tidak terdeteksi.")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── B.3 Baris 2: Pagu per OPD (kiri) + Pagu per Jenis Kegiatan (kanan) ──
        col_opd, col_jenis = st.columns(2)

        with col_opd:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Pagu per OPD Pengampu</div>",
                        unsafe_allow_html=True)
            if C_OPD:
                opd_agg = (
                    df.groupby(C_OPD)[C_PAGU].sum()
                    .sort_values(ascending=False)
                    .reset_index()
                    .rename(columns={C_OPD: 'label'})
                )
                opd_agg.columns = [C_OPD, 'Pagu Anggaran']
                render_paged(opd_agg, C_OPD,
                             color_offset=0, page_key="opd_page")
            else:
                st.info("Kolom OPD tidak terdeteksi.")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_jenis:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Pagu per Jenis Tahapan</div>",
                        unsafe_allow_html=True)
            if C_JENIS:
                jn_agg = (
                    df.groupby(C_JENIS)[C_PAGU].sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                render_paged(jn_agg, C_JENIS,
                             color_offset=3, page_key="jenis_page")
            else:
                st.info("Kolom Jenis Kegiatan tidak terdeteksi.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── B.3 Baris 3: Pagu per Fokus (kiri) + Pagu per SRS (kanan) ──
        col_fokus, col_srs = st.columns(2)

        with col_fokus:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Pagu per Fokus</div>",
                        unsafe_allow_html=True)
            if C_FOKUS:
                fk_agg = (
                    df.groupby(C_FOKUS)[C_PAGU].sum()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                render_paged(fk_agg, C_FOKUS,
                             color_offset=6, page_key="fokus_page")
            else:
                st.info("Kolom Fokus tidak terdeteksi.")
            st.markdown("</div>", unsafe_allow_html=True)

        # A.3 + B.3 – Pagu per SRS (19 kategori, sejajar dengan Fokus)
        with col_srs:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Pagu per Satuan Ruang Strategis</div>",
                        unsafe_allow_html=True)
            if C_SRS:
                df_srs_rekap, total_pagu_asli, total_pagu_srs, pagu_double = \
                    buat_rekapitulasi_srs(df, C_SRS, C_PAGU)

                if pagu_double > 0:
                    st.markdown(
                        f"<div style='background:#fff8e1;border:1px solid #f39c12;"
                        f"border-radius:8px;padding:8px 12px;margin-bottom:10px;"
                        f"font-size:0.72rem;color:#7d5a00;'>"
                        f"ℹ️ <b>Catatan:</b> Total pagu SRS ({fmt_rp_full(total_pagu_srs)}) "
                        f"berbeda dari total keseluruhan ({fmt_rp_full(total_pagu_asli)}) "
                        f"karena terdapat <b>{fmt_rp_full(pagu_double)}</b> pagu dari kegiatan "
                        f"yang tercatat di lebih dari satu SRS (multi-SRS).</div>",
                        unsafe_allow_html=True
                    )

                if not df_srs_rekap.empty:
                    srs_agg = df_srs_rekap.rename(
                        columns={'SRS': C_SRS, 'Total_Pagu': 'Pagu Anggaran'}
                    )
                    render_paged(srs_agg, C_SRS,
                                 color_offset=9, page_key="srs_page")
                else:
                    st.info("Data SRS tidak tersedia.")
            else:
                st.info("Kolom SRS tidak terdeteksi.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Tren Tahunan ──
        if C_TAHUN:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Tren Pagu Anggaran per Tahun</div>",
                        unsafe_allow_html=True)
            yr = (
                df.groupby(C_TAHUN)[C_PAGU].sum()
                .reset_index()
                .sort_values(C_TAHUN)
            )
            fig_bar = go.Figure(go.Bar(
                x=yr[C_TAHUN],
                y=yr[C_PAGU],
                marker_color=COLORS[0],
                text=[fmt_rp_full(v) for v in yr[C_PAGU]],
                textposition='outside',
                hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
                customdata=[fmt_rp_full(v) for v in yr[C_PAGU]],
            ))
            fig_bar.update_layout(
                height=220,
                margin=dict(t=30, b=10, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, tickfont=dict(size=11)),
                yaxis=dict(showgrid=True, gridcolor='#eef2f0',
                           showticklabels=False),
                uniformtext_minsize=8,
                uniformtext_mode='hide'
            )
            st.plotly_chart(fig_bar, use_container_width=True,
                            config={'displayModeBar': False})
            st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    # TAB 2 · PETA SRS
    # ══════════════════════════════════════════════════════════
    with tab_peta:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='card-title'>🗺️ Peta Interaktif · Sebaran Kegiatan & Layer Tambahan</div>",
            unsafe_allow_html=True
        )

        # ── Manajemen Layer Tambahan ──────────────────────────
        PALETTES = {
            "Hijau Alam":   ["#1a9850","#66bd63","#a6d96a","#d9ef8b","#ffffbf"],
            "Biru Laut":    ["#2166ac","#4393c3","#92c5de","#d1e5f0","#f7f7f7"],
            "Oranye Panas": ["#d73027","#f46d43","#fdae61","#fee090","#ffffbf"],
            "Ungu Elegan":  ["#762a83","#9970ab","#c2a5cf","#e7d4e8","#f7f7f7"],
            "Kategorikal":  ["#e41a1c","#377eb8","#4daf4a","#984ea3","#ff7f00","#a65628","#f781bf"],
            "Netral Abu":   ["#252525","#525252","#737373","#969696","#bdbdbd"],
        }

        with st.expander("🗂️ Upload Peta", expanded=False):
            st.markdown(
                "<p style='font-size:0.78rem;color:#555;margin-bottom:10px;'>"
                "Upload file KMZ/KML/SHP. Pilih warna seragam atau warna per-kategori "
                "berdasarkan field <b>Name</b> pada file.</p>",
                unsafe_allow_html=True
            )

            up_col1, up_col2, up_col3 = st.columns([3, 1, 1])
            with up_col1:
                layer_name_input = st.text_input(
                    "Nama Layer",
                    placeholder="contoh: Jalan, Batas Kalurahan, dll",
                    key="new_layer_name",
                    label_visibility="collapsed"
                )
            with up_col2:
                color_mode = st.selectbox(
                    "Mode Warna",
                    ["Warna Seragam", "Warna per Kategori"],
                    key="new_layer_color_mode",
                    label_visibility="collapsed"
                )
            with up_col3:
                uploaded_layer = st.file_uploader(
                    "Upload KMZ/KML/SHP", type=["kmz", "kml", "zip"],
                    key="layer_uploader",
                    label_visibility="collapsed"
                )
            st.markdown(
                "<p style='font-size:0.68rem;color:#aaa;margin:-4px 0 6px 0;'>"                "💡 Format: <b>KMZ</b>, <b>KML</b>, atau <b>SHP</b> (dikemas dalam <b>ZIP</b> "                "bersama file .dbf, .shx, dll)</p>",
                unsafe_allow_html=True
            )

            if color_mode == "Warna Seragam":
                cc1, cc2 = st.columns([1, 4])
                with cc1:
                    layer_color_single = st.color_picker(
                        "Warna", "#e74c3c", key="new_layer_color_single",
                        label_visibility="collapsed"
                    )
                with cc2:
                    st.markdown(
                        "<p style='font-size:0.72rem;color:#888;padding-top:6px;'>"
                        "Semua polygon menggunakan satu warna.</p>",
                        unsafe_allow_html=True
                    )
                layer_color_config = {"mode": "single", "color": layer_color_single}
            else:
                st.markdown(
                    "<p style='font-size:0.72rem;font-weight:600;color:#0b3327;"
                    "margin:8px 0 6px 0;'>Pilih Palet Warna Rekomendasi:</p>",
                    unsafe_allow_html=True
                )
                pal_cols = st.columns(len(PALETTES))
                for pi, (pname, pcolors) in enumerate(PALETTES.items()):
                    with pal_cols[pi]:
                        swatches_html = "".join(
                            "<div style='width:12px;height:12px;background:" + c +
                            ";border-radius:2px;display:inline-block;margin:1px;'></div>"
                            for c in pcolors[:5]
                        )
                        st.markdown(
                            "<div style='text-align:center;'>" + swatches_html + "</div>",
                            unsafe_allow_html=True
                        )
                        if st.button(pname, key="pal_btn_" + str(pi),
                                     use_container_width=True):
                            st.session_state["active_palette"] = pname
                            st.rerun()

                active_pal = st.session_state.get(
                    "active_palette", list(PALETTES.keys())[0])
                st.markdown(
                    "<p style='font-size:0.72rem;color:#27ae60;margin:6px 0;'>"
                    "✅ Palet aktif: <b>" + active_pal + "</b></p>",
                    unsafe_allow_html=True
                )
                layer_color_config = {"mode": "palette", "palette": active_pal}

            if st.button("➕ Tambah Layer", key="btn_add_layer"):
                if uploaded_layer and layer_name_input.strip():
                    # Deteksi tipe file
                    fname_lower = uploaded_layer.name.lower()
                    if fname_lower.endswith('.zip'):
                        detected_type = 'shp'
                    elif fname_lower.endswith('.kml'):
                        detected_type = 'kml'
                    else:
                        detected_type = 'kmz'
                    # Simpan layer ke penyimpanan permanen (Google Drive atau lokal)
                    entry = add_layer_to_storage(
                        layer_name_input.strip(),
                        uploaded_layer,
                        layer_color_config,
                        file_type=detected_type
                    )
                    # Update session state dari storage
                    st.session_state.extra_layers = load_layers_from_storage()
                    st.success("Layer '" + layer_name_input + "' ditambahkan secara permanen!")
                    st.rerun()
                elif not layer_name_input.strip():
                    st.warning("Masukkan nama layer terlebih dahulu.")
                elif not uploaded_layer:
                    st.warning("Pilih file KMZ/KML terlebih dahulu.")

            # Daftar layer tersedia
            if st.session_state.extra_layers:
                st.markdown(
                    "<p style='font-size:0.75rem;font-weight:700;color:#0b3327;"
                    "margin:14px 0 6px 0;'>Layer Tersedia:</p>",
                    unsafe_allow_html=True
                )
                for i, layer in enumerate(st.session_state.extra_layers):
                    cc = layer.get('color_config', {'mode': 'single', 'color': '#27ae60'})
                    dot_clr = (cc['color'] if cc['mode'] == 'single'
                               else PALETTES.get(cc.get('palette', ''),
                                                 ['#27ae60'])[0])
                    lc1, lc2, lc3, lc4, lc5 = st.columns([3, 1, 1, 1, 1])
                    with lc1:
                        st.markdown(
                            "<div style='font-size:0.78rem;color:#1a3a2a;padding-top:6px;'>"
                            "<span style='display:inline-block;width:10px;height:10px;"
                            "border-radius:50%;background:" + dot_clr + ";"
                            "margin-right:6px;'></span>" + layer['name'] + "</div>",
                            unsafe_allow_html=True
                        )
                    with lc2:
                        vis = st.toggle(
                            "👁", value=layer['visible'],
                            key="layer_vis_" + str(i),
                            help="Tampilkan/sembunyikan",
                            label_visibility="collapsed"
                        )
                        if vis != layer['visible']:
                            st.session_state.extra_layers[i]['visible'] = vis
                            # Simpan ke storage
                            save_layers_to_storage(st.session_state.extra_layers)
                            st.rerun()
                    with lc3:
                        if cc['mode'] == 'single':
                            new_color = st.color_picker(
                                "Warna", cc.get('color', '#e74c3c'),
                                key="layer_color_" + str(i),
                                label_visibility="collapsed"
                            )
                            if new_color != cc.get('color'):
                                st.session_state.extra_layers[i]['color_config']['color'] = new_color
                                # Simpan ke storage
                                save_layers_to_storage(st.session_state.extra_layers)
                                st.rerun()
                        else:
                            pal_swatches = "".join(
                                "<div style='width:9px;height:9px;background:" + c +
                                ";border-radius:1px;display:inline-block;margin:1px;'></div>"
                                for c in PALETTES.get(cc.get('palette',''), [])[:5]
                            )
                            st.markdown(
                                "<div style='padding-top:4px;'>" + pal_swatches + "</div>",
                                unsafe_allow_html=True
                            )
                    with lc4:
                        if cc['mode'] == 'palette':
                            pal_list = list(PALETTES.keys())
                            cur_pal  = cc.get('palette', pal_list[0])
                            new_pal  = st.selectbox(
                                "Palet", pal_list,
                                index=pal_list.index(cur_pal) if cur_pal in pal_list else 0,
                                key="layer_pal_" + str(i),
                                label_visibility="collapsed"
                            )
                            if new_pal != cur_pal:
                                st.session_state.extra_layers[i]['color_config']['palette'] = new_pal
                                # Simpan ke storage
                                save_layers_to_storage(st.session_state.extra_layers)
                                st.rerun()
                    with lc5:
                        if st.button("🗑️", key="del_layer_" + str(i),
                                     help="Hapus " + layer['name']):
                            # Hapus dari penyimpanan permanen
                            delete_layer_from_storage(layer['name'])
                            # Update session state dari storage
                            st.session_state.extra_layers = load_layers_from_storage()
                            st.rerun()
            else:
                st.markdown(
                    "<p style='font-size:0.72rem;color:#aaa;font-style:italic;'>"
                    "Belum ada layer tambahan.</p>",
                    unsafe_allow_html=True
                )

        # ── Session state untuk SRS yang dipilih dari tabel ──

        PATH_KMZ = "data_srs.kmz"

        if os.path.exists(PATH_KMZ) and C_SRS:
            try:
                fiona.drvsupport.supported_drivers['KML']    = 'rw'
                fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
                gdf_srs = gpd.read_file(PATH_KMZ, driver='KML')

                df_sp = (
                    df.assign(**{C_SRS: df[C_SRS].astype(str).str.split(',')})
                    .explode(C_SRS)
                    .assign(**{C_SRS: lambda d: d[C_SRS].str.strip()})
                )
                srs_agg_map = df_sp.groupby(C_SRS).agg(
                    Pagu_Total=(C_PAGU, 'sum'),
                    Jumlah_Kegiatan=(C_PAGU, 'count')
                ).reset_index()

                gdf_m = gdf_srs.merge(
                    srs_agg_map, left_on='Name', right_on=C_SRS, how='left'
                )
                gdf_m['Pagu_Total']      = gdf_m['Pagu_Total'].fillna(0)
                gdf_m['Jumlah_Kegiatan'] = gdf_m['Jumlah_Kegiatan'].fillna(0).astype(int)

                map_location = [-7.88, 110.4]
                map_zoom = 10
                selected_srs = st.session_state.selected_srs_map
                if selected_srs:
                    match = gdf_m[gdf_m['Name'] == selected_srs]
                    if not match.empty and match.geometry.iloc[0] is not None:
                        try:
                            centroid = match.geometry.iloc[0].centroid
                            map_location = [centroid.y, centroid.x]
                            map_zoom = 12
                        except Exception:
                            pass

                # ── Pilihan Basemap compact ──
                _bm_c1, _bm_c2, _bm_c3 = st.columns([4, 1, 1])
                with _bm_c2:
                    if st.button("🏙️ Street", key="bm_street", use_container_width=True):
                        st.session_state["basemap_choice"] = "street"
                        st.rerun()
                with _bm_c3:
                    if st.button("🛰️ Satelit", key="bm_sat", use_container_width=True):
                        st.session_state["basemap_choice"] = "sat"
                        st.rerun()

                # ── Input pencarian lokasi ──
                _sc1, _sc2 = st.columns([5, 1])
                with _sc1:
                    search_location = st.text_input(
                        "🔍 Cari lokasi",
                        placeholder="Cari kantor, desa, jalan, atau tempat lain...",
                        key="map_search_location",
                        label_visibility="collapsed"
                    )
                with _sc2:
                    btn_search_loc = st.button("🔍 Cari", key="btn_search_loc", use_container_width=True)

                _bm = st.session_state.get("basemap_choice", "street")
                m_map = folium.Map(location=map_location, zoom_start=map_zoom, tiles=None)
                if _bm == "sat":
                    folium.TileLayer(
                        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                        attr="Esri, Maxar, Earthstar Geographics",
                        name="Satelit", show=True, control=False,
                    ).add_to(m_map)
                else:
                    folium.TileLayer(
                        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                        attr="OpenStreetMap contributors",
                        name="Street", show=True, control=False,
                    ).add_to(m_map)

                choropleth = folium.Choropleth(
                    geo_data=gdf_m,
                    data=gdf_m,
                    columns=['Name', 'Pagu_Total'],
                    key_on='feature.properties.Name',
                    fill_color='YlGn',
                    fill_opacity=0.72,
                    line_opacity=0.25,
                    nan_fill_color='#f0f4f3',
                    legend_name='Pagu Anggaran SRS',
                    name='Sebaran Pagu per SRS',
                )
                choropleth.add_to(m_map)

                # Sembunyikan legenda bawaan (hapus macro_element_div dari control)
                for key in list(choropleth._children.keys()):
                    if 'color_map' in key:
                        choropleth._children[key].render = lambda **kwargs: ""
                        break

                # Legenda kustom 5 kategori
                BREAKPOINTS = [0, 6_500_000_000, 100_000_000_000,
                               500_000_000_000, 1_000_000_000_000]
                LEGEND_LABELS = ["Sangat Rendah","Rendah","Sedang","Tinggi","Sangat Tinggi"]
                YL_GN_COLORS  = ["#ffffcc","#c2e699","#78c679","#31a354","#006837"]

                def fmt_miliar(v):
                    if v == 0: return "Rp 0"
                    elif v >= 1_000_000_000_000: return "Rp " + str(round(v/1_000_000_000_000,1)) + " T"
                    elif v >= 1_000_000_000:     return "Rp " + str(round(v/1_000_000_000,1)) + " M"
                    elif v >= 1_000_000:         return "Rp " + str(int(v/1_000_000)) + " jt"
                    else:                        return fmt_rp_full(v)

                RANGE_LABELS = [
                    "0 – " + fmt_miliar(BREAKPOINTS[1]),
                    fmt_miliar(BREAKPOINTS[1]) + " – " + fmt_miliar(BREAKPOINTS[2]),
                    fmt_miliar(BREAKPOINTS[2]) + " – " + fmt_miliar(BREAKPOINTS[3]),
                    fmt_miliar(BREAKPOINTS[3]) + " – " + fmt_miliar(BREAKPOINTS[4]),
                    "> " + fmt_miliar(BREAKPOINTS[4]),
                ]
                legend_rows = ""
                for _i, (_c, _l, _r) in enumerate(
                        zip(YL_GN_COLORS, LEGEND_LABELS, RANGE_LABELS)):
                    legend_rows += (
                        "<div style='display:flex;align-items:center;gap:8px;"
                        "margin-top:" + ("5" if _i > 0 else "0") + "px;'>"
                        "<div style='background:" + _c + ";width:22px;height:13px;"
                        "border-radius:3px;border:1px solid #ccc;flex-shrink:0;'></div>"
                        "<div><div style='color:#222;font-size:0.7rem;font-weight:600;"
                        "line-height:1.2;'>" + _l + "</div>"
                        "<div style='color:#777;font-size:0.62rem;'>" + _r + "</div>"
                        "</div></div>"
                    )
                legend_html = (
                    "<div style='position:fixed;bottom:30px;right:30px;z-index:1000;"
                    "background:white;border-radius:10px;padding:12px 16px;"
                    "box-shadow:0 2px 10px rgba(0,0,0,0.18);min-width:220px;'>"
                    "<div style='font-weight:700;color:#0b3327;margin-bottom:8px;"
                    "font-size:0.75rem;'>Total Pagu Anggaran</div>"
                    + legend_rows + "</div>"
                )
                m_map.get_root().html.add_child(folium.Element(legend_html))

                # Highlight SRS yang dipilih
                if selected_srs:
                    match = gdf_m[gdf_m['Name'] == selected_srs]
                    if not match.empty:
                        folium.GeoJson(
                            match,
                            style_function=lambda x: {
                                'fillColor': '#e74c3c', 'fillOpacity': 0.5,
                                'color': '#c0392b', 'weight': 3
                            },
                            name='SRS Dipilih'
                        ).add_to(m_map)

                # Tooltip SRS (tanpa nama di layer control)
                gdf_m['Pagu_Display'] = gdf_m['Pagu_Total'].apply(fmt_rp_full)
                folium.GeoJson(
                    gdf_m,
                    tooltip=folium.GeoJsonTooltip(
                        fields=['Name', 'Pagu_Display', 'Jumlah_Kegiatan'],
                        aliases=['SRS:', 'Total Pagu:', 'Jumlah Kegiatan:'],
                        localize=False
                    ),
                    style_function=lambda x: {'fillOpacity': 0, 'weight': 0},
                    show=True,
                    control=False   # <-- tidak muncul di LayerControl
                ).add_to(m_map)

                # ── Render Layer Tambahan ──

                # Field bawaan KML/KMZ dari ArcMap yang perlu disembunyikan
                KML_SKIP = {
                    'timestamp','begin','end','altitudemode','tessellate','extrude',
                    'visibility','draworder','icon','description','styleurl','snippet',
                    'lookat','camera','address','phonenumber','fid','objectid',
                    'shape_leng','shape_area','shape_le_1'
                }
                EMPTY_VALS = {'none','nan','','null','-1','0.0','<null>'}

                def _clean_attr_cols(gdf):
                    """Kembalikan list kolom yang tidak kosong & bukan field bawaan KML."""
                    all_cols = [c for c in gdf.columns if c != 'geometry']
                    # Filter field bawaan
                    filtered = [c for c in all_cols if c.lower() not in KML_SKIP]
                    # Filter kolom yang SEMUA nilainya kosong
                    result = []
                    for c in filtered:
                        non_empty = gdf[c].astype(str).str.strip().str.lower()
                        if not non_empty.isin(EMPTY_VALS).all():
                            result.append(c)
                    return result

                def _row_clean_fields(row, cols):
                    """Kembalikan list kolom yang punya nilai untuk baris ini."""
                    result = []
                    for c in cols:
                        val = str(row.get(c, '')).strip()
                        if val.lower() not in EMPTY_VALS:
                            result.append(c)
                    return result

                def _detect_foto_col(row, cols):
                    """Deteksi kolom foto — URL http atau nama file gambar lokal."""
                    for c in cols:
                        val = str(row.get(c, '')).strip().lower()
                        if (val.startswith('http') or
                            any(val.endswith(ext) for ext in ('.jpg','.jpeg','.png','.webp','.gif')) or
                            c.lower() in ('foto','photo','gambar','image','picture')):
                            return c
                    return None

                def _build_popup_html(row, cols, foto_col, lyr_name, drive_folder_id=''):
                    """Buat HTML popup dengan foto (jika ada) dan tabel atribut bersih."""
                    foto_html = ""
                    rows_html = ""
                    for c in cols:
                        val = str(row.get(c, '')).strip()
                        if not val or val.lower() in EMPTY_VALS:
                            continue
                        if c == foto_col:
                            # Konversi ke URL gambar
                            img_url = None
                            if val.startswith('http'):
                                if 'drive.google.com/file/d/' in val:
                                    fid = val.split('/file/d/')[1].split('/')[0]
                                    img_url = f"https://drive.google.com/thumbnail?id={fid}&sz=w400"
                                elif 'drive.google.com/open?id=' in val:
                                    fid = val.split('id=')[1].split('&')[0]
                                    img_url = f"https://drive.google.com/thumbnail?id={fid}&sz=w400"
                                else:
                                    img_url = val
                            elif drive_folder_id and any(val.lower().endswith(e) for e in ('.jpg','.jpeg','.png')):
                                # Nama file lokal — coba cari di Drive berdasarkan nama
                                img_url = None  # tidak bisa resolve tanpa query API
                                rows_html += (
                                    f"<tr><td style='color:#7a9a8a;font-size:0.7rem;"
                                    f"padding:2px 6px;white-space:nowrap;'>{c}</td>"
                                    f"<td style='font-size:0.72rem;color:#1a3a2a;"
                                    f"padding:2px 6px;'>{val}</td></tr>"
                                )
                                continue
                            if img_url:
                                foto_html = (
                                    f"<div style='margin-bottom:8px;text-align:center;'>"
                                    f"<img src='{img_url}' style='width:100%;max-width:280px;"
                                    f"border-radius:6px;border:1px solid #ddd;' "
                                    f"onerror=\"this.style.display='none';\"/></div>"
                                )
                                continue
                        rows_html += (
                            f"<tr><td style='color:#7a9a8a;font-size:0.7rem;"
                            f"padding:2px 6px;white-space:nowrap;'>{c}</td>"
                            f"<td style='font-size:0.72rem;color:#1a3a2a;"
                            f"padding:2px 6px;word-break:break-word;max-width:200px;'>{val}</td></tr>"
                        )
                    table = (
                        f"<table style='border-collapse:collapse;width:100%;'>"
                        f"{rows_html}</table>"
                    ) if rows_html else f"<span style='font-size:0.75rem;'>{lyr_name}</span>"
                    return foto_html + table

                for layer in st.session_state.extra_layers:
                    layer_path = get_layer_file_path(layer)
                    if not layer_path:
                        continue
                    try:
                        gdf_layer = read_layer_geodataframe(layer_path, layer.get('type', 'kmz'))
                        cc_l     = layer.get('color_config', {'mode': 'single', 'color': '#e74c3c'})
                        lyr_name = layer['name']
                        lyr_show = layer['visible']

                        # Kolom bersih (berlaku untuk semua tipe geometri)
                        clean_cols = _clean_attr_cols(gdf_layer)

                        # Tentukan warna
                        if cc_l['mode'] == 'single':
                            clr = cc_l['color']
                            cat_col, cmap_cat = None, {}
                        else:
                            pal_nm     = cc_l.get('palette', list(PALETTES.keys())[0])
                            pal_colors = PALETTES.get(pal_nm, list(PALETTES.values())[0])
                            cat_col    = 'Name' if 'Name' in gdf_layer.columns else (clean_cols[0] if clean_cols else None)
                            uniq_names = gdf_layer[cat_col].dropna().unique().tolist() if cat_col else []
                            cmap_cat   = {nm: pal_colors[i % len(pal_colors)] for i, nm in enumerate(uniq_names)}
                            clr        = pal_colors[0]

                        geom_types = gdf_layer.geometry.geom_type.dropna().unique()
                        is_point   = all(gt in ('Point', 'MultiPoint') for gt in geom_types)
                        is_line    = all(gt in ('LineString', 'MultiLineString') for gt in geom_types)

                        if is_point:
                            # ── Point: MarkerCluster dengan popup bersih ──
                            folium_color_map = {
                                '#e41a1c':'red','#d73027':'red','#377eb8':'blue',
                                '#2166ac':'blue','#4daf4a':'green','#1a9850':'green',
                                '#984ea3':'purple','#762a83':'purple','#ff7f00':'orange',
                                '#a65628':'beige','#f781bf':'pink','#252525':'black',
                                '#525252':'darkgray','#737373':'gray',
                            }
                            cluster = MarkerCluster(name=lyr_name, show=lyr_show).add_to(m_map)
                            for _, row in gdf_layer.iterrows():
                                geom = row.geometry
                                if geom is None:
                                    continue
                                pts = list(geom.geoms) if geom.geom_type == 'MultiPoint' else [geom]
                                pin_clr = cmap_cat.get(str(row.get(cat_col,'')), clr) if (cc_l['mode']=='palette' and cat_col) else clr
                                f_color = folium_color_map.get(pin_clr.lower(), 'red')
                                row_cols  = _row_clean_fields(row, clean_cols)
                                foto_col  = _detect_foto_col(row, row_cols)
                                popup_html = _build_popup_html(row, row_cols, foto_col, lyr_name, DRIVE_FOLDER_ID or '')
                                tip_val = str(row.get('Name', row.get(row_cols[0], lyr_name) if row_cols else lyr_name))
                                for pt in pts:
                                    folium.Marker(
                                        location=[pt.y, pt.x],
                                        popup=folium.Popup(popup_html, max_width=300),
                                        tooltip=tip_val,
                                        icon=folium.Icon(color=f_color, icon='circle', prefix='fa')
                                    ).add_to(cluster)

                        else:
                            # ── Polygon / Line: GeoJson dengan tooltip bersih ──
                            # Untuk tooltip, gunakan kolom bersih yang ada nilainya
                            tip_fields   = clean_cols[:6]
                            tip_aliases  = [f"{c}:" for c in tip_fields]

                            weight = 2 if not is_line else 3

                            if cc_l['mode'] == 'single':
                                def _make_style(c, w):
                                    return lambda x: {
                                        'color': c, 'fillColor': c,
                                        'weight': w, 'fillOpacity': 0.35, 'opacity': 0.9
                                    }
                                folium.GeoJson(
                                    gdf_layer, name=lyr_name, show=lyr_show,
                                    style_function=_make_style(clr, weight),
                                    tooltip=folium.GeoJsonTooltip(
                                        fields=tip_fields, aliases=tip_aliases,
                                        localize=False
                                    ) if tip_fields else None
                                ).add_to(m_map)
                            else:
                                def _make_cat_style(cmap, fallback, col, w):
                                    def _s(feature):
                                        nm = feature['properties'].get(col, '') if col else ''
                                        c  = cmap.get(nm, fallback)
                                        return {'color': c, 'fillColor': c,
                                                'weight': w, 'fillOpacity': 0.42, 'opacity': 0.9}
                                    return _s
                                folium.GeoJson(
                                    gdf_layer, name=lyr_name, show=lyr_show,
                                    style_function=_make_cat_style(cmap_cat, clr, cat_col, weight),
                                    tooltip=folium.GeoJsonTooltip(
                                        fields=tip_fields, aliases=tip_aliases,
                                        localize=False
                                    ) if tip_fields else None
                                ).add_to(m_map)

                    except Exception as layer_err:
                        st.warning("Layer '" + layer['name'] + "' gagal dimuat: " + str(layer_err))

                # ── Pencarian lokasi & penambahan marker ──
                if (btn_search_loc or search_location) and search_location.strip():
                    if "last_search_loc" not in st.session_state:
                        st.session_state.last_search_loc = ""
                    # Jalankan geocode jika tombol ditekan atau keyword berubah
                    if btn_search_loc or search_location != st.session_state.last_search_loc:
                        st.session_state.last_search_loc = search_location
                        geo_result = geocode_location(search_location)
                        st.session_state.last_geo_result = geo_result
                    geo_result = st.session_state.get("last_geo_result", {"success": False})
                    if geo_result.get('success'):
                        lat, lon = geo_result['lat'], geo_result['lon']
                        folium.Marker(
                            location=[lat, lon],
                            popup=f"<b>📍 Hasil Pencarian</b><br>{geo_result['name']}",
                            icon=folium.Icon(color='red', icon='search', prefix='fa'),
                            name='Hasil Pencarian Lokasi'
                        ).add_to(m_map)
                        m_map.location = [lat, lon]
                        m_map.zoom_start = 13
                    else:
                        st.warning(f"❌ Lokasi '{search_location}' tidak ditemukan. Coba kata kunci lain.")

                # LayerControl – collapsed (ikon tumpuk, buka saat diklik)
                folium.LayerControl(collapsed=True, position='topright').add_to(m_map)
                hide_internal = folium.Element("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        document.querySelectorAll(
            '.leaflet-control-layers-overlays label'
        ).forEach(function(lbl) {
            var txt = (lbl.textContent || '').trim();
            if (txt === 'SRS Dipilih' || txt === 'Info Tooltip SRS' ||
                txt.startsWith('macro_element')) {
                lbl.closest('label') && (lbl.closest('label').style.display = 'none');
                lbl.style.display = 'none';
            }
        });
    }, 900);
});
</script>""")
                m_map.get_root().html.add_child(hide_internal)

                # ── Geocoder (pencarian lokasi) via Leaflet plugin ──
                geocoder_html = """
<script>
(function() {
  var MAX_ATTEMPTS = 15;
  function tryAddGeocoder(attempt) {
    var iframes = document.querySelectorAll('iframe');
    var added = false;
    iframes.forEach(function(fr) {
      try {
        var w = fr.contentWindow;
        if (!w || !w.L || w._taruGeocoderAdded) return;
        
        // Coba akses map object
        var mapObj = null;
        if (w.L && w.L._maps && Object.keys(w.L._maps).length > 0) {
          mapObj = Object.values(w.L._maps)[0];
        }
        if (!mapObj || !w.L.Control) return;
        
        w._taruGeocoderAdded = true;
        added = true;
        var d = fr.contentDocument || fr.contentWindow.document;
        
        // Load CSS
        var lnk = d.createElement('link');
        lnk.rel = 'stylesheet';
        lnk.href = 'https://unpkg.com/leaflet-control-geocoder/dist/Control.Geocoder.css';
        d.head.appendChild(lnk);
        
        // Load Script
        var sc = d.createElement('script');
        sc.src = 'https://unpkg.com/leaflet-control-geocoder/dist/Control.Geocoder.js';
        sc.onload = function() {
          try {
            if (w.L && w.L.Control && w.L.Control.geocoder) {
              w.L.Control.geocoder({
                defaultMarkGeocode: true,
                position: 'topleft',
                placeholder: 'Cari lokasi / kantor / desa...',
                errorMessage: 'Lokasi tidak ditemukan.',
                geocoder: w.L.Control.Geocoder.nominatim()
              }).addTo(mapObj);
            }
          } catch(e) {
            console.log('Geocoder error:', e);
          }
        };
        sc.onerror = function() {
          console.log('Failed to load geocoder script');
        };
        d.head.appendChild(sc);
      } catch(e) {
        console.log('Geocoder attempt error:', e);
      }
    });
    if (!added && attempt < MAX_ATTEMPTS) {
      setTimeout(function(){ tryAddGeocoder(attempt+1); }, 500);
    }
  }
  document.addEventListener('DOMContentLoaded', function(){ 
    setTimeout(function(){ tryAddGeocoder(0); }, 1200); 
  });
})();
</script>"""
                m_map.get_root().html.add_child(folium.Element(geocoder_html))

                st_folium(m_map, use_container_width=True, height=480)


            except Exception as map_err:
                st.error(f"Gagal memuat peta KMZ: {map_err}")
                m_base = folium.Map(location=[-7.88, 110.4], zoom_start=10,
                                    tiles="CartoDB Positron")
                st_folium(m_base, use_container_width=True, height=380)
        else:
            st.info(
                "File `data_srs.kmz` belum tersedia. "
                "Letakkan file tersebut di folder yang sama dengan `app.py` "
                "untuk menampilkan peta choropleth."
            )
            m_base = folium.Map(location=[-7.88, 110.4], zoom_start=10,
                                tiles="CartoDB Positron")
            folium.Marker(
                [-7.797, 110.370],
                popup="Daerah Istimewa Yogyakarta",
                icon=folium.Icon(color='green', icon='info-sign')
            ).add_to(m_base)
            st_folium(m_base, use_container_width=True, height=380)

        # A.1 + A.2 – Tabel ringkasan SRS dengan 19 kategori dan klik-untuk-peta
        if C_SRS:
            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='card-title' style='font-size:0.82rem;'>"
                "Ringkasan per SRS (klik baris untuk melihat di peta)</div>",
                unsafe_allow_html=True
            )

            # A.1 – Gunakan rekapitulasi 19 kategori
            df_srs_rekap_peta, total_asli, total_srs, pagu_dbl = \
                buat_rekapitulasi_srs(df, C_SRS, C_PAGU)

            if pagu_dbl > 0:
                st.markdown(
                    f"<div style='background:#fff8e1;border:1px solid #f39c12;"
                    f"border-radius:8px;padding:8px 12px;margin-bottom:10px;"
                    f"font-size:0.72rem;color:#7d5a00;'>"
                    f"ℹ️ <b>Catatan:</b> Total pagu SRS ({fmt_rp_full(total_srs)}) "
                    f"mencakup {fmt_rp_full(pagu_dbl)} pagu double dari kegiatan multi-SRS. "
                    f"Total kegiatan asli: {fmt_rp_full(total_asli)}.</div>",
                    unsafe_allow_html=True
                )

            if not df_srs_rekap_peta.empty:
                df_srs_rekap_peta['Total Pagu Anggaran'] = \
                    df_srs_rekap_peta['Total_Pagu'].apply(fmt_rp_full)

                # A.2 – Gunakan st.dataframe dengan on_select untuk navigasi peta
                srs_tbl_display = df_srs_rekap_peta[
                    ['SRS', 'Jumlah_Kegiatan', 'Total Pagu Anggaran']
                ].rename(columns={
                    'SRS': 'Satuan Ruang Strategis',
                    'Jumlah_Kegiatan': 'Jumlah Kegiatan'
                })

                event = st.dataframe(
                    srs_tbl_display,
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                    on_select="rerun",
                    selection_mode="single-row"
                )

                # A.2 – Tangkap baris yang diklik dan update peta
                if event and hasattr(event, 'selection') and event.selection:
                    sel_rows = event.selection.get('rows', [])
                    if sel_rows:
                        idx = sel_rows[0]
                        nama_srs = df_srs_rekap_peta.iloc[idx]['SRS']
                        if st.session_state.selected_srs_map != nama_srs:
                            st.session_state.selected_srs_map = nama_srs
                            st.rerun()

                if st.session_state.selected_srs_map:
                    _sel_nm = st.session_state.selected_srs_map
                    _ci, _cr = st.columns([4, 1])
                    with _ci:
                        st.markdown(
                            f"<p style='font-size:0.72rem;color:#27ae60;margin:4px 0;'>"
                            f"Peta menampilkan: <b>{_sel_nm}</b></p>",
                            unsafe_allow_html=True
                        )
                    with _cr:
                        if st.button("Reset Peta", key="reset_srs_map"):
                            st.session_state.selected_srs_map = None
                            st.rerun()

                    # ── Tabel mini kegiatan di SRS yang dipilih ──
                    if C_SRS:
                        _df_sel = df[
                            df[C_SRS].astype(str).str.contains(_sel_nm, case=False, na=False)
                        ].copy()
                        if not _df_sel.empty:
                            _mini_cols = [c for c in [C_TAHUN, C_OPD, C_PELAYAN, C_PAGU] if c]
                            _df_mini = _df_sel[_mini_cols].copy()
                            if C_PAGU in _df_mini.columns:
                                _pagu_total = _df_sel[C_PAGU].sum()
                                _df_mini[C_PAGU] = _df_mini[C_PAGU].apply(fmt_rp_full)

                            st.markdown(
                                f"<div style='margin:10px 0 5px 0;font-size:0.78rem;"
                                f"font-weight:700;color:#0b3327;'>"
                                f"Kegiatan di <span style='color:#27ae60;'>{_sel_nm}</span>"
                                f" &nbsp;|&nbsp; {len(_df_sel):,} kegiatan"
                                f" &nbsp;·&nbsp; {fmt_rp_full(_pagu_total)} total pagu</div>",
                                unsafe_allow_html=True
                            )
                            _th_m = "".join(
                                f"<th style='background:#0b3327;color:#fff;font-size:0.68rem;"
                                f"padding:6px 10px;text-align:left;white-space:nowrap;'>{c}</th>"
                                for c in _df_mini.columns
                            )
                            _tr_m = ""
                            for _ri, _row in _df_mini.iterrows():
                                _bg = "#ffffff" if _ri % 2 == 0 else "#f7fdf9"
                                _tds = "".join(
                                    f"<td style='padding:5px 10px;font-size:0.68rem;"
                                    f"color:#1a3a2a;border-bottom:1px solid #eef2f0;"
                                    f"word-break:break-word;max-width:200px;'>{str(_row[c])}</td>"
                                    for c in _df_mini.columns
                                )
                                _tr_m += f"<tr style='background:{_bg};'>{_tds}</tr>"
                            st.markdown(
                                f"<div style='overflow:auto;max-height:700px;"
                                f"border-radius:8px;border:1px solid #dce8e2;margin-bottom:4px;'>"
                                f"<table style='border-collapse:collapse;width:100%;'>"
                                f"<thead><tr>{_th_m}</tr></thead>"
                                f"<tbody>{_tr_m}</tbody></table></div>",
                                unsafe_allow_html=True
                            )
                            if st.button(
                                f"Lihat Semua Data Lengkap untuk {_sel_nm}",
                                key=f"btn_goto_data_srs_{hash(_sel_nm)}",
                                use_container_width=True
                            ):
                                st.session_state["data_search_prefill"] = _sel_nm
                                st.rerun()
                        else:
                            st.info(f"Tidak ada kegiatan yang tercatat di {_sel_nm}.")

        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    # TAB 3 · DATA LENGKAP
    # ══════════════════════════════════════════════════════════
    with tab_data:
        st.markdown("<div class='card'>", unsafe_allow_html=True)

        hdr1, hdr2 = st.columns([3, 1])
        with hdr1:
            st.markdown(
                f"<div class='card-title' style='margin-bottom:8px;'>"
                f"📄 Data Kegiatan Tata Ruang &nbsp;"
                f"<span style='font-size:0.72rem;color:#7a9a8a;font-weight:500;'>"
                f"({len(df):,} baris)</span></div>",
                unsafe_allow_html=True
            )
        with hdr2:
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "⬇️  Unduh CSV",
                data=csv_bytes,
                file_name="taru_istimewa_data.csv",
                mime="text/csv",
                use_container_width=True
            )

        _prefill_val = st.session_state.pop("data_search_prefill", "")
        search_q = st.text_input(
            "",
            placeholder="Cari kata kunci (nama kegiatan, OPD, detail...)",
            key="data_search",
            label_visibility="collapsed",
            value=_prefill_val
        )

        df_show = df.copy()
        if search_q:
            mask = df_show.apply(
                lambda col: col.astype(str).str.contains(
                    search_q, case=False, na=False)
            ).any(axis=1)
            df_show = df_show[mask]

        st.markdown(
            f"<p style='font-size:0.69rem;color:#7a9a8a;margin:4px 0 8px;'>"
            f"Menampilkan {len(df_show):,} dari {len(df):,} data</p>",
            unsafe_allow_html=True
        )

        df_display = df_show.copy()
        df_display['Pagu Anggaran'] = df_display['Pagu Anggaran'].apply(fmt_rp_full)

        # Wrap text: render sebagai HTML table dengan word-wrap agar teks panjang terbaca
        # Tentukan lebar kolom default berdasarkan tipe konten
        col_widths_default = {}
        for col in df_display.columns:
            if col == 'Pagu Anggaran':
                col_widths_default[col] = 140
            elif col in ([C_OPD] if C_OPD else []) or \
                 col in ([C_DETAIL] if C_DETAIL else []) or \
                 col in ([C_SRS] if C_SRS else []):
                col_widths_default[col] = 220
            elif col in ([C_TAHUN] if C_TAHUN else []):
                col_widths_default[col] = 80
            else:
                col_widths_default[col] = 150

        # Initialize session state untuk custom column widths
        if 'col_widths_custom' not in st.session_state:
            st.session_state.col_widths_custom = col_widths_default.copy()

        # Expander untuk pengaturan lebar kolom
        with st.expander("⚙️  Sesuaikan Lebar Kolom", expanded=False):
            col_adjust_cols = st.columns([1, 1])
            with col_adjust_cols[0]:
                if st.button("🔄  Reset ke Default", use_container_width=True):
                    st.session_state.col_widths_custom = col_widths_default.copy()
                    st.rerun()

            with col_adjust_cols[1]:
                width_all = st.slider(
                    "Sesuaikan semua kolom (%)",
                    min_value=60,
                    max_value=350,
                    value=100,
                    step=10,
                    key="width_all_slider",
                    label_visibility="collapsed"
                )

            # Update semua kolom jika slider global berubah
            if width_all != 100:
                for col in st.session_state.col_widths_custom:
                    st.session_state.col_widths_custom[col] = int(
                        col_widths_default[col] * (width_all / 100)
                    )

            st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)

            # Slider untuk setiap kolom - dibuat dalam 3 kolom
            cols_slider = st.columns(3)
            for idx, col in enumerate(df_display.columns):
                col_idx = idx % 3
                with cols_slider[col_idx]:
                    current_width = st.session_state.col_widths_custom.get(col, col_widths_default[col])
                    new_width = st.slider(
                        f"{col}",
                        min_value=60,
                        max_value=350,
                        value=current_width,
                        step=10,
                        key=f"width_{col}"
                    )
                    st.session_state.col_widths_custom[col] = new_width

        # Konversi ke pixel untuk digunakan di HTML
        col_widths = {col: f"{width}px" for col, width in st.session_state.col_widths_custom.items()}

        # Buat colgroup untuk set lebar kolom yang konsisten
        colgroup_html = "".join(
            f"<col style='width:{col_widths.get(c, '120px')};'>"
            for c in df_display.columns
        )

        # Buat header
        th_cells = "".join(
            "<th style='position:sticky;top:0;background:#0b3327;color:#fff;"
            "font-size:0.72rem;font-weight:700;padding:8px 10px;text-align:left;"
            "width:" + col_widths.get(c, "120px") + ";'>" + c + "</th>"
            for c in df_display.columns
        )
        # Buat baris data
        tr_rows = ""
        for ridx, row in df_display.iterrows():
            bg = "#ffffff" if ridx % 2 == 0 else "#f7fdf9"
            td_cells = "".join(
                "<td style='padding:7px 10px;font-size:0.72rem;color:#1a3a2a;"
                "border-bottom:1px solid #eef2f0;vertical-align:top;"
                "word-wrap:break-word;word-break:break-word;"
                "width:" + col_widths.get(c, "120px") + ";'>" + str(row[c]) + "</td>"
                for c in df_display.columns
            )
            tr_rows += "<tr style='background:" + bg + ";'>" + td_cells + "</tr>"

        table_html = f"""
<div style="overflow:auto;max-height:520px;border-radius:10px;
     border:1px solid #dce8e2;margin-top:4px;">
  <table style="border-collapse:collapse;width:100%;table-layout:fixed;">
    <colgroup>{colgroup_html}</colgroup>
    <thead><tr>{th_cells}</tr></thead>
    <tbody>{tr_rows}</tbody>
  </table>
</div>"""
        st.markdown(table_html, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    # TAB 4 · DATA PENDUKUNG
    # ══════════════════════════════════════════════════════════
    with tab_pendukung:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='card-title'>📁 Data Pendukung </div>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='font-size:0.8rem;color:#555;margin-bottom:16px;'>"
            "Cari kata kunci untuk melihat rekapitulasi data kegiatan dan file pendukung "
            "yang berkaitan. Contoh: <i>Air Bersih, Jalan, APJ</i>, dll.</p>",
            unsafe_allow_html=True
        )

        # ── Search bar bersama ──
        _pc1, _pc2 = st.columns([4, 1])
        with _pc1:
            pend_keyword = st.text_input(
                "", placeholder="Ketik kata kunci (contoh: Air Bersih, Jalan, APJ...)",
                key="pend_keyword_input", label_visibility="collapsed"
            )
        with _pc2:
            btn_pend_cari = st.button("Cari", key="btn_pend_cari", use_container_width=True)

        # ── Rekapitulasi data utama berdasarkan keyword ──
        if pend_keyword.strip():
            kw_p = pend_keyword.strip()
            mask_p = df.apply(
                lambda col: col.astype(str).str.contains(kw_p, case=False, na=False)
            ).any(axis=1)
            df_pend_filtered = df[mask_p].copy()

            st.markdown(
                f"<div style='margin:14px 0 6px 0;font-size:0.82rem;font-weight:700;"
                f"color:#0b3327;'>Rekapitulasi Data — <span style='color:#27ae60;'>"
                f"{kw_p}</span> ({len(df_pend_filtered):,} kegiatan)</div>",
                unsafe_allow_html=True
            )
            if df_pend_filtered.empty:
                st.info("Tidak ada data kegiatan yang sesuai kata kunci tersebut.")
            else:
                # Filter tahun anggaran di data pendukung
                if C_TAHUN:
                    tahun_opts = sorted(df_pend_filtered[C_TAHUN].dropna().unique())
                    sel_tahun_pend = st.multiselect(
                        "📅 Filter Tahun Anggaran",
                        tahun_opts,
                        placeholder="Semua tahun",
                        key="pend_tahun_filter"
                    )
                    if sel_tahun_pend:
                        df_pend_filtered = df_pend_filtered[df_pend_filtered[C_TAHUN].isin(sel_tahun_pend)]

                _pm1, _pm2, _pm3 = st.columns(3)
                _pm1.metric("Jumlah Kegiatan", f"{len(df_pend_filtered):,}")
                _pm2.metric("Total Pagu", fmt_rp_full(df_pend_filtered[C_PAGU].sum()))
                _pm3.metric("Jumlah OPD", str(df_pend_filtered[C_OPD].nunique() if C_OPD else "-"))

                _show_cols = [c for c in [C_TAHUN, C_OPD, C_PELAYAN, C_FOKUS, C_PAGU] if c]
                _df_show = df_pend_filtered[_show_cols].copy()
                if C_PAGU in _df_show.columns:
                    _df_show[C_PAGU] = _df_show[C_PAGU].apply(fmt_rp_full)

                _th = "".join(
                    f"<th style='background:#0b3327;color:#fff;font-size:0.7rem;"
                    f"padding:7px 10px;text-align:left;white-space:nowrap;'>{c}</th>"
                    for c in _df_show.columns
                )
                _tr = ""
                for _ri, _row in _df_show.head(50).iterrows():
                    _bg = "#ffffff" if _ri % 2 == 0 else "#f7fdf9"
                    _tds = "".join(
                        f"<td style='padding:5px 10px;font-size:0.7rem;color:#1a3a2a;"
                        f"border-bottom:1px solid #eef2f0;word-break:break-word;"
                        f"max-width:240px;'>{str(_row[c])}</td>"
                        for c in _df_show.columns
                    )
                    _tr += f"<tr style='background:{_bg};'>{_tds}</tr>"
                _note = (
                    f"<p style='font-size:0.67rem;color:#aaa;margin:4px 0;'>"
                    f"Menampilkan 50 dari {len(df_pend_filtered):,} baris.</p>"
                ) if len(df_pend_filtered) > 50 else ""
                st.markdown(
                    f"<div style='overflow:auto;max-height:340px;border-radius:8px;"
                    f"border:1px solid #dce8e2;margin-bottom:4px;'>"
                    f"<table style='border-collapse:collapse;width:100%;'>"
                    f"<thead><tr>{_th}</tr></thead>"
                    f"<tbody>{_tr}</tbody></table></div>{_note}",
                    unsafe_allow_html=True
                )
                if st.button("Lihat Semua di Data Lengkap →", key="btn_goto_data_pend", use_container_width=True):
                    st.session_state["data_search_prefill"] = kw_p
                    st.session_state["active_tab"] = 2  # index tab Data Lengkap
                    st.rerun()

            st.markdown("<hr style='margin:14px 0;'>", unsafe_allow_html=True)
            st.markdown(
                "<div style='font-size:0.82rem;font-weight:700;color:#0b3327;"
                "margin-bottom:8px;'>File Pendukung di Google Drive</div>",
                unsafe_allow_html=True
            )

        # ── Konfigurasi Google Drive ─────────────────────────
        # ID folder Google Drive dari Streamlit Secrets
        DRIVE_FOLDER_ID = ""
        try:
            DRIVE_FOLDER_ID = st.secrets["drive_config"]["folder_id"]
        except Exception:
            pass

        if not DRIVE_FOLDER_ID:
            st.markdown(
                """
<div style="background:#f0f9f4;border:1px solid #27ae60;border-radius:12px;
     padding:20px 24px;font-size:0.82rem;color:#1a3a2a;line-height:1.8;">
  <div style="font-weight:700;font-size:0.9rem;color:#0b3327;margin-bottom:12px;">
    ⚙️ Cara Mengaktifkan Pencarian Google Drive
  </div>

  <b>Langkah 1 – Aktifkan Google Drive API</b><br>
  Buka <a href="https://console.cloud.google.com/apis/library/drive.googleapis.com"
  target="_blank" style="color:#27ae60;">Google Cloud Console → Drive API</a>
  dan klik <b>Enable</b> untuk project service account Anda.
  <br><br>

  <b>Langkah 2 – Bagikan folder ke service account</b><br>
  Buka Google Drive → klik kanan folder data pendukung → <b>Bagikan</b>.<br>
  Masukkan email service account dari <code>kunci_akses.json</code>
  (field <code>client_email</code>) sebagai <b>Viewer</b>.
  <br><br>

  <b>Langkah 3 – Buat file konfigurasi</b><br>
  Buat file <code>drive_config.json</code> di folder yang sama dengan <code>app.py</code>:
  <pre style="background:#e8f5e9;border-radius:6px;padding:10px;margin:8px 0;
       font-size:0.8rem;overflow-x:auto;">{"folder_id": "ID_FOLDER_ANDA"}</pre>

  <b>Cara menemukan ID folder:</b><br>
  Buka folder di browser → lihat URL:<br>
  <code style="background:#e8f5e9;padding:2px 6px;border-radius:4px;">
  https://drive.google.com/drive/folders/<b style="color:#c0392b;">1AbC2dEfGhIj...</b>
  </code><br>
  Bagian yang dicetak merah itulah <b>folder_id</b>-nya.
  <br><br>

  <b>Langkah 4 – Install library tambahan</b> (jika belum)<br>
  <code style="background:#e8f5e9;padding:2px 6px;border-radius:4px;">
  pip install google-api-python-client httplib2
  </code>
</div>""",
                unsafe_allow_html=True
            )
        else:
            # ── Pilihan mode pencarian ──
            search_mode = st.radio(
                "Cari di:",
                ["📄 Nama file", "📝 Isi dokumen", "🔎 Keduanya"],
                horizontal=True,
                key="drive_search_mode",
                help=(
                    "Nama file: mencari semua tipe file berdasarkan nama.\n"
                    "Isi dokumen: mencari teks di dalam Google Docs, Sheets, Slides, PDF "
                    "(file harus sudah di-index Google).\n"
                    "Keduanya: gabungan, hasil paling lengkap."
                )
            )
            st.markdown(
                "<p style='font-size:0.68rem;color:#aaa;margin:-8px 0 10px 0;'>"
                "⚠️ Pencarian isi dokumen hanya bekerja untuk Google Docs, Sheets, "
                "Slides, dan PDF. File Excel/Word kadang tidak ter-index.</p>",
                unsafe_allow_html=True
            )

            # Gunakan keyword dari input bersama di atas
            drive_keyword = pend_keyword if "pend_keyword_input" in st.session_state else ""
            btn_drive_search = btn_pend_cari

            if pend_keyword.strip():
                with st.spinner("Mencari file di Google Drive…"):
                    try:
                            from googleapiclient.discovery import build

                            scope_drive = ["https://www.googleapis.com/auth/drive.readonly"]
                            sa_info_drive = dict(st.secrets["gcp_service_account"])
                            sa_info_drive["private_key"] = sa_info_drive["private_key"].replace("\\n", "\n")
                            creds_drive = ServiceAccountCredentials.from_json_keyfile_dict(
                                sa_info_drive, scope_drive
                            )
                            import httplib2
                            http    = creds_drive.authorize(httplib2.Http())
                            service = build('drive', 'v3', http=http)

                            kw = pend_keyword.strip().replace("'", "\\'")

                            # ── Fungsi rekursif: kumpulkan semua folder ID ──
                            def get_all_folder_ids(svc, root_id):
                                """BFS untuk mendapatkan semua subfolder ID."""
                                all_ids = [root_id]
                                queue   = [root_id]
                                while queue:
                                    parent = queue.pop(0)
                                    resp   = svc.files().list(
                                        q=(f"'{parent}' in parents "
                                           f"and mimeType = 'application/vnd.google-apps.folder' "
                                           f"and trashed = false"),
                                        pageSize=100,
                                        fields="files(id)"
                                    ).execute()
                                    for sub in resp.get('files', []):
                                        if sub['id'] not in all_ids:
                                            all_ids.append(sub['id'])
                                            queue.append(sub['id'])
                                return all_ids

                            # Kumpulkan semua folder (root + subfolder)
                            with st.spinner("Memetakan struktur folder…"):
                                all_folder_ids = get_all_folder_ids(service, DRIVE_FOLDER_ID)

                            # Susun kondisi parents (maks 20 folder per query — batasi jika perlu)
                            def build_parent_clause(folder_ids):
                                parts = " or ".join(
                                    f"'{fid}' in parents" for fid in folder_ids
                                )
                                return "(" + parts + ")"

                            # Google Drive API membatasi OR clause, bagi per 20 folder
                            CHUNK = 20
                            seen_ids    = set()
                            files_dedup = []

                            for chunk_start in range(0, len(all_folder_ids), CHUNK):
                                chunk_ids    = all_folder_ids[chunk_start:chunk_start + CHUNK]
                                parent_clause = build_parent_clause(chunk_ids)
                                base_chunk    = parent_clause + " and trashed = false"

                                # Susun query berdasarkan mode
                                if search_mode == "📄 Nama file":
                                    query = base_chunk + f" and name contains '{kw}'"
                                elif search_mode == "📝 Isi dokumen":
                                    query = base_chunk + f" and fullText contains '{kw}'"
                                else:
                                    query = (
                                        base_chunk
                                        + f" and (name contains '{kw}'"
                                        + f" or fullText contains '{kw}')"
                                    )

                                page_token = None
                                while True:
                                    kwargs = dict(
                                        q=query,
                                        pageSize=50,
                                        fields="nextPageToken, files(id, name, mimeType, "
                                               "size, modifiedTime, webViewLink, parents)",
                                        orderBy="modifiedTime desc"
                                    )
                                    if page_token:
                                        kwargs['pageToken'] = page_token
                                    resp  = service.files().list(**kwargs).execute()
                                    for f in resp.get('files', []):
                                        if f['id'] not in seen_ids:
                                            seen_ids.add(f['id'])
                                            files_dedup.append(f)
                                    page_token = resp.get('nextPageToken')
                                    if not page_token:
                                        break

                            if files_dedup:
                                mode_label = {
                                    "📄 Nama file":   "nama file",
                                    "📝 Isi dokumen": "isi dokumen",
                                    "🔎 Keduanya":    "nama file & isi dokumen",
                                }[search_mode]
                                n_folders = len(all_folder_ids)
                                folder_info = (
                                    f"(menelusuri {n_folders} folder"
                                    + (" & subfolder" if n_folders > 1 else "")
                                    + ")"
                                )
                                st.markdown(
                                    f"<p style='font-size:0.75rem;color:#27ae60;"
                                    f"margin-bottom:10px;'>✅ Ditemukan "
                                    f"<b>{len(files_dedup)}</b> file "
                                    f"berdasarkan <i>{mode_label}</i> "
                                    f"<span style='color:#aaa;'>{folder_info}</span></p>",
                                    unsafe_allow_html=True
                                )
                                MIME_ICONS = {
                                    'application/vnd.google-apps.spreadsheet': ('📊', 'Google Sheets'),
                                    'application/vnd.google-apps.document':    ('📝', 'Google Docs'),
                                    'application/vnd.google-apps.presentation':('📑', 'Google Slides'),
                                    'application/pdf':                          ('📄', 'PDF'),
                                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                                                                                ('📊', 'Excel'),
                                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                                                                                ('📝', 'Word'),
                                    'application/zip':                          ('🗜️', 'ZIP'),
                                    'application/octet-stream':                 ('📦', 'File'),
                                    'image/jpeg':                               ('🖼️', 'Gambar'),
                                    'image/png':                                ('🖼️', 'Gambar'),
                                }

                                # ── Tampilkan hasil sebagai tabel ringkasan di dashboard ──
                                rows_summary = []
                                for file in files_dedup:
                                    mime          = file.get('mimeType', '')
                                    ico, mime_lbl = MIME_ICONS.get(mime, ('📎', 'File'))
                                    size_b        = int(file.get('size', 0) or 0)
                                    size_s        = (
                                        f"{size_b/1_048_576:.1f} MB" if size_b > 1_048_576
                                        else f"{size_b/1024:.0f} KB" if size_b > 1024
                                        else f"{size_b} B"
                                    ) if size_b else "–"
                                    mod  = file.get('modifiedTime', '')[:10]
                                    link = file.get('webViewLink', '#')
                                    rows_summary.append({
                                        'Tipe': f"{ico} {mime_lbl}",
                                        'Nama File': file['name'],
                                        'Ukuran': size_s,
                                        'Diperbarui': mod,
                                        'Link': link,
                                    })

                                # Tabel ringkasan interaktif di dashboard
                                df_files = pd.DataFrame(rows_summary)

                                # Render sebagai HTML table dengan link klikabel
                                th_cells_p = "".join(
                                    f"<th style='background:#0b3327;color:#fff;font-size:0.72rem;"                                    f"padding:8px 10px;text-align:left;'>{c}</th>"
                                    for c in ['Tipe', 'Nama File', 'Ukuran', 'Diperbarui', 'Aksi']
                                )
                                tr_rows_p = ""
                                for ridx, row in df_files.iterrows():
                                    bg = "#ffffff" if ridx % 2 == 0 else "#f7fdf9"
                                    tr_rows_p += (
                                        f"<tr style='background:{bg};'>"                                        f"<td style='padding:7px 10px;font-size:0.72rem;color:#555;"                                        f"border-bottom:1px solid #eef2f0;white-space:nowrap;'>{row['Tipe']}</td>"                                        f"<td style='padding:7px 10px;font-size:0.72rem;color:#1a3a2a;"                                        f"border-bottom:1px solid #eef2f0;word-break:break-word;max-width:340px;'>"                                        f"{row['Nama File']}</td>"                                        f"<td style='padding:7px 10px;font-size:0.72rem;color:#555;"                                        f"border-bottom:1px solid #eef2f0;white-space:nowrap;'>{row['Ukuran']}</td>"                                        f"<td style='padding:7px 10px;font-size:0.72rem;color:#555;"                                        f"border-bottom:1px solid #eef2f0;white-space:nowrap;'>{row['Diperbarui']}</td>"                                        f"<td style='padding:7px 10px;border-bottom:1px solid #eef2f0;white-space:nowrap;'>"                                        f"<a href='{row['Link']}' target='_blank' "                                        f"style='font-size:0.7rem;background:#0b3327;color:#fff;"                                        f"padding:4px 10px;border-radius:5px;text-decoration:none;'>Buka ↗</a>"                                        f"</td></tr>"
                                    )
                                table_html_p = (
                                    "<div style='overflow:auto;border-radius:10px;"                                    "border:1px solid #dce8e2;margin-top:8px;'>"                                    "<table style='border-collapse:collapse;width:100%;'>"                                    f"<thead><tr>{th_cells_p}</tr></thead>"                                    f"<tbody>{tr_rows_p}</tbody>"                                    "</table></div>"
                                )
                                st.markdown(table_html_p, unsafe_allow_html=True)
                            else:
                                n_folders = len(all_folder_ids)
                                st.info(
                                    f"Tidak ada file yang cocok dengan kata kunci "
                                    f"**\"{drive_keyword}\"** "
                                    f"pada mode *{search_mode}* "
                                    f"(sudah ditelusuri {n_folders} folder & subfolder). "
                                    f"Coba kata kunci atau mode lain."
                                )
                    except ImportError:
                        st.error(
                            "Library `google-api-python-client` belum terinstall. "
                            "Jalankan: `pip install google-api-python-client`"
                        )
                    except Exception as drive_err:
                        st.error(f"Gagal mengakses Google Drive: {drive_err}")
            elif not pend_keyword.strip():
                st.markdown(
                    "<div style='text-align:center;padding:30px 20px;color:#aaa;'>"
                    "<div style='font-size:2rem;margin-bottom:8px;'>📂</div>"
                    "<div style='font-size:0.82rem;'>Masukkan kata kunci di atas untuk "
                    "melihat rekapitulasi dan file pendukung terkait.</div></div>",
                    unsafe_allow_html=True
                )

        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 6. ERROR HANDLER
# ============================================================
except Exception as e:
    st.error(f"⚠️  Terjadi error: {e}")
    st.markdown("""
<div style="background:#fff8f0;border:1px solid #f39c12;border-radius:10px;
     padding:18px 20px;margin-top:14px;">
  <b style="color:#b7760c;">Kemungkinan penyebab:</b>
  <ul style="margin:10px 0 0 0;color:#555;font-size:0.82rem;line-height:2;">
    <li>File <code>kunci_akses.json</code> tidak ada di folder yang sama dengan <code>app.py</code></li>
    <li>Service account belum diberi akses ke Google Spreadsheet</li>
    <li>Koneksi internet terputus</li>
    <li>URL spreadsheet berubah atau tidak bisa diakses</li>
  </ul>
</div>""", unsafe_allow_html=True)
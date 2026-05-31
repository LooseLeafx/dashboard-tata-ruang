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
from folium.plugins import MeasureControl, LocateControl

# ============================================================
# 0. FUNGSI HELPER - PERMANENT LAYER STORAGE (GITHUB API)
# ============================================================
import requests
import base64
import json
import os
import time
import hashlib
import tempfile

LAYERS_DIR = "layers"
LAYERS_METADATA_FILE = "layers_metadata.json"

def get_github_headers():
    """Mengambil header otentikasi GitHub dari Secrets"""
    token = st.secrets["github_config"]["token"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def get_github_api_url(file_path):
    """Membuat URL endpoint API GitHub"""
    owner = st.secrets["github_config"]["owner"]
    repo = st.secrets["github_config"]["repo"]
    return f"https://api.github.com/repos/{owner}/{repo}/contents/data_peta/{file_path}"

def get_github_raw_url(file_path):
    """Membuat URL file mentah untuk diunduh/dibaca"""
    owner = st.secrets["github_config"]["owner"]
    repo = st.secrets["github_config"]["repo"]
    branch = st.secrets["github_config"].get("branch", "main")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/data_peta/{file_path}"

def upload_to_github(file_path, file_content_bytes, commit_message):
    """Mengunggah (Commit) file ke GitHub via API"""
    url = get_github_api_url(file_path)
    headers = get_github_headers()
    branch = st.secrets["github_config"].get("branch", "main")
    
    # Cek apakah file sudah ada (untuk mengambil nilai SHA yang wajib untuk proses update)
    r_get = requests.get(url, headers=headers)
    sha = r_get.json().get("sha") if r_get.status_code == 200 else None
    
    # Convert file ke Base64 (Syarat GitHub API)
    content_b64 = base64.b64encode(file_content_bytes).decode("utf-8")
    
    data = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        data["sha"] = sha
        
    r_put = requests.put(url, headers=headers, json=data)
    return r_put.status_code in [200, 201]

def delete_from_github(file_path):
    """Menghapus file dari GitHub via API"""
    url = get_github_api_url(file_path)
    headers = get_github_headers()
    branch = st.secrets["github_config"].get("branch", "main")
    
    # Wajib ambil SHA dulu sebelum menghapus
    r_get = requests.get(url, headers=headers)
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")
        data = {"message": f"Delete {file_path} via Dashboard", "sha": sha, "branch": branch}
        r_del = requests.delete(url, headers=headers, json=data)
        return r_del.status_code == 200
    return False

def init_layers_storage():
    """Memastikan folder lokal sementara ada"""
    if not os.path.exists(LAYERS_DIR):
        os.makedirs(LAYERS_DIR)

def load_layers_from_storage():
    """Membaca daftar layer secara INSTAN lewat jalur VIP (GitHub API)"""
    import os
    import json
    
    try:
        import requests
        import base64
        import streamlit as st
        
        # 1. Ambil kunci rahasia VIP Anda
        token = st.secrets["github_config"]["token"]
        owner = st.secrets["github_config"]["owner"]
        repo = st.secrets["github_config"]["repo"]
        branch = st.secrets["github_config"]["branch"]
        
        # 2. Akses langsung ke gudang inti GitHub (API)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/data_peta/layers_metadata.json?ref={branch}"
        headers = {"Authorization": f"token {token}"}
        
        r = requests.get(api_url, headers=headers)
        
        # 3. Terjemahkan datanya (karena API mengirimnya dalam bentuk sandi Base64)
        if r.status_code == 200:
            content_b64 = r.json()["content"]
            content_str = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content_str)
            
    except Exception as e:
        pass
    
    # 4. Jika internet mati/gagal, coba baca file dari lokal laptop
    if os.path.exists("data_peta/layers_metadata.json"):
        try:
            with open("data_peta/layers_metadata.json", "r") as f:
                return json.load(f)
        except: 
            pass
            
    return []

def save_layers_to_storage(layers):
    """Menyimpan daftar layer ke file JSON lalu mengunggahnya ke GitHub"""
    # Simpan lokal dulu
    with open(LAYERS_METADATA_FILE, "w") as f:
        json.dump(layers, f, indent=2)
        
    # Upload ke GitHub
    json_bytes = json.dumps(layers, indent=2).encode('utf-8')
    try:
        upload_to_github(LAYERS_METADATA_FILE, json_bytes, "Update metadata layer peta")
    except Exception as e:
        st.error(f"Gagal sinkronisasi metadata ke GitHub: {e}")

def add_layer_to_storage(name, uploaded_file, color_config, file_type='kmz'):
    init_layers_storage()
    layers = load_layers_from_storage()
    existing_idx = next((i for i, l in enumerate(layers) if l['name'] == name), None)
    
    file_content = uploaded_file.read()
    file_id = hashlib.md5(name.encode()).hexdigest()[:8]
    filename = f"{file_id}_{int(time.time())}.{file_type}"

# --- Ekstrak Kolom & Kategori Atribut Peta ---
    import tempfile
    columns_list = []
    unique_vals = {} # Siapkan wadah untuk nilai kategori
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_type}') as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name
        gdf_tmp = read_layer_geodataframe(tmp_path, file_type)
        KML_SKIP = {'timestamp','begin','end','altitudemode','tessellate','extrude',
                    'visibility','draworder','icon','description','styleurl','snippet',
                    'lookat','camera','address','phonenumber','fid','objectid',
                    'shape_leng','shape_area','shape_le_1'}
        columns_list = [c for c in gdf_tmp.columns if c != 'geometry' and c.lower() not in KML_SKIP]
        
        # Tambahan: Ambil nilai unik dari setiap kolom (Maks 50 agar file tidak berat)
        for c in columns_list:
            uv = gdf_tmp[c].dropna().astype(str).unique().tolist()
            if len(uv) <= 50:
                unique_vals[c] = uv
    except:
        pass
    # ----------------------------------
    
    # Upload fisik file peta ke GitHub
    with st.spinner("Mengirim peta ke GitHub... (Tunggu sebentar)"):
        success = upload_to_github(filename, file_content, f"Upload layer peta: {name}")
    
    if success:
        entry = {
            'name': name,
            'filename': filename,
            'color_config': color_config,
            'visible': False,
            'type': file_type,
            'storage': 'github',
            'created_at': time.time(),
            'columns': columns_list,
            'unique_vals': unique_vals
        }
        
        # Hapus file lama di GitHub jika mengupdate
        if existing_idx is not None:
            old_layer = layers[existing_idx]
            if old_layer.get('storage') == 'github':
                delete_from_github(old_layer.get('filename'))
            layers[existing_idx] = entry
        else:
            layers.append(entry)
            
        save_layers_to_storage(layers)
        return entry
    else:
        st.error("Gagal mengunggah file ke GitHub.")
        return None

def delete_layer_from_storage(name):
    layers = load_layers_from_storage()
    existing = [l for l in layers if l['name'] == name]
    
    if existing:
        layer = existing[0]
        if layer.get('storage') == 'github':
            delete_from_github(layer.get('filename'))
        
        layers = [l for l in layers if l['name'] != name]
        save_layers_to_storage(layers)
        return True
    return False

def get_layer_file_path(layer):
    """Mendownload peta dari GitHub ke memori lokal sementara untuk ditampilkan"""
    if layer.get('storage') == 'github':
        raw_url = get_github_raw_url(layer.get('filename'))
        try:
            r = requests.get(raw_url)
            if r.status_code == 200:
                ext = 'zip' if layer.get('type') == 'shp' else layer.get('type', 'kmz')
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp:
                    tmp.write(r.content)
                    return tmp.name
        except Exception:
            return None
    return None


def read_layer_geodataframe(layer_path, layer_type):
    """Baca file layer menjadi GeoDataFrame.
    Mendukung dua format ArcMap KML/KMZ:
    - Format A (point):   <tr><td>KEY</td><td>VAL</td></tr>
    - Format B (polygon): <tr><th>K1</th><th>K2</th></tr>
                          <tr><td>V1</td><td>V2</td></tr>
    """
    import zipfile, tempfile, re
    ltype = layer_type or 'kmz'

    if ltype == 'geojson':
        return gpd.read_file(layer_path)

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

    # KML / KMZ
    fiona.drvsupport.supported_drivers['KML']    = 'rw'
    fiona.drvsupport.supported_drivers['LIBKML'] = 'rw'
    gdf = gpd.read_file(layer_path, driver='KML')

    if 'description' not in gdf.columns:
        return gdf

    descs = gdf['description'].fillna('')
    sample = str(descs.iloc[0]) if len(descs) > 0 else ''
    if not ('<td' in sample.lower() or '<th' in sample.lower()):
        return gdf

    def _strip(s):
        return re.sub(r'<[^>]+>', '', s).strip()

    def _parse(desc_str):
        s = str(desc_str)
        tr_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.I | re.S)
        if not tr_blocks:
            return {}
        # Deteksi Format B: baris pertama punya <th>
        first_ths = re.findall(r'<th[^>]*>(.*?)</th>', tr_blocks[0], re.I | re.S)
        if first_ths:
            # Format B: header di baris pertama, nilai di baris berikutnya
            headers = [_strip(h) for h in first_ths]
            result  = {}
            for tr in tr_blocks[1:]:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.I | re.S)
                for i, td in enumerate(tds):
                    if i < len(headers) and headers[i]:
                        result[headers[i]] = _strip(td)
            return result
        else:
            # Format A: setiap baris = KEY | VALUE
            result = {}
            for tr in tr_blocks:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.I | re.S)
                if len(tds) >= 2:
                    k = _strip(tds[0])
                    v = _strip(tds[1])
                    if k:
                        result[k] = v
            return result

    parsed = [_parse(d) for d in descs]
    if not any(parsed):
        return gdf

    df_attr = pd.DataFrame(parsed)
    gdf = gdf.drop(columns=['description'], errors='ignore')
    for col in df_attr.columns:
        if col not in gdf.columns:
            gdf[col] = df_attr[col].values
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
[data-testid="stSidebar"] .stExpander summary p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] p,
[data-testid="stSidebar"] [data-testid="stCheckbox"] span,
[data-testid="stSidebar"] [data-testid="stCheckbox"] div {
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

/* ── Lebar Popover (Melayang) ── */
[data-testid="stPopoverBody"] {
    min-width: 680px !important;
    max-width: 90vw !important;
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
    margin-top: 0px !important;
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
    lbl = str(label)[:80] + ("…" if len(str(label)) > 80 else "")
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
    Tampilkan semua item dalam container scrollable (tanpa paginasi next/prev).
    """
    if df_agg.empty:
        st.info("Data tidak tersedia.")
        return

    max_val = df_agg['Pagu Anggaran'].max() or 1
    html_items = ""
    for i, row in df_agg.iterrows():
        rank  = list(df_agg.index).index(i) + 1
        color = COLORS[(rank - 1 + color_offset) % len(COLORS)]
        html_items += bar_html(row[col_name], row['Pagu Anggaran'],
                               max_val, color, rank=rank)

    # 👇 BESAR GRAPHIC BOX
    # Misalnya: 400px (jika ingin lebih panjang) atau 250px (jika ingin lebih pendek)
    st.markdown(
        f"<div style='height:450px;overflow-y:auto;"
        f"padding-right:4px;'>{html_items}</div>",
        unsafe_allow_html=True
    )

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
    """Membaca session dari file agar login bertahan meski di-refresh"""
    try:
        session_file = get_session_file()
        if session_file.exists():
            with open(session_file, "r") as f:
                session_data = json.load(f)
            
            # Kembalikan data ke st.session_state
            st.session_state.logged_in = session_data.get("logged_in", False)
            st.session_state.username = session_data.get("username", None)
            st.session_state.login_time = session_data.get("login_time", None)
            st.session_state.last_activity_time = session_data.get("last_activity_time", None)
    except Exception as e:
        pass


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


@st.cache_data(ttl=300, show_spinner="Memuat referensi Pergub...")
def load_referensi_pergub():
    """Fungsi khusus untuk menarik data dari GSheet Referensi SRS Anda"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets"]
        sa_info = dict(st.secrets["gcp_service_account"])
        sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(sa_info, scope)
        client = gspread.authorize(creds)
        
        # ID GSheet yang Anda berikan
        sheet  = client.open_by_key("1WSYS1iv0_CXkDec5mZOgLKdy1HPu2Dw16uYt3MfYmng").sheet1
        raw    = sheet.get_all_values()
        
        # Asumsi baris pertama adalah Header
        df_ref = pd.DataFrame(raw[1:], columns=raw[0])
        return df_ref
    except Exception as e:
        return pd.DataFrame()

def evaluasi_kesesuaian_pergub(df_kegiatan, df_ref, c_srs):
    """Mengevaluasi kesesuaian berdasarkan keyword matching secara presisi F0dan transparan"""
    import re
    import pandas as pd
    hasil_eval = []
    
    # 1. Deteksi Kolom Referensi GSheet (Sangat Spesifik)
    ref_cols = df_ref.columns.tolist()
    c_ref_srs = next((c for c in ref_cols if 'satuan ruang strategis' in str(c).lower()), None)
    c_ref_kw  = next((c for c in ref_cols if 'keyword' in str(c).lower()), None)

    # 2. Deteksi Kolom Data Utama (Lebih kebal terhadap spasi tersembunyi di Excel)
    cols = df_kegiatan.columns.tolist()
    col_kegiatan = next((c for c in cols if 'kegiatan' in str(c).lower() and 'jenis' not in str(c).lower()), None)
    col_tolok = next((c for c in cols if 'tolok ukur' in str(c).lower() or 'kinerja' in str(c).lower()), None)
    
    for _, row in df_kegiatan.iterrows():
        srs_kegiatan = str(row.get(c_srs, "")).strip()
        
        # 3. Ekstrak Teks Utama secara paksa (Jika kosong, tulis 'KOSONG')
        teks_kegiatan = str(row[col_kegiatan]) if col_kegiatan and pd.notna(row[col_kegiatan]) else "KOSONG"
        teks_tolok = str(row[col_tolok]) if col_tolok and pd.notna(row[col_tolok]) else "KOSONG"
        
        # Gabungkan dan bersihkan teks utama (buang tanda baca)
        teks_gabungan = f"{teks_kegiatan} {teks_tolok}".lower()
        teks_bersih = re.sub(r'[^\w\s]', ' ', teks_gabungan)
        
        status = "Tidak Dievaluasi"
        skor = 0
        alasan = "-"
        
        if srs_kegiatan and srs_kegiatan.lower() != "non srs" and not df_ref.empty and c_ref_srs:
            # Ambil SRS pertama jika ada multi-SRS
            srs_target = [s.strip() for s in srs_kegiatan.split(',')][0]
            
            # Cari baris yang sesuai di GSheet Referensi
            ref_match = df_ref[df_ref[c_ref_srs].astype(str).str.contains(srs_target, case=False, na=False)]
            
            if not ref_match.empty:
                keywords_raw = ref_match[c_ref_kw].iloc[0] if c_ref_kw else ""
                
                # Ambil daftar keyword unik dari GSheet Referensi
                daftar_kw = list(set([k.strip().lower() for k in str(keywords_raw).split(',') if k.strip()]))
                
                if daftar_kw:
                    # Scan kecocokan keyword di dalam teks gabungan
                    matched = [kw for kw in daftar_kw if kw in teks_bersih]
                    
                    skor = (len(matched) / len(daftar_kw)) * 100
                    
                    if skor >= 70:
                        status = "Sangat Sesuai"
                    elif skor >= 30:
                        status = "Cukup Sesuai"
                    else:
                        status = "Tidak Sesuai"
                        
                    # Format output yang sangat transparan
                    alasan = (
                        f"📋 [TEKS DIEVALUASI]\n"
                        f"• Kegiatan: {teks_kegiatan}\n"
                        f"• Tolok Ukur: {teks_tolok}\n\n"
                        f"🔑 [KEYWORD REFERENSI]: {', '.join(daftar_kw)}\n\n"
                        f"✅ [HASIL PENCOCOKAN]: {len(matched)} dari {len(daftar_kw)} keyword unik ditemukan -> ({', '.join(matched) if matched else 'Tidak ada'}).\n\n"
                        f"🎯 [KESIMPULAN]: Skor {skor:.0f}%, {status}."
                    )
                else:
                    alasan = "⚠️ [Kesimpulan] Kolom Keyword di GSheet referensi kosong untuk SRS ini."
            else:
                alasan = f"⚠️ [Kesimpulan] SRS '{srs_target}' tidak ditemukan di GSheet referensi."
        
        hasil_eval.append({"Status Kesesuaian": status, "Skor Kesesuaian": skor, "Alasan Evaluasi": alasan})
        
    # Gabungkan kembali kolom hasil analisis ke DataFrame utama
    df_eval = pd.DataFrame(hasil_eval, index=df_kegiatan.index)
    df_hasil = df_kegiatan.copy()
    for col in df_eval.columns:
        df_hasil[col] = df_eval[col]
        
    return df_hasil

# ============================================================
# 5. APLIKASI UTAMA
# ============================================================
try:
    # ─────────────────────────────────────────────────────────
    # Initialize login state dengan session timeout tracking
    # ─────────────────────────────────────────────────────────
    initialize_session_state()
    
    # 1. Check if session has timed out (LAKUKAN SEBELUM ACTIVITY UPDATE)
    if check_session_timeout(timeout_seconds=3600):  # 1 hour = 3600 seconds
        st.warning("⏰ Sesi Anda telah berakhir karena tidak ada aktivitas selama 1 jam. Silakan login kembali.")
        # File session dihapus agar benar-benar logout
        try:
            get_session_file().unlink(missing_ok=True)
        except:
            pass
        st.rerun()
        
    # 2. Update activity timestamp (LAKUKAN JIKA BELUM TIMEOUT)
    if st.session_state.logged_in:
        update_activity()
    
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
            "Data Urusan Kesistimewaan Tata Ruang </div>",
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
                               SRS_KATEGORI,
                               placeholder="Semua")
                if C_SRS else []
            )

            # --- 1. TAMBAHKAN CHECKBOX EKSKLUSIF DI SINI ---
            is_global_eksklusif = False
            if C_SRS and sel_srs and len(sel_srs) > 0:
                is_global_eksklusif = st.checkbox(
                    "Eksklusif SRS Pilihan", 
                    help="Sembunyikan kegiatan multi-SRS dari seluruh grafik dan data"
                )
            # -----------------------------------------------

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
        if sel_srs and C_SRS:
            if is_global_eksklusif:
                # Jika dicentang eksklusif, buang yang multi-SRS
                df_f = df_f[df_f[C_SRS].apply(
                    lambda v: set(kategorisasi_srs(v)) == set(sel_srs)
                )]
            else:
                # Jika tidak dicentang, ambil semua yang memuat SRS tersebut
                df_f = df_f[df_f[C_SRS].apply(
                    lambda v: bool(set(kategorisasi_srs(v)) & set(sel_srs))
                )]

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

                if 'is_global_eksklusif' in locals() and is_global_eksklusif and sel_srs:
                    df_srs_rekap = df_srs_rekap[df_srs_rekap['SRS'].isin(sel_srs)]

                if not df_srs_rekap.empty:
                    srs_agg = df_srs_rekap.rename(
                        columns={'SRS': C_SRS, 'Total_Pagu': 'Pagu Anggaran'}
                    )
                    render_paged(srs_agg, C_SRS,
                                 color_offset=9, page_key="srs_page")
                else:
                    st.info("Data SRS tidak tersedia.")

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

            else:
                st.info("Kolom SRS tidak terdeteksi.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Tren Tahunan ──
        if C_TAHUN:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>Tren Pagu Anggaran per Tahun</div>",
                        unsafe_allow_html=True)

            # ── Comparison Mode toggle ──
            _cmp_on = st.toggle("🔀 Mode Perbandingan", key="comparison_mode",
                                help="Bandingkan data antar Tahun, SRS, atau OPD dalam satu grafik")

            yr = (
                df.groupby(C_TAHUN)[C_PAGU].sum()
                .reset_index()
                .sort_values(C_TAHUN)
            )
            # Pastikan tahun adalah integer untuk axis yang bersih
            try:
                yr[C_TAHUN] = yr[C_TAHUN].astype(int)
            except Exception:
                pass
            _tahun_vals = sorted(yr[C_TAHUN].unique().tolist())

            if _cmp_on:
                _cmp_by = st.selectbox(
                    "Bandingkan berdasarkan:",
                    options=[o for o in ["Tahun Anggaran", "SRS", "OPD", "Pelayanan", "Fokus"]
                             if (o != "Tahun Anggaran" or C_TAHUN)
                             and (o != "SRS" or C_SRS)
                             and (o != "OPD" or C_OPD)
                             and (o != "Pelayanan" or C_PELAYAN)
                             and (o != "Fokus" or C_FOKUS)],
                    key="cmp_by"
                )
                _cmp_col_map = {
                    "Tahun Anggaran": C_TAHUN,
                    "SRS": C_SRS,
                    "OPD": C_OPD,
                    "Pelayanan": C_PELAYAN,
                    "Fokus": C_FOKUS,
                }
                _cmp_col = _cmp_col_map.get(_cmp_by)
                # X axis: jika bandingkan tahun, pakai SRS atau OPD sebagai sumbu X
                # jika bandingkan dimensi lain, pakai tahun sebagai sumbu X
                if _cmp_by == "Tahun Anggaran":
                    _cmp_x = C_SRS or C_OPD or C_PELAYAN
                else:
                    _cmp_x = C_TAHUN or C_SRS or C_OPD

                if _cmp_col and _cmp_x:
                    _opts = sorted(df[_cmp_col].dropna().unique().tolist())
                    _sel_cmp = st.multiselect(
                        f"Pilih {_cmp_by} yang dibandingkan:",
                        _opts,
                        default=_opts[:min(3, len(_opts))],
                        key="cmp_sel"
                    )
                    if _sel_cmp:
                        fig_cmp = go.Figure()
                        for i, _val in enumerate(_sel_cmp):
                            _dfc = df[df[_cmp_col] == _val]
                            _grp = _dfc.groupby(_cmp_x)[C_PAGU].sum().reset_index().sort_values(_cmp_x)
                            fig_cmp.add_trace(go.Bar(
                                x=_grp[_cmp_x],
                                y=_grp[C_PAGU],
                                name=str(_val),
                                marker_color=COLORS[i % len(COLORS)],
                                text=[fmt_rp_full(v) for v in _grp[C_PAGU]],
                                textposition='outside',
                                hovertemplate=f"<b>{_val}</b><br>%{{x}}<br>%{{customdata}}<extra></extra>",
                                customdata=[fmt_rp_full(v) for v in _grp[C_PAGU]],
                            ))
                        fig_cmp.update_layout(
                            barmode='group',
                            height=280,
                            margin=dict(t=30, b=10, l=10, r=10),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                            yaxis=dict(showgrid=True, gridcolor='#eef2f0',
                                       showticklabels=False),
                            legend=dict(orientation='h', yanchor='bottom',
                                        y=1.02, xanchor='left', x=0),
                        )
                        st.plotly_chart(fig_cmp, use_container_width=True,
                                        config={'displayModeBar': False})
                    else:
                        st.info("Pilih minimal satu item untuk dibandingkan.")
                else:
                    st.info("Kolom yang diperlukan tidak tersedia.")
            else:
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
                    xaxis=dict(
                        showgrid=False,
                        tickfont=dict(size=11),
                        tickmode='array',
                        tickvals=_tahun_vals,
                        ticktext=[str(t) for t in _tahun_vals],
                        type='category',
                    ),
                    yaxis=dict(showgrid=True, gridcolor='#eef2f0',
                               showticklabels=False),
                    uniformtext_minsize=8,
                    uniformtext_mode='hide'
                )
                st.plotly_chart(fig_bar, use_container_width=True,
                                config={'displayModeBar': False})
            st.markdown("</div>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════
        # SMART INSIGHT
        # ══════════════════════════════════════════════════════════
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<div class='card-title'>💡 Smart Insight</div>",
                    unsafe_allow_html=True)

        def _hhi(series):
            """Hitung Herfindahl-Hirschman Index (0-1)."""
            total = series.sum()
            if total == 0:
                return 0
            shares = series / total
            return float((shares ** 2).sum())

        def _konsentrasi(hhi):
            if hhi > 0.25:  return "sangat terkonsentrasi"
            elif hhi > 0.15: return "cukup terkonsentrasi"
            elif hhi > 0.10: return "moderat"
            else:            return "terdistribusi merata"

        def _generate_insights(df, C_OPD, C_PELAYAN, C_FOKUS, C_SRS, C_TAHUN, C_PAGU, C_DAERAH,
                               sel_srs=None, sel_opd=None, sel_pelayan=None, sel_fokus=None):
            insights = []
            total = df[C_PAGU].sum()

            # 1. Insight OPD — skip jika filter OPD aktif
            if C_OPD and not sel_opd:
                opd_grp = df.groupby(C_OPD)[C_PAGU].sum().sort_values(ascending=False)
                hhi_opd = _hhi(opd_grp)
                top_opd = opd_grp.index[0] if len(opd_grp) > 0 else "-"
                top_pct = opd_grp.iloc[0] / total * 100 if total > 0 else 0
                insights.append({
                    "icon": "🏛️",
                    "judul": "Distribusi Anggaran antar OPD",
                    "teks": (
                        f"Distribusi anggaran antar OPD bersifat <b>{_konsentrasi(hhi_opd)}</b> "
                        f"(HHI: {hhi_opd:.3f}). OPD dengan alokasi tertinggi adalah "
                        f"<b>{top_opd}</b> ({top_pct:.1f}% dari total pagu). "
                        + ("Perlu evaluasi pemerataan peran antar OPD dalam penganggaran tata ruang."
                           if hhi_opd > 0.25 else
                           "Distribusi antar OPD sudah cukup proporsional.")
                    )
                })

            # 2. Insight SRS — skip jika filter SRS aktif
            if C_SRS and not sel_srs:
                srs_grp = df.groupby(C_SRS)[C_PAGU].sum().sort_values(ascending=False)
                hhi_srs = _hhi(srs_grp)
                top_srs = srs_grp.index[0] if len(srs_grp) > 0 else "-"
                top_srs_pct = srs_grp.iloc[0] / total * 100 if total > 0 else 0
                insights.append({
                    "icon": "🗺️",
                    "judul": "Distribusi Spasial per SRS",
                    "teks": (
                        f"Konsentrasi anggaran per Satuan Ruang Strategis bersifat "
                        f"<b>{_konsentrasi(hhi_srs)}</b> (HHI: {hhi_srs:.3f}). "
                        f"SRS dengan pagu tertinggi adalah <b>{top_srs}</b> "
                        f"({top_srs_pct:.1f}% dari total). "
                        + (f"Wilayah {top_srs} mendominasi alokasi — pertimbangkan pemerataan ke SRS lain."
                           if hhi_srs > 0.25 else
                           "Alokasi spasial antar SRS sudah cukup seimbang.")
                    )
                })

            # 3. Insight Pelayanan/Fokus — skip jika filter pelayanan/fokus aktif
            _col_pf = C_PELAYAN or C_FOKUS
            if _col_pf and not sel_pelayan and not sel_fokus:
                pf_grp = df.groupby(_col_pf)[C_PAGU].sum().sort_values(ascending=False)
                hhi_pf = _hhi(pf_grp)
                top_pf = pf_grp.index[0] if len(pf_grp) > 0 else "-"
                insights.append({
                    "icon": "🎯",
                    "judul": "Distribusi per Pelayanan/Fokus",
                    "teks": (
                        f"Berdasarkan kategori {_col_pf}, distribusi bersifat "
                        f"<b>{_konsentrasi(hhi_pf)}</b> (HHI: {hhi_pf:.3f}). "
                        f"Kategori dominan adalah <b>{top_pf}</b>. "
                        + ("Dominasi satu kategori dapat mengurangi cakupan layanan tata ruang secara menyeluruh."
                           if hhi_pf > 0.25 else
                           "Cakupan kategori layanan sudah cukup merata.")
                    )
                })

            # 4. Insight Tren
            if C_TAHUN:
                yr_grp = df.groupby(C_TAHUN)[C_PAGU].sum().sort_index()
                if len(yr_grp) >= 2:
                    thn_min = yr_grp.index[0]
                    thn_max = yr_grp.index[-1]
                    delta   = (yr_grp.iloc[-1] - yr_grp.iloc[0]) / yr_grp.iloc[0] * 100 if yr_grp.iloc[0] > 0 else 0
                    arah    = "meningkat" if delta > 0 else "menurun"
                    insights.append({
                        "icon": "📈",
                        "judul": "Tren Anggaran",
                        "teks": (
                            f"Pagu anggaran dari tahun <b>{thn_min}</b> ke <b>{thn_max}</b> "
                            f"<b>{arah} {abs(delta):.1f}%</b>. "
                            + ("Tren positif menunjukkan komitmen yang meningkat terhadap program tata ruang."
                               if delta > 0 else
                               "Tren menurun perlu dicermati untuk memastikan program tetap berjalan optimal.")
                        )
                    })

            # 5. Rata-rata & outlier
            if total > 0 and len(df) > 0:
                avg_pagu  = total / len(df)
                top10_pct = df.nlargest(10, C_PAGU)[C_PAGU].sum() / total * 100
                insights.append({
                    "icon": "📊",
                    "judul": "Distribusi Individual Kegiatan",
                    "teks": (
                        f"Rata-rata pagu per kegiatan adalah <b>{fmt_rp_full(avg_pagu)}</b>. "
                        f"10 kegiatan terbesar menyerap <b>{top10_pct:.1f}%</b> dari total anggaran. "
                        + ("Konsentrasi tinggi pada kegiatan besar — pertimbangkan distribusi ke kegiatan skala kecil-menengah."
                           if top10_pct > 50 else
                           "Distribusi kegiatan sudah cukup merata dari sisi skala.")
                    )
                })

            return insights

        with st.spinner("Menganalisis data..."):
            _insights = _generate_insights(
                df, C_OPD, C_PELAYAN, C_FOKUS, C_SRS, C_TAHUN, C_PAGU, C_DAERAH,
                sel_srs=sel_srs, sel_opd=sel_opd,
                sel_pelayan=sel_pelayan, sel_fokus=sel_fokus
            )

        for _ins in _insights:
            st.markdown(
                f"<div style='background:#f8fdf9;border-left:4px solid #27ae60;"
                f"border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:10px;'>"
                f"<div style='font-size:0.78rem;font-weight:700;color:#0b3327;"
                f"margin-bottom:4px;'>{_ins['icon']} {_ins['judul']}</div>"
                f"<div style='font-size:0.74rem;color:#2d5a3d;line-height:1.6;'>"
                f"{_ins['teks']}</div></div>",
                unsafe_allow_html=True
            )

        st.markdown("</div>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════
        # ANALISIS KESESUAIAN PERGUB
        # ══════════════════════════════════════════════════════════
        if C_SRS:
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-title'>⚖️ Analisis Kesesuaian Strategi Pengembangan Wilayah (Pergub)</div>", unsafe_allow_html=True)
            
            with st.spinner("Mencocokkan keyword dengan data referensi..."):
                df_ref_pergub = load_referensi_pergub()
                
                if not df_ref_pergub.empty:
                    # Jalankan evaluasi pada data aktif saat ini
                    df_evaluasi = evaluasi_kesesuaian_pergub(df, df_ref_pergub, C_SRS)
                    
                    # Buang yang "Tidak Dievaluasi" (seperti Non SRS)
                    df_valid_eval = df_evaluasi[df_evaluasi["Status Kesesuaian"] != "Tidak Dievaluasi"]
                    
                    if not df_valid_eval.empty:
                        # 1. SUMMARY
                        s_sangat = len(df_valid_eval[df_valid_eval["Status Kesesuaian"] == "Sangat Sesuai"])
                        s_cukup = len(df_valid_eval[df_valid_eval["Status Kesesuaian"] == "Cukup Sesuai"])
                        s_tidak = len(df_valid_eval[df_valid_eval["Status Kesesuaian"] == "Tidak Sesuai"])
                        
                        ec1, ec2, ec3 = st.columns(3)
                        with ec1:
                            st.markdown(f"<div style='background:#e8f5e9;padding:15px;border-radius:8px;border-left:4px solid #27ae60;'><div style='font-size:0.75rem;color:#2d5a3d;font-weight:bold;'>Sangat Sesuai</div><div style='font-size:1.6rem;color:#0b3327;font-weight:bold;'>{s_sangat} <span style='font-size:0.8rem;font-weight:normal;'>kegiatan</span></div></div>", unsafe_allow_html=True)
                        with ec2:
                            st.markdown(f"<div style='background:#fff8e1;padding:15px;border-radius:8px;border-left:4px solid #f39c12;'><div style='font-size:0.75rem;color:#7d5a00;font-weight:bold;'>Cukup Sesuai</div><div style='font-size:1.6rem;color:#0b3327;font-weight:bold;'>{s_cukup} <span style='font-size:0.8rem;font-weight:normal;'>kegiatan</span></div></div>", unsafe_allow_html=True)
                        with ec3:
                            st.markdown(f"<div style='background:#fdedec;padding:15px;border-radius:8px;border-left:4px solid #c0392b;'><div style='font-size:0.75rem;color:#78281f;font-weight:bold;'>Tidak Sesuai</div><div style='font-size:1.6rem;color:#0b3327;font-weight:bold;'>{s_tidak} <span style='font-size:0.8rem;font-weight:normal;'>kegiatan</span></div></div>", unsafe_allow_html=True)
                        
                        st.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)
                        
                        # 2. LEVEL DETAIL & ALASAN
                        st.markdown("<div style='font-size:0.8rem;font-weight:700;color:#0b3327;margin-bottom:10px;'>Detail Evaluasi per Kegiatan</div>", unsafe_allow_html=True)
                        
                        # Kolom yang akan ditampilkan (bisa disesuaikan dengan header excel Anda)
                        kolom_tampil = [c for c in ['Kegiatan/Subkegiatan', C_OPD, C_PAGU, 'Status Kesesuaian', 'Alasan Evaluasi'] if c in df_valid_eval.columns]
                        
                        st.dataframe(
                            df_valid_eval[kolom_tampil],
                            use_container_width=True,
                            hide_index=True,
                            height=300,
                            column_config={
                                "Status Kesesuaian": st.column_config.TextColumn("Status", width="small"),
                                "Alasan Evaluasi": st.column_config.TextColumn("Alasan (Scroll untuk baca lengkap)", width="large"),
                                C_PAGU: st.column_config.NumberColumn("Pagu", format="Rp %d") if C_PAGU in kolom_tampil else None
                            }
                        )
                    else:
                        st.info("Tidak ada kegiatan SRS yang dievaluasi pada filter saat ini.")
                else:
                    st.warning("⚠️ Data referensi Pergub kosong atau gagal ditarik dari Google Sheets. Pastikan Service Account sudah diberikan akses Viewer ke file GSheet tersebut.")
            st.markdown("</div>", unsafe_allow_html=True)       

        # ══════════════════════════════════════════════════════════
        # EXPORT PDF REPORT
        # ══════════════════════════════════════════════════════════
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        
        # Membagi baris untuk Judul dan Toggle
        _title_col, _toggle_col = st.columns([4, 1])
        with _title_col:
            st.markdown("<div class='card-title' style='margin-bottom:0;'>📄 Export Laporan PDF</div>",
                        unsafe_allow_html=True)
        with _toggle_col:
            tampilkan_export = st.toggle("Buka Menu", key="tgl_export")

        # Menu hanya akan dirender jika toggle diaktifkan
        if tampilkan_export:
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
            
            _pdf_col1, _pdf_col2 = st.columns([3, 1])
            with _pdf_col1:
                st.markdown(
                    "<div style='font-size:0.75rem;color:#7a9a8a;'>"
                    "Generate laporan formal rekapitulasi kegiatan dalam format HTML "
                    "yang siap dikonversi ke PDF (Ctrl+P → Simpan sebagai PDF di browser)."
                    "</div>",
                    unsafe_allow_html=True
                )
            with _pdf_col2:
                _logo_file = st.file_uploader("Logo Instansi (opsional)",
                                              type=['png','jpg','jpeg'],
                                              key="pdf_logo",
                                              label_visibility="collapsed")

            # Pengaturan tampilan PDF
            _set_c1, _set_c2, _set_c3 = st.columns(3)
            with _set_c1:
                _pdf_tema = st.selectbox("🎨 Tema Warna", ["Hijau", "Biru", "Merah"], key="pdf_tema")
            with _set_c2:
                _pdf_fontsize = st.selectbox("🔡 Ukuran Font", ["Kecil (10px)", "Normal (12px)", "Besar (14px)"], index=1, key="pdf_fontsize")
            with _set_c3:
                # Tambahan padding agar checkbox sejajar secara vertikal dengan dropdown
                st.markdown("<div style='padding-top: 28px;'>", unsafe_allow_html=True)
                _pdf_show_insight = st.checkbox("Sertakan Smart Insight", value=True, key="pdf_insight")
                st.markdown("</div>", unsafe_allow_html=True)

            if st.button("🖨️ Generate Laporan HTML", key="btn_gen_pdf",
                         use_container_width=True):
                import io as _io_pdf, base64 as _b64, datetime as _dt

                # Logo
                _logo_html = ""
                if _logo_file:
                    _logo_b64 = _b64.b64encode(_logo_file.read()).decode()
                    _logo_ext = _logo_file.name.split('.')[-1]
                    _logo_html = (
                        f"<img src='data:image/{_logo_ext};base64,{_logo_b64}' "
                        f"style='height:70px;object-fit:contain;margin-bottom:8px;' />"
                    )

                # Filter aktif
                _filter_aktif = []
                if sel_tahun:   _filter_aktif.append(f"Tahun: {', '.join(map(str,sel_tahun))}")
                if sel_srs:     _filter_aktif.append(f"SRS: {', '.join(sel_srs)}")
                if sel_opd:     _filter_aktif.append(f"OPD: {', '.join(sel_opd)}")
                _filter_str = " &nbsp;|&nbsp; ".join(_filter_aktif) if _filter_aktif else "Semua data"
                _tgl_gen    = _dt.datetime.now().strftime("%d %B %Y %H:%M")

                # Terapkan tema
                _tema_map = {
                    "Hijau":  {"header": "#0b3327", "accent": "#27ae60", "light": "#f0f9f4", "border": "#c8e6c9"},
                    "Biru":   {"header": "#0d2b4e", "accent": "#2980b9", "light": "#eaf4fb", "border": "#b3d7ee"},
                    "Merah":  {"header": "#4a0e0e", "accent": "#c0392b", "light": "#fdf0f0", "border": "#f5b7b1"},
                }
                _t = _tema_map.get(_pdf_tema, _tema_map["Hijau"])
                _fs_map = {"Kecil (10px)": "10px", "Normal (12px)": "12px", "Besar (14px)": "14px"}
                _fs = _fs_map.get(_pdf_fontsize, "12px")
                _fs_sm = {"10px": "9px", "12px": "10px", "14px": "12px"}[_fs]

                _ins_html = ""
                if _pdf_show_insight:
                    _t_light  = _t["light"]
                    _t_accent = _t["accent"]
                    for _ins in _insights[:3]:
                        _ins_html += (
                            f"<div style='background:{_t_light};border-left:3px solid {_t_accent};"
                            f"padding:8px 12px;margin-bottom:8px;border-radius:0 4px 4px 0;'>"
                            f"<b>{_ins['icon']} {_ins['judul']}</b><br>"
                            f"<span style='font-size:0.85em;'>{_ins['teks']}</span></div>"
                        )

                # Metrik
                _avg_pagu = df[C_PAGU].mean() if len(df) > 0 else 0
                _max_srs  = df.groupby(C_SRS)[C_PAGU].sum().idxmax() if C_SRS else "-"

                # Top 10 Pelayanan berdasarkan pagu
                _top10_pelayan = pd.DataFrame()
                if C_PELAYAN:
                    _top10_pelayan = (
                        df.groupby(C_PELAYAN)[C_PAGU].sum()
                        .sort_values(ascending=False)
                        .head(10)
                        .reset_index()
                    )
                    _top10_pelayan.columns = [C_PELAYAN, 'Total Pagu']
                    _top10_pelayan['Total Pagu'] = _top10_pelayan['Total Pagu'].apply(fmt_rp_full)

                _top10_th = "".join(
                    f"<th style='background:#0b3327;color:#fff;padding:7px 12px;"
                    f"text-align:left;font-size:0.8em;'>{c}</th>"
                    for c in (_top10_pelayan.columns if not _top10_pelayan.empty else [C_PELAYAN or 'Pelayanan', 'Total Pagu'])
                )
                _top10_tr = ""
                if not _top10_pelayan.empty:
                    for _ri2, _row2 in _top10_pelayan.iterrows():
                        _bg2 = "#ffffff" if _ri2 % 2 == 0 else "#f0f9f4"
                        _top10_tr += (
                            f"<tr style='background:{_bg2};'>" +
                            "".join(f"<td style='padding:6px 12px;font-size:0.8em;"
                                    f"border-bottom:1px solid #eee;'>{str(_row2[c])}</td>"
                                    for c in _top10_pelayan.columns) +
                            "</tr>"
                        )
                else:
                    _top10_tr = "<tr><td colspan='2' style='padding:8px;color:#999;'>Data tidak tersedia</td></tr>"

                # Analisis spasial otomatis — tabel SRS
                _srs_html_rows = ""
                if C_SRS:
                    _srs_g = df.groupby(C_SRS)[C_PAGU].sum().sort_values(ascending=False)
                    _srs_tot = _srs_g.sum()
                    for _sn, _sv in _srs_g.items():
                        _srs_pct = _sv / _srs_tot * 100 if _srs_tot > 0 else 0
                        _bar_w   = int(_srs_pct * 2)  # max 200px untuk 100%
                        _srs_html_rows += (
                            f"<tr>"
                            f"<td style='padding:5px 10px;font-size:0.78em;border-bottom:1px solid #eee;'>{_sn}</td>"
                            f"<td style='padding:5px 10px;font-size:0.78em;border-bottom:1px solid #eee;text-align:right;'>{fmt_rp_full(_sv)}</td>"
                            f"<td style='padding:5px 10px;border-bottom:1px solid #eee;'>"
                            f"<div style='background:#27ae60;height:10px;width:{_bar_w}px;border-radius:3px;display:inline-block;'></div>"
                            f" <span style='font-size:0.72em;color:#777;'>{_srs_pct:.1f}%</span></td>"
                            f"</tr>"
                        )

                # Distribusi OPD
                _opd_rows = ""
                if C_OPD:
                    _opd_g = df.groupby(C_OPD)[C_PAGU].sum().sort_values(ascending=False).head(10)
                    _tot_opd = _opd_g.sum()
                    for _on, _ov in _opd_g.items():
                        _pct_o = _ov / _tot_opd * 100 if _tot_opd > 0 else 0
                        _opd_rows += (
                            f"<tr><td style='padding:5px 10px;font-size:0.8em;"
                            f"border-bottom:1px solid #eee;'>{_on}</td>"
                            f"<td style='padding:5px 10px;font-size:0.8em;"
                            f"border-bottom:1px solid #eee;text-align:right;'>"
                            f"{fmt_rp_full(_ov)}</td>"
                            f"<td style='padding:5px 10px;font-size:0.8em;"
                            f"border-bottom:1px solid #eee;text-align:right;'>"
                            f"{_pct_o:.1f}%</td></tr>"
                        )

                _html_report = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>Laporan Rekapitulasi Kegiatan Tata Ruang</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; color: #1a1a1a;
          font-size: {_fs}; line-height: 1.5; background: #fff; padding: 20px; }}
  h3 {{ color: #0b3327; margin-top: 20px; margin-bottom: 10px; border-bottom: 2px solid #27ae60; padding-bottom: 5px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
</style>
</head>
<body>
    {_logo_html}
    <h2 style="color: #0b3327;">Laporan Rekapitulasi Kegiatan Tata Ruang</h2>
    <p style="font-size: {_fs_sm}; color: #555;">
        <b>Dibuat pada:</b> {_tgl_gen}<br>
        <b>Filter Aktif:</b> {_filter_str}
    </p>
    
    <div style="margin-bottom: 20px;">
        {_ins_html}
    </div>

    <h3>Top 10 Pagu per Pelayanan</h3>
    <table>
        <thead><tr>{_top10_th}</tr></thead>
        <tbody>{_top10_tr}</tbody>
    </table>

    <h3>Distribusi per Satuan Ruang Strategis (SRS)</h3>
    <table>
        <tbody>{_srs_html_rows}</tbody>
    </table>

    <h3>Distribusi per OPD</h3>
    <table>
        <tbody>{_opd_rows}</tbody>
    </table>
</body>
</html>"""

                _html_bytes = _html_report.encode('utf-8')
                st.download_button(
                    "⬇️ Download Laporan HTML (buka di browser → Ctrl+P → Simpan PDF)",
                    data=_html_bytes,
                    file_name=f"laporan_taru_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}.html",
                    mime="text/html",
                    key="dl_report_html"
                )
                st.success("✅ Laporan siap! Buka file HTML di browser lalu tekan Ctrl+P untuk simpan sebagai PDF.")

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

        # Memberi jarak kosong dari atas
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        # ── Tombol Popover Sejajar (Kiri - Kanan) ──
        btn_col1, btn_col2, _ = st.columns([1.5, 1.5, 4])
        
        pop_upload = btn_col1.popover("🗂️ Upload Peta", use_container_width=True)
        pop_buffer = btn_col2.popover("🛠️ Geoprocessing", use_container_width=True)

        with pop_upload:
            st.markdown(
                "<p style='font-size:0.78rem;color:#555;margin-bottom:10px;'>"
                "Upload file KMZ/KML/SHP."
                "Beri nama layer berdasarkan field <b>Name</b> pada file.</p>",
                unsafe_allow_html=True
            )

            # Baris 1: Nama Layer & Mode Warna (Diberi ruang lebih pas)
            up_col1, up_col2 = st.columns([2, 1.2])
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
            
            # Baris 2: File Uploader dibiarkan membentang penuh (Full Width)
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
                    lc1, lc2, lc3, lc4, lc5, lc6 = st.columns([2.5, 0.5, 0.8, 1.2, 1.8, 0.6])
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
                        if cc['mode'] == 'palette':
                            cols_tmp = layer.get('columns', [])
                            if cols_tmp:
                                cur_attr = cc.get('attribute', cols_tmp[0])
                                
                                # Bagi lc5 menjadi dua (dropdown dan tombol palet)
                                a_col, p_col = st.columns([3, 1])
                                with a_col:
                                    new_attr = st.selectbox("Atribut", cols_tmp, index=cols_tmp.index(cur_attr) if cur_attr in cols_tmp else 0, key="layer_attr_" + str(i), label_visibility="collapsed")
                                    if new_attr != cur_attr:
                                        st.session_state.extra_layers[i]['color_config']['attribute'] = new_attr
                                        save_layers_to_storage(st.session_state.extra_layers)
                                        st.rerun()
                                
                                with p_col:
                                    uv_dict = layer.get('unique_values', {})
                                    if cur_attr in uv_dict:
                                        with st.popover("🎨"):
                                            st.markdown("<b style='font-size:0.75rem;'>Warna per Kategori</b>", unsafe_allow_html=True)
                                            custom_cols = cc.get('custom_colors', {})
                                            pal_colors = PALETTES.get(cc.get('palette', 'Kategorikal'), PALETTES['Kategorikal'])
                                            
                                            updated = False
                                            for idx, val in enumerate(uv_dict[cur_attr]):
                                                val_str = str(val)
                                                default_c = pal_colors[idx % len(pal_colors)]
                                                current_c = custom_cols.get(val_str, default_c)
                                                new_c = st.color_picker(val_str, current_c, key=f"cp_{i}_{val_str}")
                                                if new_c != current_c:
                                                    custom_cols[val_str] = new_c
                                                    updated = True
                                            if updated:
                                                st.session_state.extra_layers[i]['color_config']['custom_colors'] = custom_cols
                                                save_layers_to_storage(st.session_state.extra_layers)
                                                st.rerun()
                            else:
                                st.markdown("<span style='font-size:0.7rem;color:#e74c3c;'>Re-upload</span>", unsafe_allow_html=True)
                    
                    with lc6:
                        if st.button("🗑️", key="del_layer_" + str(i), help="Hapus " + layer['name']):
                            delete_layer_from_storage(layer['name'])
                            st.session_state.extra_layers = load_layers_from_storage()
                            st.rerun()
            else:
                st.markdown(
                    "<p style='font-size:0.72rem;color:#aaa;font-style:italic;'>"
                    "Belum ada layer tambahan.</p>",
                    unsafe_allow_html=True
                )

        # ── Menu Geoprocessing (Buffer) di dalam Popover ──
        with pop_buffer:
            st.markdown("<p style='font-size:0.78rem;color:#555;'>Buat radius/buffer (dalam satuan meter)</p>", unsafe_allow_html=True)

            if st.session_state.extra_layers:
                layer_names = [l['name'] for l in st.session_state.extra_layers]

                buf_c1, buf_c2, buf_c3 = st.columns([2, 1, 1.2])
                with buf_c1:
                    sel_buf_layer = st.selectbox("Pilih Layer", layer_names, label_visibility="collapsed")
                with buf_c2:
                    buf_dist = st.number_input("Jarak (Meter)", min_value=1, value=50, step=10, label_visibility="collapsed")
                with buf_c3:
                    btn_do_buffer = st.button("🔄 Buat Buffer", use_container_width=True)

                if btn_do_buffer:
                    with st.spinner(f"Menghitung Buffer {buf_dist} meter..."):
                        target_layer = next(l for l in st.session_state.extra_layers if l['name'] == sel_buf_layer)
                        l_path = get_layer_file_path(target_layer)
                        if l_path:
                            try:
                                # 1. Baca data
                                gdf_target = read_layer_geodataframe(l_path, target_layer.get('type', 'kmz'))

                                # 2. Proses Buffer (Ubah ke meter -> buffer -> kembalikan ke koordinat GPS)
                                gdf_proj = gdf_target.to_crs(epsg=3857)
                                gdf_proj['geometry'] = gdf_proj.geometry.buffer(buf_dist)
                                gdf_final = gdf_proj.to_crs(epsg=4326)

                                # 3. Konversi ke GeoJSON Bytes
                                geojson_bytes = gdf_final.to_json().encode('utf-8')

                                # 4. Menyimpan hasil buffer sebagai layer baru
                                class MockFile:
                                    def read(self): return geojson_bytes
                                    @property
                                    def name(self): return "buffer.geojson"

                                new_name = f"Buffer {buf_dist}m - {sel_buf_layer}"
                                color_cfg = {"mode": "single", "color": "#3498db"} # Default biru

                                add_layer_to_storage(new_name, MockFile(), color_cfg, file_type='geojson')
                                st.session_state.extra_layers = load_layers_from_storage()
                                st.success(f"Layer '{new_name}' berhasil ditambahkan!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Gagal membuat buffer: {e}")
            else:
                st.info("Upload peta terlebih dahulu untuk menggunakan fitur Buffer.")

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
                    btn_search_loc = st.button("Cari", key="btn_search_loc", use_container_width=True)

                _bm = st.session_state.get("basemap_choice", "street")
                m_map = folium.Map(
                    location=map_location,
                    zoom_start=map_zoom,
                    tiles=None, # Kita atur tile-nya secara manual di bawah
                    max_zoom=22,
                    control_scale=True
                )

                # 1. Menambahkan fitur pengukur jarak dan luas (Penggaris)
                m_map.add_child(MeasureControl(
                    position='topleft', 
                    primary_length_unit='meters', 
                    primary_area_unit='sqmeters'
                ))

                # 2. Menambahkan fitur pencari lokasi saat ini (GPS)
                LocateControl(
                    auto_start=False, 
                    position='topleft'
                ).add_to(m_map)

                # 1. Tambahkan Basemap: Street (Default aktif)
                folium.TileLayer(
                    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                    attr="OpenStreetMap contributors",
                    name="Basemap: Street", 
                    control=True, 
                    show=True
                ).add_to(m_map)
                
                # 2. Tambahkan Basemap: Satelit (Opsional)
                folium.TileLayer(
                    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                    attr="Esri, Maxar, Earthstar Geographics",
                    name="Basemap: Satelit", 
                    control=True, 
                    show=False
                ).add_to(m_map)

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

                # 1. Buat kolom teks rupiahnya DULU sebelum peta digambar
                gdf_m['Pagu_Display'] = gdf_m['Pagu_Total'].apply(fmt_rp_full)

                # 2. Baru gambar petanya menggunakan data yang sudah lengkap
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

                # 3. Tempelkan informasi (tooltip) ke peta tersebut
                choropleth.geojson.add_child(
                    folium.features.GeoJsonTooltip(
                        fields=['Name', 'Pagu_Display', 'Jumlah_Kegiatan'],
                        aliases=['SRS:', 'Total Pagu:', 'Jumlah Kegiatan:'],
                        localize=False
                    )
                )

                gdf_m['Pagu_Display'] = gdf_m['Pagu_Total'].apply(fmt_rp_full)
                choropleth.geojson.add_child(
                    folium.features.GeoJsonTooltip(
                        fields=['Name', 'Pagu_Display', 'Jumlah_Kegiatan'],
                        aliases=['SRS:', 'Total Pagu:', 'Jumlah Kegiatan:'],
                        localize=False
                    )
                )

                # Sembunyikan legenda bawaan (hapus macro_element_div dari control)
                for key in list(choropleth._children.keys()):
                    if 'color_map' in key:
                        choropleth._children[key].render = lambda **kwargs: ""
                        break


                # Legenda kustom 5 kategori — toggle di dalam peta
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

                # --- TAMBAHAN: LEGENDA DINAMIS UNTUK LAYER EKSTRA ---
                for layer in st.session_state.extra_layers:
                    if layer['visible']: # Hanya masukkan legenda jika layer sedang nyala (👁️)
                        cc_l = layer.get('color_config', {'mode': 'single', 'color': '#e74c3c'})
                        legend_rows += f"<div class='taru-legend-title' style='margin-top:10px; border-top:1px solid #eee; padding-top:8px;'>{layer['name']}</div>"
                        
                        if cc_l['mode'] == 'single':
                            legend_rows += (
                                f"<div style='display:flex;align-items:center;gap:8px;'>"
                                f"<div style='background:{cc_l['color']};width:15px;height:15px;border-radius:3px;border:1px solid #ccc;flex-shrink:0;'></div>"
                                f"<div style='color:#555;font-size:0.7rem;'>Semua area</div></div>"
                            )
                        else:
                            attr = cc_l.get('attribute', 'Kategori')
                            custom_cols = cc_l.get('custom_colors', {})
                            uv_dict = layer.get('unique_values', {})
                            
                            if attr in uv_dict:
                                pal_colors = PALETTES.get(cc_l.get('palette', 'Kategorikal'), PALETTES['Kategorikal'])
                                for idx, val in enumerate(uv_dict[attr]):
                                    val_str = str(val)
                                    c = custom_cols.get(val_str, pal_colors[idx % len(pal_colors)])
                                    legend_rows += (
                                        f"<div style='display:flex;align-items:center;gap:8px;margin-top:3px;'>"
                                        f"<div style='background:{c};width:15px;height:15px;border-radius:3px;border:1px solid #ccc;flex-shrink:0;'></div>"
                                        f"<div style='color:#555;font-size:0.7rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:150px;' title='{val_str}'>{val_str}</div></div>"
                                    )
                # ------------------------------------

                # --- LEGENDA DINAMIS UNTUK LAYER EKSTRA ---
                legend_rows_extra = ""
                for layer in st.session_state.extra_layers:
                    # Buat ID unik dari nama layer (hapus spasi dan simbol)
                    safe_id = "".join([c for c in layer['name'] if c.isalnum()])
                    # Tentukan status tampil awal dari Popover
                    disp = "block" if layer['visible'] else "none"
                    
                    # Bungkus legenda per-layer dengan ID khusus
                    legend_rows_extra += f"<div id='leg_{safe_id}' style='display:{disp};'>"
                    legend_rows_extra += f"<div class='taru-legend-title' style='margin-top:10px; border-top:1px solid #eee; padding-top:8px;'>{layer['name']}</div>"
                    
                    cc_l = layer.get('color_config', {'mode': 'single', 'color': '#e74c3c'})
                    if cc_l['mode'] == 'single':
                        legend_rows_extra += (
                            f"<div style='display:flex;align-items:center;gap:8px;'>"
                            f"<div style='background:{cc_l['color']};width:15px;height:15px;border-radius:3px;border:1px solid #ccc;flex-shrink:0;'></div>"
                            f"<div style='color:#555;font-size:0.7rem;'>Semua area</div></div>"
                        )
                    else:
                        attr = cc_l.get('attribute', 'Kategori')
                        custom_cols = cc_l.get('custom_colors', {})
                        uv_dict = layer.get('unique_values', {})
                        
                        if attr in uv_dict:
                            pal_colors = PALETTES.get(cc_l.get('palette', 'Kategorikal'), PALETTES['Kategorikal'])
                            for idx, val in enumerate(uv_dict[attr]):
                                val_str = str(val)
                                c = custom_cols.get(val_str, pal_colors[idx % len(pal_colors)])
                                legend_rows_extra += (
                                    f"<div style='display:flex;align-items:center;gap:8px;margin-top:3px;'>"
                                    f"<div style='background:{c};width:15px;height:15px;border-radius:3px;border:1px solid #ccc;flex-shrink:0;'></div>"
                                    f"<div style='color:#555;font-size:0.7rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:150px;' title='{val_str}'>{val_str}</div></div>"
                                )
                    legend_rows_extra += "</div>"
                # ------------------------------------

                legend_html = (
                    "<style>"
                    ".taru-legend-ctrl {"
                    "position:absolute;bottom:30px;right:10px;z-index:1000;"
                    "font-family:Arial,sans-serif;}"
                    ".taru-legend-toggle {"
                    "background:white;border:2px solid rgba(0,0,0,0.2);"
                    "border-radius:6px;padding:5px 10px;cursor:pointer;"
                    "font-size:0.78rem;font-weight:600;color:#0b3327;"
                    "display:block;text-align:center;user-select:none;"
                    "box-shadow:0 1px 5px rgba(0,0,0,0.15);white-space:nowrap;}"
                    ".taru-legend-toggle:hover{background:#f4f4f4;}"
                    ".taru-legend-panel{"
                    "background:white;border:2px solid rgba(0,0,0,0.2);"
                    "border-radius:6px;padding:10px 14px;margin-top:4px;"
                    "box-shadow:0 1px 5px rgba(0,0,0,0.15);min-width:200px;display:none;}"
                    ".taru-legend-panel.open{display:block;}"
                    ".taru-legend-title{font-weight:700;color:#0b3327;"
                    "font-size:0.75rem;margin-bottom:8px;}"
                    "</style>"
                    "<div class='taru-legend-ctrl'>"
                    "<div class='taru-legend-panel' id='taruLegendPanel'>"
                    
                    # 1. Bungkus Legenda Pagu Utama agar bisa merespon klik
                    "<div id='leg_SebaranPaguperSRS'>"
                    "<div class='taru-legend-title'>Total Pagu Anggaran</div>"
                    + legend_rows +
                    "</div>"
                    
                    # 2. Masukkan Legenda Ekstra
                    + legend_rows_extra +
                    
                    "</div>"
                    "<div class='taru-legend-toggle' id='taruLegendToggle' onclick=\""
                    "var p=document.getElementById('taruLegendPanel');"
                    "var t=document.getElementById('taruLegendToggle');"
                    "if(p.classList.contains('open')){"
                    "p.classList.remove('open');t.textContent='▲ Legenda';"
                    "}else{p.classList.add('open');t.textContent='▼ Legenda';}"
                    "\">▲ Legenda</div>"
                    "</div>"
                    
                    # 3. JAVASCRIPT AJAIB: Menghubungkan klik peta dengan legenda
                    "<script>"
                    "document.addEventListener('DOMContentLoaded', function() {"
                    "  setTimeout(function() {"
                    "    var mapObj = null;"
                    "    for (var key in window.L._maps) {"
                    "      mapObj = window.L._maps[key];"
                    "      break;"
                    "    }"
                    "    if (mapObj) {"
                    "      mapObj.on('overlayadd', function(e) {"
                    "        var safeName = e.name.replace(/[^a-zA-Z0-9]/g, '');"
                    "        var leg = document.getElementById('leg_' + safeName);"
                    "        if(leg) leg.style.display = 'block';"
                    "      });"
                    "      mapObj.on('overlayremove', function(e) {"
                    "        var safeName = e.name.replace(/[^a-zA-Z0-9]/g, '');"
                    "        var leg = document.getElementById('leg_' + safeName);"
                    "        if(leg) leg.style.display = 'none';"
                    "      });"
                    "    }"
                    "  }, 1000);"
                    "});"
                    "</script>"
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
                            cat_col    = cc_l.get('attribute', 'Name' if 'Name' in gdf_layer.columns else (clean_cols[0] if clean_cols else None))
                            uniq_names = gdf_layer[cat_col].dropna().astype(str).unique().tolist() if cat_col else []
                            
                            # --- Baca Warna Custom yang disetting pengguna ---
                            custom_cols = cc_l.get('custom_colors', {})
                            cmap_cat   = {nm: custom_cols.get(nm, pal_colors[i % len(pal_colors)]) for i, nm in enumerate(uniq_names)}
                            clr        = pal_colors[0]
                        geom_types = gdf_layer.geometry.geom_type.dropna().unique()
                        is_point   = all(gt in ('Point', 'MultiPoint') for gt in geom_types)
                        is_line    = all(gt in ('LineString', 'MultiLineString') for gt in geom_types)

                        if is_point:
                            # ── Point: MarkerCluster dengan popup bersih ──
                            # disableClusteringAtZoom=16: zoom ≥16 marker
                            # langsung muncul tepat di koordinat aslinya
                            folium_color_map = {
                                '#e41a1c':'red','#d73027':'red','#377eb8':'blue',
                                '#2166ac':'blue','#4daf4a':'green','#1a9850':'green',
                                '#984ea3':'purple','#762a83':'purple','#ff7f00':'orange',
                                '#a65628':'beige','#f781bf':'pink','#252525':'black',
                                '#525252':'darkgray','#737373':'gray',
                            }
                            cluster = MarkerCluster(
                                name=lyr_name,
                                show=lyr_show,
                                options={
                                    'disableClusteringAtZoom': 16,
                                    'spiderfyOnMaxZoom': False,
                                    'maxClusterRadius': 60,
                                }
                            ).add_to(m_map)
                            for _, row in gdf_layer.iterrows():
                                geom = row.geometry
                                if geom is None:
                                    continue
                                pts = list(geom.geoms) if geom.geom_type == 'MultiPoint' else [geom]
                                pin_clr = cmap_cat.get(str(row.get(cat_col,'')), clr) if (cc_l['mode']=='palette' and cat_col) else clr
                                f_color = folium_color_map.get(pin_clr.lower(), 'red')
                                row_cols  = _row_clean_fields(row, clean_cols)
                                foto_col  = _detect_foto_col(row, row_cols)
                                popup_html = _build_popup_html(row, row_cols, foto_col, lyr_name, '')
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

                st_folium(m_map, use_container_width=True, height=620)


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

            # Jika filter SRS aktif, tampilkan hanya SRS yang dipilih
            if sel_srs:
                df_srs_rekap_peta = df_srs_rekap_peta[
                    df_srs_rekap_peta['SRS'].isin(sel_srs)
                ].copy()

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
                        # 1. Filter awal: ambil semua yang memuat SRS ini
                        _df_sel_base = df[
                            df[C_SRS].apply(lambda v: _sel_nm in kategorisasi_srs(v))
                        ].copy()

                        if not _df_sel_base.empty:
                            _k_full = f"show_full_{hash(_sel_nm)}"
                            _k_eks = f"eks_map_{hash(_sel_nm)}"
                            _is_full = st.session_state.get(_k_full, False)

                            _hdr1, _hdr_eks, _hdr2 = st.columns([4, 1.5, 1.5])
                            
                            with _hdr_eks:
                                st.markdown("<div style='padding-top: 8px;'>", unsafe_allow_html=True)
                                _is_eks = st.checkbox("Eksklusif 1 SRS", key=_k_eks, help="Sembunyikan kegiatan multi-SRS")
                                st.markdown("</div>", unsafe_allow_html=True)

                            # 2. Terapkan filter eksklusif jika dicentang
                            if _is_eks:
                                _df_sel = _df_sel_base[_df_sel_base[C_SRS].apply(
                                    lambda v: kategorisasi_srs(v) == [_sel_nm]
                                )].copy()
                            else:
                                _df_sel = _df_sel_base.copy()

                            _mode_label = "📋 Ringkas" if _is_full else "📄 Lihat Semua Kolom"
                            _pagu_total = _df_sel[C_PAGU].sum() if not _df_sel.empty else 0

                            with _hdr1:
                                st.markdown(
                                    f"<div style='margin:10px 0 5px;font-size:0.78rem;"
                                    f"font-weight:700;color:#0b3327;'>"
                                    f"Kegiatan di <span style='color:#27ae60;'>{_sel_nm}</span>"
                                    f" &nbsp;|&nbsp; {len(_df_sel):,} kegiatan"
                                    f" &nbsp;·&nbsp; {fmt_rp_full(_pagu_total)} total pagu</div>",
                                    unsafe_allow_html=True
                                )
                                
                            with _hdr2:
                                if st.button(_mode_label,
                                             key=f"btn_full_{hash(_sel_nm)}",
                                             use_container_width=True):
                                    st.session_state[_k_full] = not _is_full
                                    st.rerun()

                            # 3. Render tabel jika data tidak kosong setelah difilter eksklusif
                            if not _df_sel.empty:
                                _mini_cols = [c for c in [C_TAHUN, C_OPD, C_PELAYAN, C_PAGU] if c]
                                _all_cols  = list(_df_sel.columns)

                                # Pilih kolom sesuai mode
                                _cols_used = _all_cols if _is_full else _mini_cols
                                _df_show_tbl = _df_sel[_cols_used].copy()
                                if C_PAGU in _df_show_tbl.columns:
                                    _df_show_tbl[C_PAGU] = _df_show_tbl[C_PAGU].apply(fmt_rp_full)

                                _th_m = "".join(
                                    f"<th style='background:#0b3327;color:#fff;font-size:0.68rem;"
                                    f"padding:6px 10px;text-align:left;white-space:nowrap;'>{c}</th>"
                                    for c in _df_show_tbl.columns
                                )
                                _tr_m = ""
                                for _ri, _row in _df_show_tbl.iterrows():
                                    _bg = "#ffffff" if _ri % 2 == 0 else "#f7fdf9"
                                    _tds = "".join(
                                        f"<td style='padding:5px 10px;font-size:0.68rem;"
                                        f"color:#1a3a2a;border-bottom:1px solid #eef2f0;"
                                        f"word-break:break-word;max-width:200px;'>{str(_row[c])}</td>"
                                        for c in _df_show_tbl.columns
                                    )
                                    _tr_m += f"<tr style='background:{_bg};'>{_tds}</tr>"
                                st.markdown(
                                    f"<div style='overflow:auto;max-height:500px;"
                                    f"border-radius:8px;border:1px solid #dce8e2;margin-bottom:4px;'>"
                                    f"<table style='border-collapse:collapse;width:100%;'>"
                                    f"<thead><tr>{_th_m}</tr></thead>"
                                    f"<tbody>{_tr_m}</tbody></table></div>",
                                    unsafe_allow_html=True
                                )
                                if _is_full:
                                    import io as _io
                                    _buf = _io.BytesIO()
                                    _df_sel.to_excel(_buf, index=False, engine='openpyxl')
                                    st.download_button(
                                        f"⬇️ Export Excel — {_sel_nm}",
                                        data=_buf.getvalue(),
                                        file_name=f"data_{_sel_nm.replace(' ','_')}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_xl_{hash(_sel_nm)}"
                                    )
                            else:
                                st.info(f"Tidak ada kegiatan yang eksklusif HANYA di {_sel_nm} (semua kegiatan bersifat multi-SRS).")
                        else:
                            st.info(f"Tidak ada kegiatan yang tercatat di {_sel_nm}.")

        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    # TAB 3 · DATA LENGKAP
    # ══════════════════════════════════════════════════════════
    with tab_data:
        st.markdown("<div class='card'>", unsafe_allow_html=True)

        # 1. ── AMBIL INPUT PENCARIAN DULU ──
        _prefill_val = st.session_state.pop("data_search_prefill", "")
        
    # ── KOTAK PENCARIAN DENGAN TOMBOL ──
        col_input, col_btn = st.columns([4, 1])

        with col_input:
            search_q = st.text_input(
                "Cari",
                placeholder="Cari kata kunci (nama kegiatan, OPD, detail...)",
                key="data_search",
                label_visibility="collapsed",
                value=_prefill_val
            )

        with col_btn:
            tombol_cari = st.button("Cari", use_container_width=True)

        # 2. ── TERAPKAN FILTER PENCARIAN ──
        df_show = df.copy()
        if search_q:
            mask = df_show.apply(
                lambda col: col.astype(str).str.contains(
                    search_q, case=False, na=False)
            ).any(axis=1)
            df_show = df_show[mask]

        # 3. ── TAMPILKAN HEADER & TOMBOL EXPORT (Gunakan df_show) ──
        hdr1, hdr2 = st.columns([3, 1])
        
        with hdr1:
            st.markdown(
                f"<p style='font-size:0.69rem;color:#7a9a8a;margin:4px 0 8px;'>"
                f"Menampilkan {len(df_show):,} dari {len(df):,} data</p>",
                unsafe_allow_html=True
            )

        with hdr2:
            import io as _io3
            _buf3 = _io3.BytesIO()
            # PERBAIKAN: Gunakan df_show, bukan df
            df_show.to_excel(_buf3, index=False, engine='openpyxl') 
            st.download_button(
                "⬇️ Export Excel",
                data=_buf3.getvalue(),
                file_name=f"taru_istimewa_{search_q}.xlsx" if search_q else "taru_istimewa_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # 4. ── RENDER TABEL HTML ──
        df_display = df_show.copy()
        df_display['Pagu Anggaran'] = df_display['Pagu Anggaran'].apply(fmt_rp_full)

        # (Mulai dari sini ke bawah, kodenya sama persis dengan milik Anda)
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

        if 'col_widths_custom' not in st.session_state:
            st.session_state.col_widths_custom = col_widths_default.copy()

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

            if width_all != 100:
                for col in st.session_state.col_widths_custom:
                    st.session_state.col_widths_custom[col] = int(
                        col_widths_default[col] * (width_all / 100)
                    )

            st.markdown("<hr style='margin:8px 0;'>", unsafe_allow_html=True)

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

        col_widths = {col: f"{width}px" for col, width in st.session_state.col_widths_custom.items()}

        colgroup_html = "".join(
            f"<col style='width:{col_widths.get(c, '120px')};'>"
            for c in df_display.columns
        )

        th_cells = "".join(
            "<th style='position:sticky;top:0;background:#0b3327;color:#fff;"
            "font-size:0.72rem;font-weight:700;padding:8px 10px;text-align:left;"
            "width:" + col_widths.get(c, "120px") + ";'>" + c + "</th>"
            for c in df_display.columns
        )
        
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

                # Catatan multi-SRS jika relevan
                if C_SRS and pagu_double > 0:
                    st.markdown(
                        f"<div style='background:#fff8e1;border:1px solid #f39c12;"
                        f"border-radius:6px;padding:7px 12px;margin:6px 0;"
                        f"font-size:0.7rem;color:#7d5a00;'>"
                        f"ℹ️ <b>Catatan:</b> Total pagu SRS ({fmt_rp_full(total_pagu_srs)}) "
                        f"berbeda dari total keseluruhan ({fmt_rp_full(total_pagu_asli)}) "
                        f"karena terdapat {fmt_rp_full(pagu_double)} pagu dari kegiatan "
                        f"yang tercatat di lebih dari satu SRS (multi-SRS).</div>",
                        unsafe_allow_html=True
                    )

                # Toggle ringkas / semua kolom
                _k_pend_full  = "show_full_pend"
                _is_pend_full = st.session_state.get(_k_pend_full, False)
                _pend_mini_cols = [c for c in [C_TAHUN, C_OPD, C_PELAYAN, C_FOKUS, C_PAGU] if c]
                _pend_all_cols  = list(df_pend_filtered.columns)
                _pend_cols_used = _pend_all_cols if _is_pend_full else _pend_mini_cols
                _df_pend_tbl    = df_pend_filtered[_pend_cols_used].copy()
                if C_PAGU in _df_pend_tbl.columns:
                    _df_pend_tbl[C_PAGU] = _df_pend_tbl[C_PAGU].apply(fmt_rp_full)

                _ph1, _ph2 = st.columns([3, 1])
                with _ph2:
                    _pend_mode_lbl = "📋 Ringkas" if _is_pend_full else "📄 Semua Kolom"
                    if st.button(_pend_mode_lbl, key="btn_pend_full",
                                 use_container_width=True):
                        st.session_state[_k_pend_full] = not _is_pend_full
                        st.rerun()

                _th_pend = "".join(
                    f"<th style='background:#0b3327;color:#fff;font-size:0.7rem;"
                    f"padding:7px 10px;text-align:left;white-space:nowrap;'>{c}</th>"
                    for c in _df_pend_tbl.columns
                )
                _tr_pend = ""
                for _ri, _row in _df_pend_tbl.iterrows():
                    _bg = "#ffffff" if _ri % 2 == 0 else "#f7fdf9"
                    _tds = "".join(
                        f"<td style='padding:5px 10px;font-size:0.7rem;color:#1a3a2a;"
                        f"border-bottom:1px solid #eef2f0;word-break:break-word;"
                        f"max-width:240px;'>{str(_row[c])}</td>"
                        for c in _df_pend_tbl.columns
                    )
                    _tr_pend += f"<tr style='background:{_bg};'>{_tds}</tr>"
                st.markdown(
                    f"<div style='overflow:auto;max-height:420px;border-radius:8px;"
                    f"border:1px solid #dce8e2;margin-bottom:6px;'>"
                    f"<table style='border-collapse:collapse;width:100%;'>"
                    f"<thead><tr>{_th_pend}</tr></thead>"
                    f"<tbody>{_tr_pend}</tbody></table></div>",
                    unsafe_allow_html=True
                )
                if _is_pend_full:
                    import io as _io2
                    _buf2 = _io2.BytesIO()
                    df_pend_filtered.to_excel(_buf2, index=False, engine='openpyxl')
                    st.download_button(
                        f"⬇️ Export Excel — {kw_p}",
                        data=_buf2.getvalue(),
                        file_name=f"data_{kw_p.replace(' ','_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_xl_pend"
                    )

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
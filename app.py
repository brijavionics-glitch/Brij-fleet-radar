"""
Flight Tracker
Live tracking of our aircraft at Mumbai (BOM) and Delhi (DEL).

Tabs
1. Mumbai Plan   : upload the Mumbai schedule (photo, Excel, Word, PDF, CSV), check it, track it.
2. Delhi Plan    : same for Delhi.
3. Mumbai Live   : every arrival and departure of our aircraft at Mumbai.
4. Delhi Live    : same for Delhi.
5. Fleet         : where each aircraft is now, add or remove registrations.
6. Help          : how to use the app.

Data sources (all free, tried one after another):
  Schedules : Flightradar24 (no key) -> AeroDataBox (optional free key)
  Live      : adsb.lol -> airplanes.live -> adsb.fi (no key)
"""

import html
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

import pandas as pd
import requests
import streamlit as st

# --------------------------------------------------------------------------------------
# Basic settings
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="Flight Tracker", page_icon="✈️", layout="wide",
                   initial_sidebar_state="expanded")

IST = timezone(timedelta(hours=5, minutes=30))
DATA_FILE = "fleet_data.json"
DEFAULT_REGS = ["VT-ANC", "VT-ANP", "VT-ANT", "VT-ANZ", "VT-AWA",
                "VT-AWB", "VT-AWC", "VT-AWD", "VT-NAA", "VT-NAC"]
STATIONS = {"BOM": "Mumbai", "DEL": "Delhi"}
CITY = {
    "BOM": "Mumbai", "DEL": "Delhi", "LHR": "London", "DXB": "Dubai", "FRA": "Frankfurt",
    "HND": "Tokyo", "NRT": "Tokyo", "YYZ": "Toronto", "FCO": "Rome", "BLR": "Bengaluru",
    "MAA": "Chennai", "HYD": "Hyderabad", "CCU": "Kolkata", "COK": "Kochi", "AMD": "Ahmedabad",
    "GOI": "Goa", "JFK": "New York", "EWR": "Newark", "SFO": "San Francisco", "ORD": "Chicago",
    "IAD": "Washington", "SIN": "Singapore", "BKK": "Bangkok", "CDG": "Paris", "AMS": "Amsterdam",
    "ZRH": "Zurich", "VIE": "Vienna", "CPH": "Copenhagen", "MXP": "Milan", "BHX": "Birmingham",
    "LGW": "London Gatwick", "SYD": "Sydney", "MEL": "Melbourne", "DOH": "Doha", "AUH": "Abu Dhabi",
    "RUH": "Riyadh", "JED": "Jeddah", "KTM": "Kathmandu", "DAC": "Dhaka", "CMB": "Colombo",
    "MLE": "Male", "SVO": "Moscow", "ICN": "Seoul", "PVG": "Shanghai", "HKG": "Hong Kong",
    "MRU": "Mauritius", "NBO": "Nairobi", "JNB": "Johannesburg", "YVR": "Vancouver",
}
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}
REFRESH_OPTIONS = {"30 seconds": 30, "1 minute": 60, "2 minutes": 120, "5 minutes": 300}


def city(code):
    code = (code or "").upper()
    return f"{CITY.get(code, code)} ({code})" if code else "unknown"


def now_ist():
    return datetime.now(IST)


# --------------------------------------------------------------------------------------
# Look and feel
# --------------------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(1200px 600px at 10% -10%, #1b2a6b 0%, transparent 60%),
                     radial-gradient(900px 500px at 110% 10%, #4b1d6b 0%, transparent 55%),
                     #070b1a; }
.block-container { padding-top: 1.2rem; }
/* readable light text everywhere, even without the theme file */
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"] { color: #e6ecff; }
.stApp [data-testid="stCaptionContainer"] p { color: #9fb0e8; }
section[data-testid="stSidebar"] { background: #0d1330; }
/* menu buttons: all visible at once, wrap onto a second row on small phones */
.stApp [data-testid="stPills"] button, .stApp [data-testid="stButtonGroup"] button {
  border-radius: 12px; padding: 6px 14px; font-weight: 600; }
.stApp [data-testid="stBaseButton-pills"], .stApp [data-testid="stPills"] button {
  background: rgba(255,255,255,.08) !important; border: 1px solid rgba(255,255,255,.25) !important;
  color: #e6ecff !important; }
.stApp [data-testid="stBaseButton-pills"] p, .stApp [data-testid="stPills"] button p,
.stApp [data-testid="stPills"] button div { color: #e6ecff !important; }
.stApp [data-testid="stBaseButton-pillsActive"] {
  background: linear-gradient(90deg, #0891b2, #7c3aed) !important; border: 1px solid #67e8f9 !important; }
.stApp [data-testid="stBaseButton-pillsActive"] p,
.stApp [data-testid="stBaseButton-pillsActive"] div { color: #ffffff !important; }
/* MENU: light orange buttons, dark text; selected = strong orange, white text */
.st-key-menubox button, .st-key-menubox [data-testid^="stBaseButton-pills"],
[data-testid="stPills"] button {
  background: #fed7aa !important; background-color: #fed7aa !important;
  border: 1px solid #fb923c !important; border-radius: 12px !important; opacity: 1 !important; }
.st-key-menubox button *, [data-testid="stPills"] button * {
  color: #1c1917 !important; font-weight: 700 !important; opacity: 1 !important; }
.st-key-menubox button[kind="pillsActive"], .st-key-menubox [data-testid="stBaseButton-pillsActive"],
[data-testid="stPills"] button[kind="pillsActive"] {
  background: #f97316 !important; background-color: #f97316 !important; border: 2px solid #c2410c !important; }
.st-key-menubox button[kind="pillsActive"] *, .st-key-menubox [data-testid="stBaseButton-pillsActive"] *,
[data-testid="stPills"] button[kind="pillsActive"] * { color: #ffffff !important; font-weight: 800 !important; }
/* old tab styles kept harmless */
.stTabs [data-baseweb="tab-list"] { flex-wrap: wrap; gap: 6px 8px; overflow: visible !important; }
.stTabs [data-baseweb="tab-list"] button { padding: 6px 12px; border-radius: 12px;
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); }
.stTabs [data-baseweb="tab-list"] button p { color: #dfe6ff; font-weight: 600; font-size: .95rem; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
  background: linear-gradient(90deg, rgba(34,211,238,.35), rgba(168,85,247,.35)); border-color: #67e8f9; }
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] p { color: #ffffff; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
.hero { padding: 22px 26px; border-radius: 22px; margin-bottom: 14px;
        background: linear-gradient(120deg, rgba(34,211,238,.18), rgba(168,85,247,.18));
        border: 1px solid rgba(255,255,255,.10); box-shadow: 0 10px 40px rgba(0,0,0,.35); }
.hero h1 { margin: 0; font-size: 2.1rem; font-weight: 800; letter-spacing: .5px;
           background: linear-gradient(90deg,#67e8f9,#a78bfa,#f472b6);
           -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.hero p { margin: 4px 0 0 0; color: #b9c3ff; }
.clock { font-family: 'JetBrains Mono', monospace; color:#67e8f9; font-size: 1.05rem; }
.chips { margin-top: 10px; display:flex; flex-wrap:wrap; gap:8px; }
.chip { padding: 4px 10px; border-radius: 999px; font-size: .78rem; border:1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.05); color:#dfe6ff; }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
.ok { background:#22c55e; box-shadow:0 0 8px #22c55e; } .fail { background:#ef4444; box-shadow:0 0 8px #ef4444; }
.idle { background:#64748b; }
.kpis { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:12px; margin: 6px 0 16px 0; }
@media (max-width: 800px) { .kpis { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.kpi { border-radius:18px; padding:14px 16px; background: rgba(255,255,255,.05);
       border:1px solid rgba(255,255,255,.08); }
.kpi .n { font-size: 1.9rem; font-weight: 800; }
.kpi .l { color:#aab4e8; font-size:.85rem; }
.k-arr .n { color:#22d3ee; } .k-dep .n { color:#fbbf24; } .k-del .n { color:#f87171; } .k-air .n { color:#a78bfa; }
.sec { display:flex; align-items:center; gap:10px; margin: 18px 0 8px 0; font-weight:800; font-size:1.15rem; }
.sec .bar { width:6px; height:22px; border-radius:4px; }
.sec.arr .bar { background:#22d3ee; } .sec.dep .bar { background:#fbbf24; } .sec.alert .bar { background:#f87171; }
.sec.plan .bar { background:#a78bfa; }
html, body, .stApp, .block-container { overflow-x: hidden !important; max-width: 100vw; }
.block-container { padding-left: 1rem; padding-right: 1rem; }
.cards { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:10px; }
.fc { min-width:0; border-radius:16px; padding:12px 14px; background: rgba(255,255,255,.05);
      border:1px solid rgba(255,255,255,.09); border-left:5px solid #a78bfa; overflow-wrap:anywhere; }
.fc.arr { border-left-color:#22d3ee; } .fc.dep { border-left-color:#fbbf24; } .fc.plan { border-left-color:#a78bfa; }
.fc .top { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
.fc .top .reg { font-size:1.1rem; }
.fc .route { font-size:1.05rem; font-weight:700; margin-top:6px; color:#ffffff; }
.fc .city { color:#aab4e8; font-weight:400; font-size:.9rem; }
.fc .meta { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:6px; color:#aab4e8; font-size:.85rem; }
.fc .meta b { color:#eef2ff; font-family:'JetBrains Mono', monospace; }
.hero h1 { font-size: clamp(1.5rem, 6vw, 2.1rem); }
.tbl { width:100%; border-collapse: separate; border-spacing: 0 6px; font-size: .92rem; }
.tbl th { text-align:left; padding: 6px 10px; color:#9fb0ff; font-weight:600; font-size:.8rem;
          text-transform: uppercase; letter-spacing:.6px; }
.tbl td { padding: 10px; background: rgba(255,255,255,.045); color:#eef2ff; }
.tbl tr td:first-child { border-radius: 12px 0 0 12px; }
.tbl tr td:last-child { border-radius: 0 12px 12px 0; }
.tbl.arr tr td:first-child { border-left: 4px solid #22d3ee; }
.tbl.dep tr td:first-child { border-left: 4px solid #fbbf24; }
.tbl.plan tr td:first-child { border-left: 4px solid #a78bfa; }
.reg { font-family:'JetBrains Mono', monospace; font-weight:700; color:#fff; }
.mono { font-family:'JetBrains Mono', monospace; }
.b { padding: 3px 10px; border-radius:999px; font-size:.78rem; font-weight:700; white-space:nowrap; }
.b-good { background: rgba(34,197,94,.16); color:#4ade80; border:1px solid rgba(34,197,94,.35); }
.b-warn { background: rgba(251,191,36,.14); color:#fbbf24; border:1px solid rgba(251,191,36,.35); }
.b-bad  { background: rgba(239,68,68,.16); color:#f87171; border:1px solid rgba(239,68,68,.4); }
.b-info { background: rgba(34,211,238,.14); color:#67e8f9; border:1px solid rgba(34,211,238,.35); }
.b-new  { background: rgba(168,85,247,.16); color:#c4b5fd; border:1px solid rgba(168,85,247,.4); }
.b-grey { background: rgba(148,163,184,.12); color:#cbd5e1; border:1px solid rgba(148,163,184,.3); }
.alert { padding: 12px 16px; border-radius: 14px; margin-bottom: 8px; line-height:1.5;
         background: linear-gradient(90deg, rgba(239,68,68,.16), rgba(239,68,68,.04));
         border:1px solid rgba(239,68,68,.35); color:#ffe4e6; }
.alert.warn { background: linear-gradient(90deg, rgba(251,191,36,.16), rgba(251,191,36,.04));
              border-color: rgba(251,191,36,.35); color:#fff7d6; }
.alert.new { background: linear-gradient(90deg, rgba(168,85,247,.18), rgba(168,85,247,.04));
             border-color: rgba(168,85,247,.4); color:#f3e8ff; }
.okbox { padding: 12px 16px; border-radius: 14px; background: rgba(34,197,94,.10);
         border:1px solid rgba(34,197,94,.3); color:#dcfce7; }
.muted { color:#8b97c9; font-size:.85rem; }
.empty { padding: 18px; border-radius: 14px; text-align:center; color:#9aa6d6;
         background: rgba(255,255,255,.03); border:1px dashed rgba(255,255,255,.12); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------------------
# Storage (simple JSON file next to the app)
# --------------------------------------------------------------------------------------
def load_data():
    if "data" not in st.session_state:
        data = {"regs": DEFAULT_REGS.copy(), "plans": {}}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as fh:
                    data.update(json.load(fh))
            except Exception:
                pass
        st.session_state.data = data
    return st.session_state.data


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump(st.session_state.data, fh, indent=2)
    except Exception:
        pass


def secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Small cache shared by all users of the app (keeps the free sources happy)
# --------------------------------------------------------------------------------------
@st.cache_resource
def shared_store():
    return {"cache": {}, "health": {}, "sent": set()}


def set_health(source, ok, msg=""):
    shared_store()["health"][source] = (ok, now_ist(), msg)


def cache_get(key, ttl):
    item = shared_store()["cache"].get(key)
    if item and time.time() - item[0] < ttl:
        return item[1]
    return None


def cache_put(key, value):
    shared_store()["cache"][key] = (time.time(), value)


# --------------------------------------------------------------------------------------
# Cleaning helpers
# --------------------------------------------------------------------------------------
def fmt_reg(value):
    if value is None:
        return ""
    s = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    if s.startswith("VT") and len(s) == 5:
        return "VT-" + s[2:]
    return s


def fmt_flight(value):
    s = re.sub(r"[\s\-]+", "", str(value or "").upper())
    s = re.sub(r"^AIC(?=\d)", "AI", s)
    m = re.match(r"^([A-Z]{2}|[A-Z]\d|\d[A-Z])0*(\d{1,4})$", s)
    if m:
        return f"{m.group(1)}{int(m.group(2))}"
    return ""


def fmt_time(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, dtime):
        return value.strftime("%H:%M")
    s = str(value).strip().upper()
    if not s or s in ("NAN", "NONE", "NAT") or "X" in s:
        return ""
    m = re.search(r"(\d{1,2})[:.]?(\d{2})", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h < 24 and mi < 60:
            return f"{h:02d}:{mi:02d}"
    return ""


def sector_codes(value):
    return re.findall(r"[A-Z]{3}", str(value or "").upper())


MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def find_date(text):
    m = re.search(r"(\d{1,2})\s*[-/ ]?\s*(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s*[-/ ]?\s*(\d{4})",
                  str(text).upper())
    if m:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------------------
# Reading schedules (Excel, CSV, Word, PDF, photo)
# --------------------------------------------------------------------------------------
HEADER_RULES = [
    ("flight_arr", lambda h: "flight" in h and "arr" in h),
    ("flight_dep", lambda h: "flight" in h and "dep" in h),
    ("eta", lambda h: h.startswith("eta") or h.startswith("sta") or "arrival time" in h),
    ("etd", lambda h: h.startswith("etd") or h.startswith("std") or "departure time" in h),
    ("sector", lambda h: "sector" in h or "route" in h),
    ("reg", lambda h: "call sign" in h or "callsign" in h or "tail" in h or "registration" in h
     or h in ("reg", "a/c", "aircraft")),
]


def rows_from_table(table):
    """Find the header row in a table (list of rows) and read every aircraft row under it."""
    for i, row in enumerate(table):
        cells = [str(c if c is not None else "").strip().lower() for c in row]
        cmap = {}
        for j, h in enumerate(cells):
            for key, rule in HEADER_RULES:
                if key not in cmap and h and rule(h):
                    cmap[key] = j
                    break
        if "reg" not in cmap or not ("flight_arr" in cmap or "flight_dep" in cmap):
            continue
        out = []
        for r in table[i + 1:]:
            def get(k):
                idx = cmap.get(k)
                return r[idx] if idx is not None and idx < len(r) else None
            reg = fmt_reg(get("reg"))
            if not re.match(r"^[A-Z0-9]{1,2}-[A-Z0-9]{2,5}$", reg):
                continue
            out.append({
                "reg": reg,
                "sector": " ".join(sector_codes(get("sector"))),
                "eta": fmt_time(get("eta")),
                "etd": fmt_time(get("etd")),
                "flight_arr": fmt_flight(get("flight_arr")),
                "flight_dep": fmt_flight(get("flight_dep")),
            })
        if out:
            return out
    return []


FLIGHT_RE = r"\b(?:AIC|AI)\s?-?\s?\d{2,4}\b"


def close_match(value, known):
    """Fix small reading mistakes from photos, for example DEI to DEL or VT-AWO to VT-AWD."""
    if value in known:
        return value
    hits = [k for k in known if len(k) == len(value) and sum(a != b for a, b in zip(k, value)) <= 1]
    return hits[0] if len(hits) == 1 else value


def rows_from_text(text, station, known_regs=None):
    """Read schedule lines from plain text (used for photos and PDFs without tables)."""
    known_regs = known_regs or DEFAULT_REGS
    rows = []
    for line in str(text).splitlines():
        u = line.upper().replace("—", "-").replace("–", "-")
        m = re.search(r"V[TI1]\s*[-.]?\s*([A-Z0-9]{3})\b", u)
        if not m:
            continue
        reg = close_match("VT-" + m.group(1).replace("0", "O").replace("1", "I"), known_regs)
        rest = u[m.end():]
        flights = [fmt_flight(f) for f in re.findall(FLIGHT_RE, rest)]
        rest_nf = re.sub(FLIGHT_RE, " ", rest)
        seq = re.search(r"\b[A-Z]{3}(?:\s*[-> ]\s*[A-Z]{3}){1,3}\b", rest_nf)
        codes = [close_match(c, CITY) for c in sector_codes(seq.group(0))] if seq else []
        times = [fmt_time(t) for t in re.findall(r"\b\d{1,2}[:.]\d{2}\b|\b\d{4}\b", rest_nf)]
        times = [t for t in times if t]
        if station in codes:
            k = codes.index(station)
            has_arr, has_dep = k > 0, k < len(codes) - 1
        else:
            has_arr, has_dep = len(flights) >= 2, len(flights) >= 1
        fa = fd = eta = etd = ""
        if has_arr and has_dep:
            fa = flights[0] if flights else ""
            fd = flights[1] if len(flights) > 1 else ""
            eta = times[0] if times else ""
            etd = times[1] if len(times) > 1 else ""
        elif has_arr:
            fa = flights[0] if flights else ""
            eta = times[0] if times else ""
        elif has_dep:
            fd = flights[0] if flights else ""
            etd = times[0] if times else ""
        rows.append({"reg": reg, "sector": " ".join(codes), "eta": eta, "etd": etd,
                     "flight_arr": fa, "flight_dep": fd})
    return rows


def ocr_image(raw):
    from PIL import Image, ImageOps
    import pytesseract
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 2000:
        scale = 2000 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, config="--psm 6")


def read_schedule(uploaded, station, known_regs=None):
    """Returns (rows, plan_date or None, note)."""
    name = uploaded.name.lower()
    raw = uploaded.getvalue()
    tables, text = [], ""
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=object)
            for df in sheets.values():
                tbl = df.astype(object).where(pd.notna(df), None).values.tolist()
                tables.append(tbl)
                text += "\n".join(" ".join(str(c) for c in r if c is not None) for r in tbl[:6])
        elif name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), header=None, dtype=object)
            tables.append(df.astype(object).where(pd.notna(df), None).values.tolist())
        elif name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(raw))
            for t in doc.tables:
                tables.append([[c.text for c in row.cells] for row in t.rows])
            text = "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    for t in page.extract_tables() or []:
                        tables.append(t)
                    text += "\n" + (page.extract_text() or "")
        elif name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
            text = ocr_image(raw)
        else:
            text = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        return [], None, f"Could not read the file: {exc}"

    rows = []
    for t in tables:
        rows = rows_from_table(t)
        if rows:
            break
    note = "Read from the table in the file."
    if not rows:
        rows = rows_from_text(text, station, known_regs)
        note = ("Read from the text in the file. Photos are read by machine, so please check every row "
                "and fix any mistake before saving. Excel or Word files give the best result.")
    if not rows and tables:
        flat = "\n".join(" ".join(str(c) for c in r if c) for t in tables for r in t)
        rows = rows_from_text(flat, station, known_regs)
    return rows, find_date(text), note


def plan_movements(plan, station):
    """Turn plan rows into single arrival and departure movements."""
    moves = []
    for r in plan.get("rows", []):
        codes = sector_codes(r.get("sector"))
        k = codes.index(station) if station in codes else -1
        if r.get("flight_arr"):
            frm = codes[k - 1] if k > 0 else (codes[0] if codes and codes[0] != station else "")
            moves.append({"kind": "ARR", "reg": r["reg"], "flight": r["flight_arr"],
                          "time": r.get("eta", ""), "other": frm})
        if r.get("flight_dep"):
            to = codes[k + 1] if 0 <= k < len(codes) - 1 else (codes[-1] if codes and codes[-1] != station else "")
            moves.append({"kind": "DEP", "reg": r["reg"], "flight": r["flight_dep"],
                          "time": r.get("etd", ""), "other": to})
    return moves


# --------------------------------------------------------------------------------------
# Live data sources
# --------------------------------------------------------------------------------------
def http_json(url, params=None, headers=None, timeout=12):
    r = requests.get(url, params=params, headers=headers or UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def ts(v):
    try:
        return datetime.fromtimestamp(int(v), IST) if v else None
    except Exception:
        return None


def norm_fr24(it, fallback_reg=""):
    try:
        ident = it.get("identification") or {}
        number = fmt_flight((ident.get("number") or {}).get("default"))
        ac = it.get("aircraft") or {}
        reg = fmt_reg(ac.get("registration")) or fallback_reg
        ap = it.get("airport") or {}
        origin = (((ap.get("origin") or {}).get("code") or {}).get("iata")) or ""
        dest = (((ap.get("destination") or {}).get("code") or {}).get("iata")) or ""
        t = it.get("time") or {}
        sch, real, est = t.get("scheduled") or {}, t.get("real") or {}, t.get("estimated") or {}
        status = it.get("status") or {}
        return {
            "flight": number, "reg": reg, "origin": origin, "dest": dest,
            "sched_dep": ts(sch.get("departure")), "sched_arr": ts(sch.get("arrival")),
            "real_dep": ts(real.get("departure")), "real_arr": ts(real.get("arrival")),
            "est_dep": ts(est.get("departure")), "est_arr": ts(est.get("arrival")),
            "status_text": status.get("text") or "", "live": bool(status.get("live")),
            "source": "Flightradar24",
        }
    except Exception:
        return None


def fr24_list(query, fetch_by):
    j = http_json("https://api.flightradar24.com/common/v1/flight/list.json",
                  {"query": query.lower(), "fetchBy": fetch_by, "page": 1, "limit": 40})
    data = (((j.get("result") or {}).get("response") or {}).get("data")) or []
    fallback = fmt_reg(query) if fetch_by == "reg" else ""
    return [x for x in (norm_fr24(it, fallback) for it in data) if x]


def adb_time(node, key):
    v = ((node or {}).get(key) or {}).get("utc")
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(IST)
    except Exception:
        return None


def adb_list(search_by, value):
    key = secret("AERODATABOX_KEY")
    if not key:
        return None
    out = []
    for day in (now_ist().date(), now_ist().date() + timedelta(days=1)):
        url = f"https://aerodatabox.p.rapidapi.com/flights/{search_by}/{value}/{day.isoformat()}"
        hdr = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com"}
        r = requests.get(url, headers=hdr, timeout=15)
        if r.status_code == 204:
            continue
        r.raise_for_status()
        for it in r.json() or []:
            dep, arr = it.get("departure") or {}, it.get("arrival") or {}
            status = it.get("status") or ""
            out.append({
                "flight": fmt_flight(it.get("number")),
                "reg": fmt_reg((it.get("aircraft") or {}).get("reg")),
                "origin": ((dep.get("airport") or {}).get("iata")) or "",
                "dest": ((arr.get("airport") or {}).get("iata")) or "",
                "sched_dep": adb_time(dep, "scheduledTime"), "sched_arr": adb_time(arr, "scheduledTime"),
                "real_dep": adb_time(dep, "runwayTime"), "real_arr": adb_time(arr, "runwayTime"),
                "est_dep": adb_time(dep, "revisedTime"), "est_arr": adb_time(arr, "revisedTime"),
                "status_text": status, "live": status.lower() in ("departed", "enroute", "en route"),
                "source": "AeroDataBox",
            })
    return out


SCHEDULE_SOURCES = [
    ("Flightradar24", lambda by, v: fr24_list(v, "reg" if by == "reg" else "flight")),
    ("AeroDataBox", lambda by, v: adb_list("reg" if by == "reg" else "number", v)),
]


def fetch_schedule(by, value):
    """Try each schedule source in turn. Returns (flights, source name or '')."""
    for name, fn in SCHEDULE_SOURCES:
        try:
            res = fn(by, value)
            if res is None:            # source not set up (no key)
                continue
            set_health(name, True)
            if res:
                return res, name
        except Exception as exc:
            set_health(name, False, str(exc)[:80])
    return [], ""


LIVE_SOURCES = [
    ("adsb.lol", "https://api.adsb.lol/v2/reg/{reg}"),
    ("airplanes.live", "https://api.airplanes.live/v2/reg/{reg}"),
    ("adsb.fi", "https://opendata.adsb.fi/api/v2/registration/{reg}"),
]


def fetch_live_position(reg):
    """Try each free ADS-B network until one sees the aircraft."""
    answered = None
    for name, url in LIVE_SOURCES:
        try:
            j = http_json(url.format(reg=reg))
            set_health(name, True)
            ac = j.get("ac") or j.get("aircraft") or []
            if ac:
                a = ac[0]
                alt = a.get("alt_baro")
                return {"seen": True, "source": name, "flight": fmt_flight((a.get("flight") or "").strip()),
                        "on_ground": alt == "ground", "alt": alt if isinstance(alt, (int, float)) else 0,
                        "speed": a.get("gs") or 0, "lat": a.get("lat"), "lon": a.get("lon")}
            answered = name
        except Exception as exc:
            set_health(name, False, str(exc)[:80])
    return {"seen": False, "source": answered or ""}


def get_many(kind, keys, ttl):
    """Fetch many registrations or flight numbers in parallel with a short shared cache."""
    results, todo = {}, []
    for k in keys:
        hit = cache_get((kind, k), ttl)
        if hit is not None:
            results[k] = hit
        else:
            todo.append(k)
    if todo:
        if kind == "pos":
            worker = fetch_live_position
        else:
            def worker(k):
                return fetch_schedule("reg" if kind == "reg" else "flight", k)
        with ThreadPoolExecutor(max_workers=6) as ex:
            for k, val in zip(todo, ex.map(worker, todo)):
                results[k] = val
                cache_put((kind, k), val)
    return results


# --------------------------------------------------------------------------------------
# Status logic
# --------------------------------------------------------------------------------------
def times_for(f, kind):
    if kind == "ARR":
        return f["sched_arr"], f["real_arr"] or f["est_arr"], f["real_arr"]
    return f["sched_dep"], f["real_dep"] or f["est_dep"], f["real_dep"]


def status_of(f, kind):
    txt = (f.get("status_text") or "").lower()
    if "cancel" in txt:
        return "Cancelled", "b-bad", 0
    if "divert" in txt:
        return "Diverted", "b-bad", 0
    sched, exp, done = times_for(f, kind)
    delay = int((exp - sched).total_seconds() // 60) if exp and sched else 0
    if delay > 15:
        label, cls = f"Delayed {delay} min", ("b-warn" if delay < 60 else "b-bad")
    elif delay < -10:
        label, cls = f"Early {-delay} min", "b-good"
    else:
        label, cls = "On time", "b-good"
    if done:
        label = ("Landed · " if kind == "ARR" else "Departed · ") + label
    elif kind == "ARR" and f.get("real_dep"):
        label = "In the air · " + label
        cls = "b-info" if cls == "b-good" else cls
    return label, cls, delay


def hhmm(dt):
    return dt.strftime("%H:%M") if dt else "--:--"


def dmy(dt):
    return dt.strftime("%d %b") if dt else ""


def find_instance(flights, flight_no, station, kind, planned_dt):
    best, best_gap = None, None
    for f in flights:
        if f["flight"] != flight_no:
            continue
        if kind == "ARR" and f["dest"] != station:
            continue
        if kind == "DEP" and f["origin"] != station:
            continue
        ref = f["sched_arr"] if kind == "ARR" else f["sched_dep"]
        if not ref:
            continue
        gap = abs((ref - planned_dt).total_seconds())
        if gap <= 14 * 3600 and (best_gap is None or gap < best_gap):
            best, best_gap = f, gap
    return best


def check_plan(station, plan, regs, ttl):
    """Compare the saved plan with live data. Returns (rows for table, alerts)."""
    pdate = date.fromisoformat(plan["date"])
    moves = plan_movements(plan, station)
    flight_nos = sorted({m["flight"] for m in moves})
    by_flight = get_many("flight", flight_nos, ttl)
    by_reg = get_many("reg", regs, ttl)
    pool_from_regs = [f for fl, _ in by_reg.values() for f in fl]
    place = STATIONS.get(station, station)
    rows, alerts = [], []

    for m in moves:
        try:
            hh, mm = map(int, m["time"].split(":"))
            planned_dt = datetime.combine(pdate, dtime(hh, mm), IST)
        except Exception:
            planned_dt = datetime.combine(pdate, dtime(12, 0), IST)
        flights, src = by_flight.get(m["flight"], ([], ""))
        inst = find_instance(flights + pool_from_regs, m["flight"], station, m["kind"], planned_dt)
        row = {"m": m, "inst": inst, "check": ("Not found yet", "b-grey"), "status": ("", "b-grey")}
        if inst:
            label, cls, _ = status_of(inst, m["kind"])
            row["status"] = (label, cls)
            sched, exp, _ = times_for(inst, m["kind"])
            exp = exp or sched
            verb_in = m["kind"] == "ARR"
            other = city(m["other"] or (inst["origin"] if verb_in else inst["dest"]))
            if "cancel" in (inst.get("status_text") or "").lower():
                alerts.append(("bad", f"Flight {m['flight']} with {m['reg']} "
                                      f"{'coming to' if verb_in else 'going from'} {place} is cancelled."))
                row["check"] = ("Cancelled", "b-bad")
            elif inst["reg"] and inst["reg"] != m["reg"]:
                if verb_in:
                    txt = (f"Flight {m['flight']} was to come to {place} from {other} at {m['time']} "
                           f"with {m['reg']}. Now {inst['reg']} is coming at {hhmm(exp)}.")
                else:
                    txt = (f"Flight {m['flight']} was going from {place} to {other} at {m['time']} "
                           f"with {m['reg']}. Now {inst['reg']} is going at {hhmm(exp)}.")
                alerts.append(("bad", txt))
                row["check"] = ("Aircraft changed", "b-bad")
            elif exp and abs((exp - planned_dt).total_seconds()) > 30 * 60:
                txt = (f"{m['reg']} on flight {m['flight']} "
                       f"{'arriving' if verb_in else 'departing'} {place} was planned at {m['time']}. "
                       f"Now expected at {hhmm(exp)}.")
                alerts.append(("warn", txt))
                row["check"] = ("Time changed", "b-warn")
            else:
                row["check"] = ("Same as plan", "b-good")
        rows.append(row)

    planned_keys = {(m["flight"], m["kind"]) for m in moves}
    for reg, (fl, _) in by_reg.items():
        for f in fl:
            for kind in ("ARR", "DEP"):
                at = f["dest"] if kind == "ARR" else f["origin"]
                ref = f["sched_arr"] if kind == "ARR" else f["sched_dep"]
                if at != station or not ref or ref.date() != pdate:
                    continue
                if (f["flight"], kind) in planned_keys:
                    continue
                if kind == "ARR":
                    txt = (f"{reg} is coming to {place} from {city(f['origin'])} at {hhmm(ref)} "
                           f"by {f['flight']}. This is not in our plan.")
                else:
                    txt = (f"{reg} is going from {place} to {city(f['dest'])} at {hhmm(ref)} "
                           f"by {f['flight']}. This is not in our plan.")
                alerts.append(("new", txt))
    return rows, alerts


def build_board(station, regs, hours_back, hours_fwd, ttl, plan):
    now = now_ist()
    lo, hi = now - timedelta(hours=hours_back), now + timedelta(hours=hours_fwd)
    by_reg = get_many("reg", regs, ttl)
    planned = set()
    if plan:
        planned = {(m["reg"], m["flight"], m["kind"]) for m in plan_movements(plan, station)}
    arr, dep, seen = [], [], set()
    for reg, (fl, src) in by_reg.items():
        for f in fl:
            for kind in ("ARR", "DEP"):
                at = f["dest"] if kind == "ARR" else f["origin"]
                ref = f["sched_arr"] if kind == "ARR" else f["sched_dep"]
                if at != station or not ref or not (lo <= ref <= hi):
                    continue
                key = (f["flight"], kind, ref)
                if key in seen:
                    continue
                seen.add(key)
                label, cls, delay = status_of(f, kind)
                sched, exp, _ = times_for(f, kind)
                rec = {"reg": f["reg"] or reg, "flight": f["flight"], "date": dmy(ref),
                       "from": f["origin"], "to": f["dest"], "sched": hhmm(sched),
                       "exp": hhmm(exp) if exp else "", "label": label, "cls": cls, "delay": delay,
                       "ref": ref, "source": f.get("source", src),
                       "in_plan": None if not plan else ((f["reg"] or reg, f["flight"], kind) in planned)}
                (arr if kind == "ARR" else dep).append(rec)
    arr.sort(key=lambda r: r["ref"])
    dep.sort(key=lambda r: r["ref"])
    missing = [reg for reg, (fl, src) in by_reg.items() if not src]
    return arr, dep, missing


# --------------------------------------------------------------------------------------
# HTML pieces
# --------------------------------------------------------------------------------------
def badge(text, cls):
    return f'<span class="b {cls}">{html.escape(text)}</span>'


def section(title, kind):
    st.markdown(f'<div class="sec {kind}"><span class="bar"></span>{html.escape(title)}</div>',
                unsafe_allow_html=True)


def board_table(rows, kind, show_plan):
    if not rows:
        return '<div class="empty">No flights of our aircraft in this time window.</div>'
    out = ['<div class="cards">']
    for r in rows:
        other = r["from"] if kind == "arr" else r["to"]
        plan_b = ""
        if show_plan:
            plan_b = badge("In plan", "b-good") if r["in_plan"] else badge("Not in plan", "b-new")
        out.append(
            f'<div class="fc {kind}">'
            f'<div class="top"><span><span class="reg">{html.escape(r["reg"])}</span> '
            f'<span class="mono muted">{html.escape(r["flight"])}</span></span>{badge(r["label"], r["cls"])}</div>'
            f'<div class="route">{html.escape(r["from"])} → {html.escape(r["to"])} '
            f'<span class="city">{"from" if kind == "arr" else "to"} {html.escape(CITY.get(other, other))}</span></div>'
            f'<div class="meta"><span>{html.escape(r["date"])}</span>'
            f'<span>Sched <b>{r["sched"]}</b></span><span>Expected <b>{r["exp"] or "--:--"}</b></span>'
            f'{plan_b}<span class="muted">{html.escape(r["source"])}</span></div></div>')
    out.append("</div>")
    return "".join(out)


def kpi_html(items):
    return '<div class="kpis">' + "".join(
        f'<div class="kpi {c}"><div class="n">{n}</div><div class="l">{html.escape(l)}</div></div>'
        for n, l, c in items) + "</div>"


def alerts_html(alerts):
    if not alerts:
        return '<div class="okbox">All good. Every planned flight matches the live data so far.</div>'
    cls = {"bad": "alert", "warn": "alert warn", "new": "alert new"}
    return "".join(f'<div class="{cls[k]}">{i}. {html.escape(t)}</div>'
                   for i, (k, t) in enumerate(alerts, 1))


def notify(alerts, station):
    """Pop up new alerts once, and send them to Telegram if a bot is set up (free)."""
    store = shared_store()["sent"]
    seen = st.session_state.setdefault("toasted", set())
    new = []
    for kind, txt in alerts:
        key = (station, txt)
        if key not in seen:
            seen.add(key)
            st.toast(txt, icon="⚠️")
        if key not in store:
            store.add(key)
            new.append(txt)
    token, chat = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
    if new and token and chat:
        msg = f"{STATIONS.get(station, station)} changes:\n" + "\n".join(
            f"{i}. {t}" for i, t in enumerate(new, 1))
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": msg}, timeout=10)
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# Page parts
# --------------------------------------------------------------------------------------
data = load_data()

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    refresh_label = st.selectbox("Live update every", list(REFRESH_OPTIONS), index=1)
    refresh = REFRESH_OPTIONS[refresh_label]
    hours_back = st.slider("Show flights from the last (hours)", 0, 24, 6)
    hours_fwd = st.slider("Show flights for the next (hours)", 6, 48, 30)
    if st.button("🔄 Refresh now", use_container_width=True):
        shared_store()["cache"].clear()
        st.rerun()
    st.markdown("---")
    st.markdown("**Phone alerts**")
    if secret("TELEGRAM_BOT_TOKEN") and secret("TELEGRAM_CHAT_ID"):
        st.success("Telegram alerts are on")
    else:
        st.caption("Optional. Add a free Telegram bot in the app secrets to get changes on your phone.")
    st.caption("Extra schedule source: " + ("AeroDataBox on" if secret("AERODATABOX_KEY") else "AeroDataBox off (optional free key)"))

ttl = max(25, refresh - 5)


def hero():
    health = shared_store()["health"]
    chips = []
    for name in ["Flightradar24", "AeroDataBox", "adsb.lol", "airplanes.live", "adsb.fi"]:
        if name == "AeroDataBox" and not secret("AERODATABOX_KEY"):
            continue
        h = health.get(name)
        dot = "idle" if not h else ("ok" if h[0] else "fail")
        when = f" · {h[1].strftime('%H:%M:%S')}" if h else ""
        chips.append(f'<span class="chip"><span class="dot {dot}"></span>{name}{when}</span>')
    st.markdown(
        f'<div class="hero"><h1>✈️ Flight Tracker</h1>'
        f'<p>Live tracking of our aircraft at Mumbai and Delhi · '
        f'<span class="clock">{now_ist().strftime("%a %d %b %Y · %H:%M:%S")} IST</span> · '
        f'updates every {refresh_label}</p>'
        f'<div class="chips">{"".join(chips)}</div></div>', unsafe_allow_html=True)


st.fragment(run_every=refresh)(hero)()


def plan_tab(station):
    place = STATIONS[station]
    plans = data.setdefault("plans", {})
    st.markdown(f"#### Upload the {place} schedule")
    st.caption("Photo (JPG, PNG), Excel, Word, PDF or CSV. You can check and fix every row before saving.")
    up = st.file_uploader(f"{place} schedule", key=f"up_{station}", label_visibility="collapsed",
                          type=["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "xlsx", "xlsm", "xls",
                                "csv", "docx", "pdf", "txt"])
    if up is not None:
        sig = (up.name, up.size)
        if st.session_state.get(f"sig_{station}") != sig:
            with st.spinner("Reading the schedule..."):
                rows, found_date, note = read_schedule(up, station, data["regs"])
            st.session_state[f"sig_{station}"] = sig
            st.session_state[f"draft_{station}"] = rows
            st.session_state[f"draft_date_{station}"] = found_date
            st.session_state[f"note_{station}"] = note
        rows = st.session_state.get(f"draft_{station}", [])
        st.info(st.session_state.get(f"note_{station}", ""))
        default_date = st.session_state.get(f"draft_date_{station}") or (now_ist().date() + timedelta(days=1))
        if default_date.month != now_ist().month and abs((default_date - now_ist().date()).days) > 20:
            st.warning(f"The file says {default_date.strftime('%d %b %Y')}. That looks wrong, please pick the right date.")
            default_date = now_ist().date() + timedelta(days=1)
        pdate = st.date_input("Plan date", value=default_date, key=f"date_{station}")
        df = pd.DataFrame(rows or [{"reg": "", "sector": "", "eta": "", "etd": "", "flight_arr": "", "flight_dep": ""}],
                          columns=["reg", "sector", "eta", "etd", "flight_arr", "flight_dep"])
        edited = st.data_editor(
            df, num_rows="dynamic", use_container_width=True, key=f"ed_{station}",
            column_config={
                "reg": st.column_config.TextColumn("Aircraft", help="Example VT-ANC"),
                "sector": st.column_config.TextColumn("Sector", help="Example LHR BOM LHR"),
                "eta": st.column_config.TextColumn("ETA", help="Arrival time, example 05:15"),
                "etd": st.column_config.TextColumn("ETD", help="Departure time, example 08:40"),
                "flight_arr": st.column_config.TextColumn("Flight Arr", help="Example AI130"),
                "flight_dep": st.column_config.TextColumn("Flight Dep", help="Example AI131"),
            })
        if st.button(f"✅ Save and track this {place} plan", type="primary", key=f"save_{station}"):
            clean = []
            for r in edited.fillna("").to_dict("records"):
                reg = fmt_reg(r["reg"])
                if not reg:
                    continue
                clean.append({"reg": reg, "sector": " ".join(sector_codes(r["sector"])),
                              "eta": fmt_time(r["eta"]), "etd": fmt_time(r["etd"]),
                              "flight_arr": fmt_flight(r["flight_arr"]), "flight_dep": fmt_flight(r["flight_dep"])})
            plans[station] = {"date": pdate.isoformat(), "rows": clean, "saved": now_ist().isoformat()}
            for r in clean:
                if r["reg"] not in data["regs"]:
                    data["regs"].append(r["reg"])
            save_data()
            st.success(f"Saved {len(clean)} rows for {pdate.strftime('%d %b %Y')}. Tracking started.")

    plan = plans.get(station)
    if not plan:
        st.markdown('<div class="empty">No plan saved yet. Upload a schedule above.</div>', unsafe_allow_html=True)
        return

    def tracked():
        rows, alerts = check_plan(station, plan, data["regs"], ttl)
        notify(alerts, station)
        section(f"Changes against the plan · {date.fromisoformat(plan['date']).strftime('%d %b %Y')}", "alert")
        st.markdown(alerts_html(alerts), unsafe_allow_html=True)
        section("Plan with live status", "plan")
        out = ['<div class="cards">']
        for r in rows:
            m, inst = r["m"], r["inst"]
            is_arr = m["kind"] == "ARR"
            kind_b = badge("Arrival", "b-info") if is_arr else badge("Departure", "b-warn")
            live_reg = (inst or {}).get("reg") or "--"
            exp = "--:--"
            if inst:
                s_, e_, _ = times_for(inst, m["kind"])
                exp = hhmm(e_ or s_)
            other = CITY.get(m["other"], m["other"]) if m["other"] else "--"
            status_b = badge(*r["status"]) if r["status"][0] else ""
            out.append(
                f'<div class="fc {"arr" if is_arr else "dep"}">'
                f'<div class="top"><span><span class="reg">{m["reg"]}</span> '
                f'<span class="mono muted">{m["flight"]}</span></span>{kind_b}</div>'
                f'<div class="route">{"from" if is_arr else "to"} {html.escape(other)}</div>'
                f'<div class="meta"><span>Plan <b>{m["time"] or "--:--"}</b></span>'
                f'<span>Live aircraft <b>{html.escape(live_reg)}</b></span>'
                f'<span>Expected <b>{exp}</b></span></div>'
                f'<div class="meta">{badge(*r["check"])}{status_b}</div></div>')
        out.append("</div>")
        st.markdown("".join(out), unsafe_allow_html=True)
        st.caption(f"Last check {now_ist().strftime('%H:%M:%S')} IST. Not found yet means the free sources "
                   "do not show this flight yet (often more than a day ahead).")

    st.fragment(run_every=refresh)(tracked)()
    if st.button(f"🗑️ Delete the saved {place} plan", key=f"del_{station}"):
        plans.pop(station, None)
        save_data()
        st.rerun()


def live_tab(station):
    place = STATIONS[station]

    def board():
        plan = data.get("plans", {}).get(station)
        arr, dep, missing = build_board(station, data["regs"], hours_back, hours_fwd, ttl, plan)
        delayed = sum(1 for r in arr + dep if r["delay"] > 15 or r["cls"] == "b-bad")
        airborne = sum(1 for r in arr if r["label"].startswith("In the air"))
        st.markdown(kpi_html([(len(arr), f"Arrivals to {place}", "k-arr"),
                              (len(dep), f"Departures from {place}", "k-dep"),
                              (delayed, "Delayed or cancelled", "k-del"),
                              (airborne, f"In the air to {place}", "k-air")]), unsafe_allow_html=True)
        section(f"🛬 Arrivals to {place}", "arr")
        st.markdown(board_table(arr, "arr", bool(plan)), unsafe_allow_html=True)
        section(f"🛫 Departures from {place}", "dep")
        st.markdown(board_table(dep, "dep", bool(plan)), unsafe_allow_html=True)
        if missing:
            st.caption("No schedule data right now for: " + ", ".join(missing) +
                       ". The app keeps trying all sources every update.")
        st.caption(f"Last update {now_ist().strftime('%H:%M:%S')} IST · window {hours_back} h back, {hours_fwd} h ahead.")

    st.fragment(run_every=refresh)(board)()


def fleet_tab():
    section("Where is each aircraft now", "plan")

    def where():
        regs = data["regs"]
        pos = get_many("pos", regs, ttl)
        sched = get_many("reg", regs, ttl)
        now = now_ist()
        out = ['<div class="cards">']
        points = []
        for reg in regs:
            p = pos.get(reg) or {"seen": False, "source": ""}
            fl, _ = sched.get(reg, ([], ""))
            past = [f for f in fl if (f["real_dep"] or f["sched_dep"]) and (f["real_dep"] or f["sched_dep"]) <= now]
            fut = [f for f in fl if f["sched_dep"] and f["sched_dep"] > now and not f["real_dep"]]
            last = max(past, key=lambda f: f["real_dep"] or f["sched_dep"], default=None)
            nxt = min(fut, key=lambda f: f["sched_dep"], default=None)
            if p.get("seen") and not p.get("on_ground"):
                now_b = badge("Flying", "b-info")
                if p.get("lat") is not None and p.get("lon") is not None:
                    points.append({"lat": p["lat"], "lon": p["lon"]})
            elif p.get("seen"):
                now_b = badge("On ground", "b-good")
            elif last and last.get("real_dep") and not last.get("real_arr") and last.get("live"):
                now_b = badge("Flying", "b-info")
            else:
                now_b = badge("Not seen", "b-grey")
            def desc(f):
                if not f:
                    return "--"
                return (f'<span class="mono">{f["flight"]}</span> {f["origin"]} → {f["dest"]} '
                        f'<span class="muted">{dmy(f["sched_dep"])} {hhmm(f["sched_dep"])}</span>')
            flying = p.get("seen") and not p.get("on_ground")
            extra = (f'<span>Callsign <b>{p.get("flight") or "--"}</b></span>'
                     f'<span>Alt <b>{int(p.get("alt") or 0):,} ft</b></span>'
                     f'<span>Speed <b>{int(p.get("speed") or 0)} kt</b></span>') if flying else ""
            out.append(
                f'<div class="fc plan"><div class="top"><span class="reg">{reg}</span>{now_b}</div>'
                f'<div class="meta">{extra}</div>'
                f'<div class="meta"><span>Last: {desc(last)}</span></div>'
                f'<div class="meta"><span>Next: {desc(nxt)}</span></div>'
                f'<div class="meta"><span class="muted">{p.get("source") or ""}</span></div></div>')
        out.append("</div>")
        st.markdown("".join(out), unsafe_allow_html=True)
        if points:
            st.map(pd.DataFrame(points), size=20000, color="#22d3ee")
        st.caption(f"Last update {now_ist().strftime('%H:%M:%S')} IST.")

    st.fragment(run_every=refresh)(where)()

    section("Our aircraft list", "plan")
    st.markdown(" ".join(badge(r, "b-info") for r in data["regs"]), unsafe_allow_html=True)
    c1, c2 = st.columns([3, 1])
    new = c1.text_input("Add a new registration", placeholder="Example VT-AWE", label_visibility="collapsed")
    if c2.button("➕ Add aircraft", use_container_width=True):
        reg = fmt_reg(new)
        if not re.match(r"^[A-Z0-9]{1,2}-[A-Z0-9]{2,5}$", reg):
            st.error("Please type a registration like VT-AWE.")
        elif reg in data["regs"]:
            st.info(f"{reg} is already in the list.")
        else:
            data["regs"].append(reg)
            save_data()
            st.success(f"{reg} added. It is tracked from now on.")
            st.rerun()
    c3, c4 = st.columns([3, 1])
    remove = c3.multiselect("Remove aircraft", data["regs"], label_visibility="collapsed",
                            placeholder="Pick aircraft to remove")
    if c4.button("➖ Remove", use_container_width=True) and remove:
        data["regs"] = [r for r in data["regs"] if r not in remove]
        save_data()
        st.rerun()
    if st.button("↩️ Reset to the original 10 aircraft"):
        data["regs"] = DEFAULT_REGS.copy()
        save_data()
        st.rerun()


def help_tab():
    st.markdown("""
#### How to use
1. Open **Mumbai Plan**, upload the Mumbai schedule (photo, Excel, Word, PDF or CSV).
2. Check the rows, fix anything wrong, pick the plan date, press **Save and track**.
3. Do the same in **Delhi Plan**.
4. The plan tabs show every change in simple words: aircraft changed, time changed, cancelled, or one of our aircraft on a flight that is not in the plan.
5. **Mumbai Live** and **Delhi Live** show every arrival and departure of our aircraft, with delay status.
6. **Fleet** shows where each aircraft is now. Add new registrations at the bottom.

#### Colours
1. Blue line: arrival.
2. Yellow line: departure.
3. Green badge: on time.
4. Yellow badge: delayed less than 1 hour.
5. Red badge: delayed 1 hour or more, cancelled, or aircraft changed.
6. Purple badge: not in our plan.

#### Data sources
1. Flightradar24 gives the schedule, tail number and delays.
2. AeroDataBox is a backup schedule source. It needs a free key.
3. adsb.lol, airplanes.live and adsb.fi show where the aircraft is flying now.
4. If one source fails, the app moves to the next one by itself.
""")


VIEWS = {
    "Mumbai Live": lambda: live_tab("BOM"),
    "Delhi Live": lambda: live_tab("DEL"),
    "Mumbai Plan": lambda: plan_tab("BOM"),
    "Delhi Plan": lambda: plan_tab("DEL"),
    "Fleet": fleet_tab,
    "Help": help_tab,
}
with st.container(key="menubox"):
    choice = st.pills("Menu", list(VIEWS), selection_mode="single", default="Mumbai Live",
                      key="menu", label_visibility="collapsed")
VIEWS[choice or "Mumbai Live"]()

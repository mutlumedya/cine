#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import signal
import threading
import subprocess
import tempfile
import hashlib
import sqlite3
from datetime import datetime
import platform

print("[BASLANGIC] Bot baslatiliyor...")

# ============================================================
# TELEGRAM BOT IMPORT
# ============================================================

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    print("[TELEGRAM] python-telegram-bot yuklu!")
except ImportError as e:
    print(f"[TELEGRAM] Import hatasi: {e}")
    print("[TELEGRAM] python-telegram-bot kuruluyor...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "python-telegram-bot==20.7"], capture_output=True)
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    print("[TELEGRAM] python-telegram-bot kuruldu!")

# ============================================================
# FFMPEG KONTROL - BASIT
# ============================================================

def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5, check=True)
        return True
    except:
        return False

if not check_ffmpeg():
    print("[FFMPEG] FFmpeg bulunamadi! sudo apt install ffmpeg -y")
    sys.exit(1)
else:
    print("[FFMPEG] FFmpeg bulundu!")

# ============================================================
# REQUESTS KONTROL - BASIT
# ============================================================

try:
    import requests
except:
    print("[REQUESTS] Requests kuruluyor...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "requests"], capture_output=True)
    import requests

# ============================================================
# VERITABANI - BASIT
# ============================================================

DB_FILE = "yayin_bot.db"

def init_db():
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            registered_at TEXT
        )''')
        
        c.execute('''CREATE TABLE streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stream_name TEXT,
            stream_key TEXT,
            m3u_url TEXT,
            logo_url TEXT,
            price INTEGER,
            is_active INTEGER DEFAULT 0,
            is_paid INTEGER DEFAULT 0,
            created_at TEXT,
            paid_at TEXT
        )''')
        
        c.execute('''CREATE TABLE stream_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stream_name TEXT,
            stream_key TEXT,
            m3u_url TEXT,
            logo_url TEXT,
            stream_count INTEGER,
            total_price INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )''')
        
        c.execute('''CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stream_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            created_at TEXT,
            approved_at TEXT
        )''')
        
        c.execute('''CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        admin_id = os.environ.get('ADMIN_ID', '7092798502')
        c.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin, registered_at) VALUES (?, ?, ?, ?)",
                  (int(admin_id), 'admin', 1, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        print("[DB] Veritabani hazir!")
        return True
    except Exception as e:
        print(f"[DB] Hata: {e}")
        return False

if not init_db():
    print("[DB] Veritabani olusturulamadi!")
    sys.exit(1)

# ============================================================
# YAYIN MOTORU - OPTIMIZE
# ============================================================

class StreamEngine:
    def __init__(self):
        self.processes = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.restart_delay = 2
        print("[ENGINE] Stream Engine baslatildi!")
    
    def start_stream(self, stream_id, stream_key, m3u_url, logo_url=None):
        if stream_id in self.processes:
            self.stop_stream(stream_id)
        
        def run():
            while not self.stop_event.is_set():
                try:
                    print(f"[STREAM {stream_id}] Baslatiliyor...")
                    
                    response = requests.get(m3u_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                    content = response.text
                    lines = [x.strip() for x in content.splitlines() if x.strip()]
                    
                    videos = []
                    title = None
                    for line in lines:
                        if line.startswith("#EXTINF"):
                            if "," in line:
                                title = line.split(",", 1)[1].strip()
                            else:
                                title = "Film"
                            continue
                        if line.startswith("#"):
                            continue
                        if line.startswith(("http://", "https://")):
                            if '.mp4' in line or '.m3u8' in line:
                                videos.append({"title": title or "Film", "url": line})
                            title = None
                    
                    if not videos:
                        print(f"[STREAM {stream_id}] M3U bos, 30 sn bekleniyor...")
                        time.sleep(30)
                        continue
                    
                    print(f"[STREAM {stream_id}] {len(videos)} video bulundu.")
                    rtmp_url = f"rtmp://ssh101.bozztv.com:1935/ssh101/{stream_key}"
                    
                    logo_path = None
                    if logo_url:
                        try:
                            logo_hash = hashlib.md5(logo_url.encode()).hexdigest()
                            logo_path = os.path.join(tempfile.gettempdir(), f"logo_{logo_hash}.png")
                            if not os.path.isfile(logo_path):
                                response = requests.get(logo_url, timeout=20)
                                with open(logo_path, 'wb') as f:
                                    f.write(response.content)
                        except:
                            pass
                    
                    video_index = 0
                    while not self.stop_event.is_set() and stream_id in self.processes:
                        video = videos[video_index % len(videos)]
                        video_index += 1
                        
                        cmd = [
                            "ffmpeg", "-re", "-stream_loop", "-1",
                            "-i", video['url'],
                            "-c:v", "libx264", "-preset", "ultrafast",
                            "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                            "-b:v", "2000k",
                            "-maxrate", "2500k",
                            "-bufsize", "5000k",
                            "-g", "60",
                            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                            "-f", "flv", rtmp_url
                        ]
                        
                        if logo_path and os.path.isfile(logo_path):
                            cmd = [
                                "ffmpeg", "-re", "-stream_loop", "-1",
                                "-i", video['url'],
                                "-loop", "1", "-i", logo_path,
                                "-filter_complex", "[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black[base];[1:v]scale=150:-1[logo];[base][logo]overlay=W-w-15:15[v]",
                                "-map", "[v]", "-map", "0:a?",
                                "-c:v", "libx264", "-preset", "ultrafast",
                                "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                                "-b:v", "2000k",
                                "-maxrate", "2500k",
                                "-bufsize", "5000k",
                                "-g", "60",
                                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                                "-f", "flv", rtmp_url
                            ]
                        
                        print(f"[STREAM {stream_id}] Oynatiliyor: {video['title'][:30]}...")
                        
                        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        with self.lock:
                            if stream_id in self.processes:
                                self.processes[stream_id]['process'] = process
                        
                        while stream_id in self.processes:
                            if self.stop_event.is_set():
                                process.terminate()
                                try:
                                    process.wait(timeout=3)
                                except:
                                    process.kill()
                                return
                            
                            code = process.poll()
                            if code is not None:
                                if code == 0:
                                    print(f"[STREAM {stream_id}] Video bitti, siradaki...")
                                else:
                                    print(f"[STREAM {stream_id}] FFmpeg hata: {code}, yeniden basliyor...")
                                break
                            time.sleep(1)
                        
                        time.sleep(1)
                    
                    if stream_id not in self.processes:
                        break
                    
                    print(f"[STREAM {stream_id}] Liste bitti, bastan basliyor...")
                    time.sleep(2)
                    
                except Exception as e:
                    print(f"[STREAM {stream_id}] Hata: {e}")
                    time.sleep(5)
            
            print(f"[STREAM {stream_id}] Durduruldu")
        
        thread = threading.Thread(target=run, daemon=True)
        with self.lock:
            self.processes[stream_id] = {'thread': thread, 'process': None}
        thread.start()
        return True
    
    def stop_stream(self, stream_id):
        with self.lock:
            if stream_id in self.processes:
                if self.processes[stream_id].get('process'):
                    try:
                        self.processes[stream_id]['process'].terminate()
                        try:
                            self.processes[stream_id]['process'].wait(timeout=3)
                        except:
                            self.processes[stream_id]['process'].kill()
                    except:
                        pass
                del self.processes[stream_id]
                return True
        return False
    
    def is_running(self, stream_id):
        with self.lock:
            return stream_id in self.processes

stream_engine = StreamEngine()

# ============================================================
# TELEGRAM BOT - BASIT
# ============================================================

TOKEN = os.environ.get('BOT_TOKEN', '8732252434:AAGUA0qrHKrsbFq3sfNQUtwSFlAzHDivD3M')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7092798502'))

IBAN_INFO = """
🏦 **BANKA BILGILERI**

Bank: Garanti BBVA
IBAN: TR10 0006 2000 9100 0006 9697 09
Alıcı: Garanti Odeme ve Elektronik Para Hizmetleri A.S.
Aciklama: TAMİ7617949650259144

⚠️ Aciklama kismini mutlaka yazin!
"""

STREAM_PRICES = {1: 150, 2: 300, 3: 500}

# ============================================================
# VERITABANI FONKSIYONLARI
# ============================================================

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def register_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, registered_at) VALUES (?, ?, ?, ?)",
              (user_id, username or '', first_name or '', datetime.now().isoformat()))
    conn.commit()
    conn.close()

def is_user_banned(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def create_stream(user_id, name, stream_key, m3u_url, logo_url, price):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO streams (user_id, stream_name, stream_key, m3u_url, logo_url, price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (user_id, name, stream_key, m3u_url, logo_url, price, datetime.now().isoformat()))
    stream_id = c.lastrowid
    conn.commit()
    conn.close()
    return stream_id

def create_stream_request(user_id, data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO stream_requests (user_id, stream_name, stream_key, m3u_url, logo_url, stream_count, total_price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (user_id, data['name'], data['key'], data['m3u'], data['logo'], data['count'], data['price'], datetime.now().isoformat()))
    request_id = c.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_pending_requests():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM stream_requests WHERE status = 'pending' ORDER BY id DESC")
    result = c.fetchall()
    conn.close()
    return result

def get_request(request_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM stream_requests WHERE id = ?", (request_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_request_status(request_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE stream_requests SET status = ? WHERE id = ?", (status, request_id))
    conn.commit()
    conn.close()

def get_user_streams(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM streams WHERE user_id = ? ORDER BY id DESC", (user_id,))
    result = c.fetchall()
    conn.close()
    return result

def get_stream(stream_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM streams WHERE id = ?", (stream_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_stream_status(stream_id, is_active):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE streams SET is_active = ? WHERE id = ?", (is_active, stream_id))
    conn.commit()
    conn.close()

def update_stream_paid(stream_id, is_paid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE streams SET is_paid = ?, paid_at = ? WHERE id = ?", 
              (is_paid, datetime.now().isoformat(), stream_id))
    conn.commit()
    conn.close()

def delete_stream(stream_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM streams WHERE id = ?", (stream_id,))
    conn.commit()
    conn.close()

def get_all_streams():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT s.*, u.username FROM streams s JOIN users u ON s.user_id = u.user_id ORDER BY s.id DESC")
    result = c.fetchall()
    conn.close()
    return result

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY id DESC")
    result = c.fetchall()
    conn.close()
    return result

def get_active_streams():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM streams WHERE is_active = 1 AND is_paid = 1")
    result = c.fetchall()
    conn.close()
    return result

def is_bot_locked():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'bot_locked'")
    result = c.fetchone()
    conn.close()
    return result and result[0] == '1'

def create_payment(user_id, stream_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO payments (user_id, stream_id, amount, created_at) VALUES (?, ?, ?, ?)",
              (user_id, stream_id, amount, datetime.now().isoformat()))
    payment_id = c.lastrowid
    conn.commit()
    conn.close()
    return payment_id

def get_pending_payments():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT p.*, s.stream_name, u.username FROM payments p "
              "JOIN streams s ON p.stream_id = s.id "
              "JOIN users u ON p.user_id = u.user_id "
              "WHERE p.status = 'pending' ORDER BY p.id DESC")
    result = c.fetchall()
    conn.close()
    return result

def get_payment(payment_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
    result = c.fetchone()
    conn.close()
    return result

def update_payment_status(payment_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE payments SET status = ?, approved_at = ? WHERE id = ?", 
              (status, datetime.now().isoformat(), payment_id))
    conn.commit()
    conn.close()

def update_payment_receipt(payment_id, file_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE payments SET receipt_file_id = ? WHERE id = ?", (file_id, payment_id))
    conn.commit()
    conn.close()

# ============================================================
# REPLY KEYBOARD
# ============================================================

def get_main_keyboard(user_id):
    keyboard = [
        ["📝 Yayin Talebi Olustur"],
        ["📋 Yayinlarim", "⭐ Bilgilerim"],
        ["💳 Odeme Yap"],
        ["🏦 IBAN Bilgileri"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["🔧 Admin Paneli"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ============================================================
# BOT KOMUTLARI
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)
    
    if is_user_banned(user.id):
        await update.message.reply_text("🚫 YASAKLANDIN!", parse_mode='Markdown')
        return
    
    welcome = f"""
🎬 **Yayin Botuna Hos Geldin!**

👤 Kullanici: {user.first_name}

📌 **Fiyatlar:**
1 Yayin = 150 ₺
2 Yayin = 300 ₺
3 Yayin = 500 ₺

📝 **Nasil Calisir:**
1. Yayin talebi olustur
2. Admin onaylar
3. IBAN'a odeme yap
4. Dekont gonder
5. Admin onaylar
6. Yayin baslar!

Asagidaki butonlari kullan.
"""
    await update.message.reply_text(welcome, reply_markup=get_main_keyboard(user.id), parse_mode='Markdown')

# ============================================================
# MESAJ HANDLER
# ============================================================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    step = context.user_data.get('step')
    
    if is_user_banned(user_id) and user_id != ADMIN_ID:
        await update.message.reply_text("🚫 YASAKLANDIN!")
        return
    
    # ANA MENU
    if text == "📝 Yayin Talebi Olustur":
        if is_bot_locked() and user_id != ADMIN_ID:
            await update.message.reply_text("🔒 Bot kilitli!")
            return
        context.user_data['step'] = 'request_name'
        await update.message.reply_text("📝 **Yayin Adi:**\nYayinina bir isim ver:", parse_mode='Markdown')
    
    elif text == "📋 Yayinlarim":
        streams = get_user_streams(user_id)
        if not streams:
            await update.message.reply_text("❌ Yayinin yok!", reply_markup=get_main_keyboard(user_id))
            return
        
        msg = "📋 **Yayinlarim:**\n\n"
        keyboard = []
        for s in streams:
            if s[7] == 1 and s[8] == 1:
                status = "🟢 Yayinda" if stream_engine.is_running(s[0]) else "⏸ Durduruldu"
            else:
                status = "🔴 Odeme bekliyor"
            
            msg += f"**{s[2]}** (ID: {s[0]})\nDurum: {status}\nFiyat: {s[6]} ₺\nKey: `{s[3]}`\n---\n"
            
            if s[7] == 1 and s[8] == 1:
                if stream_engine.is_running(s[0]):
                    keyboard.append([InlineKeyboardButton(f"⏹ Durdur #{s[0]}", callback_data=f"stop_{s[0]}")])
                else:
                    keyboard.append([InlineKeyboardButton(f"▶️ Baslat #{s[0]}", callback_data=f"start_{s[0]}")])
            else:
                keyboard.append([InlineKeyboardButton(f"💳 Odeme Yap #{s[0]} ({s[6]}₺)", callback_data=f"pay_{s[0]}")])
            keyboard.append([InlineKeyboardButton(f"🗑 Sil #{s[0]}", callback_data=f"delete_{s[0]}")])
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif text == "⭐ Bilgilerim":
        user = get_user(user_id)
        streams = get_user_streams(user_id)
        info = f"""
👤 **Kullanici Bilgileri:**
ID: {user_id}
Kullanici: @{user[1] or 'yok'}
Kayit: {user[5]}
📺 Toplam Yayin: {len(streams)}
📌 Durum: {'Yasakli' if user[3] == 1 else 'Aktif'}
"""
        await update.message.reply_text(info, reply_markup=get_main_keyboard(user_id), parse_mode='Markdown')
    
    elif text == "💳 Odeme Yap":
        streams = get_user_streams(user_id)
        unpaid = [s for s in streams if s[8] == 0]
        if not unpaid:
            await update.message.reply_text("✅ Odeme bekleyen yayin yok!", reply_markup=get_main_keyboard(user_id))
            return
        
        keyboard = []
        for s in unpaid:
            keyboard.append([InlineKeyboardButton(f"{s[2]} - {s[6]}₺", callback_data=f"payment_select_{s[0]}")])
        await update.message.reply_text("💳 **Odeme Yap:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif text == "🏦 IBAN Bilgileri":
        await update.message.reply_text(IBAN_INFO, reply_markup=get_main_keyboard(user_id), parse_mode='Markdown')
    
    elif text == "🔧 Admin Paneli":
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Yetkin yok!")
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 Bekleyen Talepler", callback_data="pending_requests")],
            [InlineKeyboardButton("💳 Bekleyen Odemeler", callback_data="pending_payments")],
            [InlineKeyboardButton("👥 Kullanicilar", callback_data="admin_users")],
            [InlineKeyboardButton("📺 Tum Yayinlar", callback_data="admin_streams")],
            [InlineKeyboardButton("🔒 Kilitle", callback_data="admin_lock")],
            [InlineKeyboardButton("🔓 Ac", callback_data="admin_unlock")],
            [InlineKeyboardButton("📢 Duyuru", callback_data="admin_broadcast")],
        ]
        await update.message.reply_text("🔧 **Admin Paneli**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # FORM
    elif step == 'request_name':
        context.user_data['request_name'] = text
        context.user_data['step'] = 'request_key'
        await update.message.reply_text("🔑 **Yayin Key:**\nAnahtar gir (ornek: 'kanalim_123')", parse_mode='Markdown')
    
    elif step == 'request_key':
        if not text or ' ' in text:
            await update.message.reply_text("❌ Key bosluk icermemeli!")
            return
        context.user_data['request_key'] = text
        context.user_data['step'] = 'request_m3u'
        await update.message.reply_text("📡 **M3U URL:**\nM3U adresini gir:", parse_mode='Markdown')
    
    elif step == 'request_m3u':
        if not text.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ Gecersiz URL!")
            return
        context.user_data['request_m3u'] = text
        context.user_data['step'] = 'request_logo'
        await update.message.reply_text("🖼 **Logo URL:**\nLogo istemiyorsan 'gec' yaz:", parse_mode='Markdown')
    
    elif step == 'request_logo':
        logo_url = None
        if text.lower() != 'gec' and text.startswith(('http://', 'https://')):
            logo_url = text
        elif text.lower() != 'gec':
            await update.message.reply_text("❌ Gecersiz URL! 'gec' yaz veya URL gir.")
            return
        
        context.user_data['request_logo'] = logo_url
        context.user_data['step'] = 'request_count'
        
        keyboard = [
            [InlineKeyboardButton("1 Yayin - 150 ₺", callback_data="req_count_1")],
            [InlineKeyboardButton("2 Yayin - 300 ₺", callback_data="req_count_2")],
            [InlineKeyboardButton("3 Yayin - 500 ₺", callback_data="req_count_3")],
        ]
        await update.message.reply_text("💰 **Kac Yayin?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif step == 'broadcast':
        if user_id == ADMIN_ID:
            users = get_all_users()
            count = 0
            for u in users:
                if u[3] == 0:
                    try:
                        await context.bot.send_message(u[0], f"📢 DUYURU:\n\n{text}")
                        count += 1
                        time.sleep(0.05)
                    except:
                        pass
            await update.message.reply_text(f"✅ {count} kullaniciya gonderildi!")
            context.user_data['step'] = None

# ============================================================
# INLINE CALLBACK
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if is_user_banned(user_id) and user_id != ADMIN_ID:
        await query.edit_message_text("🚫 YASAKLANDIN!")
        return
    
    # Yayin talebi
    if data.startswith("req_count_"):
        count = int(data.split("_")[2])
        price = STREAM_PRICES.get(count, 150)
        
        name = context.user_data.get('request_name', 'Yayin')
        key = context.user_data.get('request_key', '')
        m3u = context.user_data.get('request_m3u', '')
        logo = context.user_data.get('request_logo', None)
        
        request_data = {'name': name, 'key': key, 'm3u': m3u, 'logo': logo, 'count': count, 'price': price}
        request_id = create_stream_request(user_id, request_data)
        
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"📝 YENI TALEP!\nID: {request_id}\nKullanici: {user_id}\nYayin: {name}\nKey: {key}\nSayi: {count}\nFiyat: {price} ₺",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Onayla", callback_data=f"approve_{request_id}")],
                    [InlineKeyboardButton("❌ Reddet", callback_data=f"reject_{request_id}")]
                ])
            )
        except:
            pass
        
        await query.edit_message_text(
            f"✅ Talep Olusturuldu!\n📺 {name}\n🔑 Key: {key}\n💰 {price} ₺\n\n⏳ Admin onayi bekleniyor...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menu", callback_data="main_menu")]]),
            parse_mode='Markdown'
        )
        
        context.user_data['step'] = None
        for k in ['request_name', 'request_key', 'request_m3u', 'request_logo']:
            context.user_data.pop(k, None)
    
    # Odeme secim
    elif data.startswith("payment_select_"):
        stream_id = int(data.split("_")[2])
        stream = get_stream(stream_id)
        if not stream or stream[1] != user_id:
            await query.edit_message_text("❌ Yayin bulunamadi!")
            return
        
        payment_id = create_payment(user_id, stream_id, stream[6])
        
        await query.edit_message_text(
            f"💳 Odeme Yapiliyor...\n\n📺 {stream[2]}\n💰 {stream[6]} ₺\n\n{IBAN_INFO}\n\n📤 Odeme yaptiktan sonra dekontu gonder!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Ana Menu", callback_data="main_menu")]]),
            parse_mode='Markdown'
        )
        
        context.user_data['payment_id'] = payment_id
        context.user_data['step'] = 'waiting_receipt'
    
    # Admin onay/red
    elif data.startswith("approve_") or data.startswith("reject_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Yetkin yok!")
            return
        
        request_id = int(data.split("_")[1])
        action = data.split("_")[0]
        req = get_request(request_id)
        if not req:
            await query.edit_message_text("❌ Talep bulunamadi!")
            return
        
        if action == "approve":
            update_request_status(request_id, 'approved')
            user_id2 = req[1]
            name = req[2]
            stream_key = req[3]
            m3u_url = req[4]
            logo_url = req[5]
            count = req[6]
            price = req[7]
            
            for i in range(count):
                key = f"{stream_key}_{i+1}" if count > 1 else stream_key
                stream_name = f"{name} #{i+1}" if count > 1 else name
                stream_id = create_stream(user_id2, stream_name, key, m3u_url, logo_url, price // count)
                update_stream_status(stream_id, 0)
                update_stream_paid(stream_id, 0)
            
            try:
                await context.bot.send_message(user_id2, f"✅ Yayin Talebin Onaylandi!\n📺 {name}\n🔑 Key: {stream_key}\n💰 {price} ₺\n\nOdeme yapmak icin '💳 Odeme Yap' butonuna tikla.")
            except:
                pass
            
            await query.edit_message_text(f"✅ Talep #{request_id} onaylandi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_panel")]]))
        
        elif action == "reject":
            update_request_status(request_id, 'rejected')
            try:
                await context.bot.send_message(req[1], f"❌ Yayin Talebin Reddedildi!\n📺 {req[2]}")
            except:
                pass
            await query.edit_message_text(f"❌ Talep #{request_id} reddedildi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_panel")]]))
    
    # Admin odeme onay/red
    elif data.startswith("pay_approve_") or data.startswith("pay_reject_"):
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Yetkin yok!")
            return
        
        payment_id = int(data.split("_")[2])
        action = data.split("_")[1]
        payment = get_payment(payment_id)
        if not payment:
            await query.edit_message_text("❌ Odeme bulunamadi!")
            return
        
        stream_id = payment[2]
        stream = get_stream(stream_id)
        
        if action == "approve":
            update_payment_status(payment_id, 'approved')
            update_stream_paid(stream_id, 1)
            update_stream_status(stream_id, 1)
            stream_engine.start_stream(stream_id, stream[3], stream[4], stream[5])
            
            try:
                await context.bot.send_message(payment[1], f"✅ Odemen Onaylandi!\n📺 {stream[2]}\n💰 {payment[3]} ₺\n\n🟢 Yayin baslatildi!")
            except:
                pass
            
            await query.edit_message_text(f"✅ Odeme #{payment_id} onaylandi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_panel")]]))
        
        elif action == "reject":
            update_payment_status(payment_id, 'rejected')
            try:
                await context.bot.send_message(payment[1], f"❌ Odemen Reddedildi!\n📺 {stream[2]}\n💰 {payment[3]} ₺")
            except:
                pass
            await query.edit_message_text(f"❌ Odeme #{payment_id} reddedildi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data="admin_panel")]]))
    
    # Yayin islemleri
    elif data.startswith("pay_"):
        stream_id = int(data.split("_")[1])
        stream = get_stream(stream_id)
        if not stream or stream[1] != user_id:
            await query.edit_message_text("❌ Yayin bulunamadi!")
            return
        
        if stream[8] == 1:
            await query.edit_message_text("✅ Zaten odendi!")
            return
        
        payment_id = create_payment(user_id, stream_id, stream[6])
        await query.edit_message_text(
            f"💳 Odeme Yapiliyor...\n\n📺 {stream[2]}\n💰 {stream[6]} ₺\n\n{IBAN_INFO}\n\n📤 Odeme yaptiktan sonra dekontu gonder!",
            parse_mode='Markdown'
        )
        context.user_data['payment_id'] = payment_id
        context.user_data['step'] = 'waiting_receipt'
    
    elif data.startswith("start_"):
        stream_id = int(data.split("_")[1])
        stream = get_stream(stream_id)
        if stream and stream[1] == user_id:
            if stream[7] != 1 or stream[8] != 1:
                await query.edit_message_text("❌ Odeme yapilmamis veya onaylanmamis!")
                return
            stream_engine.start_stream(stream_id, stream[3], stream[4], stream[5])
            await query.edit_message_text(f"✅ Yayin baslatildi!\n📺 {stream[2]}")
    
    elif data.startswith("stop_"):
        stream_id = int(data.split("_")[1])
        stream = get_stream(stream_id)
        if stream and (stream[1] == user_id or user_id == ADMIN_ID):
            stream_engine.stop_stream(stream_id)
            update_stream_status(stream_id, 0)
            await query.edit_message_text(f"⏹ Yayin durduruldu: {stream[2]}")
    
    elif data.startswith("delete_"):
        stream_id = int(data.split("_")[1])
        stream = get_stream(stream_id)
        if stream and (stream[1] == user_id or user_id == ADMIN_ID):
            stream_engine.stop_stream(stream_id)
            delete_stream(stream_id)
            await query.edit_message_text(f"🗑 Yayin silindi: {stream[2]}")
    
    # Admin panel
    elif data == "pending_requests":
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Yetkin yok!")
            return
        requests = get_pending_requests()
        if not requests:
            await query.edit_message_text("✅ Bekleyen talep yok.")
            return
        
        text = "📝 **Bekleyen Talepler:**\n\n"
        keyboard = []
        for r in requests:
            text += f"ID: {r[0]} | Kullanici: {r[1]}\nYayin: {r[2]} | Fiyat: {r[7]} ₺\n---\n"
            keyboard.append([
                InlineKeyboardButton(f"✅ Onayla #{r[0]}", callback_data=f"approve_{r[0]}"),
                InlineKeyboardButton(f"❌ Reddet #{r[0]}", callback_data=f"reject_{r[0]}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "pending_payments":
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Yetkin yok!")
            return
        payments = get_pending_payments()
        if not payments:
            await query.edit_message_text("✅ Bekleyen odeme yok.")
            return
        
        text = "💳 **Bekleyen Odemeler:**\n\n"
        keyboard = []
        for p in payments:
            text += f"ID: {p[0]} | Kullanici: @{p[8] or 'yok'}\nYayin: {p[7]} | Tutar: {p[3]} ₺\nDekont: {'✅' if p[5] else '❌'}\n---\n"
            keyboard.append([
                InlineKeyboardButton(f"✅ Onayla #{p[0]}", callback_data=f"pay_approve_{p[0]}"),
                InlineKeyboardButton(f"❌ Reddet #{p[0]}", callback_data=f"pay_reject_{p[0]}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "admin_users":
        if user_id != ADMIN_ID:
            return
        users = get_all_users()
        text = "👥 **Kullanicilar:**\n\n"
        for u in users[:50]:
            text += f"ID: {u[0]} | @{u[1] or 'yok'}\nDurum: {'🚫 Yasakli' if u[3] == 1 else '✅ Aktif'}\n---\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")]]), parse_mode='Markdown')
    
    elif data == "admin_streams":
        if user_id != ADMIN_ID:
            return
        streams = get_all_streams()
        if not streams:
            await query.edit_message_text("❌ Yayin yok.")
            return
        text = "📺 **Tum Yayinlar:**\n\n"
        for s in streams[:20]:
            status = "🟢 Aktif" if s[7] == 1 and s[8] == 1 else "🔴 Pasif"
            text += f"ID: {s[0]} | {s[2]}\nKullanici: @{s[9] or 'yok'}\nDurum: {status} | Fiyat: {s[6]} ₺\n---\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")]]), parse_mode='Markdown')
    
    elif data == "admin_lock":
        if user_id != ADMIN_ID:
            return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('bot_locked', '1'))
        conn.commit()
        conn.close()
        await query.edit_message_text("🔒 Bot kilitlendi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")]]))
    
    elif data == "admin_unlock":
        if user_id != ADMIN_ID:
            return
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('bot_locked', '0'))
        conn.commit()
        conn.close()
        await query.edit_message_text("🔓 Bot acildi!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Geri", callback_data="admin_panel")]]))
    
    elif data == "admin_broadcast":
        if user_id != ADMIN_ID:
            return
        context.user_data['step'] = 'broadcast'
        await query.edit_message_text("📢 Duyuru mesajini yaz:", parse_mode='Markdown')
    
    elif data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.edit_message_text("❌ Yetkin yok!")
            return
        keyboard = [
            [InlineKeyboardButton("📝 Bekleyen Talepler", callback_data="pending_requests")],
            [InlineKeyboardButton("💳 Bekleyen Odemeler", callback_data="pending_payments")],
            [InlineKeyboardButton("👥 Kullanicilar", callback_data="admin_users")],
            [InlineKeyboardButton("📺 Tum Yayinlar", callback_data="admin_streams")],
            [InlineKeyboardButton("🔒 Kilitle", callback_data="admin_lock")],
            [InlineKeyboardButton("🔓 Ac", callback_data="admin_unlock")],
            [InlineKeyboardButton("📢 Duyuru", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔙 Ana Menu", callback_data="main_menu")],
        ]
        await query.edit_message_text("🔧 **Admin Paneli**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "main_menu":
        await query.edit_message_text("🎬 **Ana Menu**", reply_markup=get_main_keyboard(user_id), parse_mode='Markdown')

# ============================================================
# DEKONT GONDERME
# ============================================================

async def receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    step = context.user_data.get('step')
    
    if step != 'waiting_receipt':
        return
    
    payment_id = context.user_data.get('payment_id')
    if not payment_id:
        return
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Dekontu resim veya dosya olarak gonder!", reply_markup=get_main_keyboard(user_id))
        return
    
    update_payment_receipt(payment_id, file_id)
    payment = get_payment(payment_id)
    
    try:
        stream = get_stream(payment[2])
        admin_text = f"💳 YENI DEKONT!\nOdeme ID: {payment_id}\nKullanici: {user_id}\nYayin: {stream[2] if stream else 'Bilinmiyor'}\nTutar: {payment[3]} ₺"
        
        keyboard = [
            [InlineKeyboardButton("✅ Onayla", callback_data=f"pay_approve_{payment_id}")],
            [InlineKeyboardButton("❌ Reddet", callback_data=f"pay_reject_{payment_id}")]
        ]
        
        if update.message.photo:
            await context.bot.send_photo(ADMIN_ID, file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await context.bot.send_document(ADMIN_ID, file_id, caption=admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        pass
    
    await update.message.reply_text("✅ Dekont gonderildi! Admin onayi bekleniyor.", reply_markup=get_main_keyboard(user_id))
    context.user_data['step'] = None
    context.user_data.pop('payment_id', None)

# ============================================================
# ANA FONKSIYON - 7/24 CALISIR VE HATA YONETIMI
# ============================================================

def main():
    print("[BOT] Baslatiliyor...")
    
    if TOKEN == '8732252434:AAGUA0qrHKrsbFq3sfNQUtwSFlAzHDivD3M':
        print("⚠️ Varsayilan token kullaniliyor!")
    
    # Sonsuz dongu ile 7/24 calisma
    while True:
        try:
            app = Application.builder().token(TOKEN).build()
            
            app.add_handler(CommandHandler("start", start))
            app.add_handler(CallbackQueryHandler(button_handler))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
            app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_handler))
            
            print(f"[BOT] Aktif! Admin: {ADMIN_ID}")
            
            # Kayitli yayinlari baslat
            streams = get_active_streams()
            for s in streams:
                try:
                    stream_engine.start_stream(s[0], s[3], s[4], s[5])
                    print(f"[BOT] Yayin yuklendi: {s[2]}")
                except Exception as e:
                    print(f"[BOT] Yayin yukleme hatasi: {e}")
            
            # Drop pending updates - CONFLICT cozumu
            # https://core.telegram.org/bots/api#getting-updates
            print("[BOT] Bekleniyor...")
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True  # Bu satir conflict hatasini cozer!
            )
            
        except Exception as e:
            print(f"[BOT] HATA: {e}")
            if "Conflict" in str(e):
                print("[BOT] Conflict hatasi! Bot zaten calisiyor olabilir.")
                print("[BOT] 30 saniye bekleniyor...")
                time.sleep(30)
            else:
                print("[BOT] 10 saniye sonra yeniden baslatiliyor...")
                time.sleep(10)
            continue

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
import time
import os
import threading
import requests

class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'

def print_colored(color, text):
    print(f"{color}{text}{Colors.NC}")

# Telegram RTMP ayarları
RTMP_URL = "rtmps://dc4-1.rtmp.t.me/s/"
STREAM_KEY = "3628247749:CP9SdqFTFOg3vd_nWef_Aw"
rtmp_server = f"{RTMP_URL}{STREAM_KEY}"

# DOĞRUDAN YAYIN KAYNAĞI (M3U8 veya direkt stream URL)
STREAM_SOURCE = "https://stream41.radyotelekom.com.tr/stream/m3u8/bfa921dfddb1846b74069b68904d64e6/bfa921dfddb1846b74069b68904d64e6.m3u8"

LOGO_URL = "https://raw.githubusercontent.com/mutlumedya/cine/refs/heads/main/telegram.png"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STREAM_USER_AGENT = "VLC/3.0.18 LibVLC/3.0.18"

# Yayın başlığı (ekranda gösterilecek)
STREAM_TITLE = "CANLI YAYIN"

def is_termux():
    return 'TERMUX_VERSION' in os.environ or '/data/data/com.termux' in os.environ

def check_dependencies():
    try:
        import requests  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        if is_termux():
            subprocess.run(["pkg", "install", "-y", "ffmpeg"], check=True)

def download_logo():
    try:
        if LOGO_URL.startswith('http'):
            response = requests.get(LOGO_URL, timeout=15)
            with open('logo.png', 'wb') as f:
                f.write(response.content)
            return True
        return os.path.exists(LOGO_URL)
    except Exception:
        return False

def sure_guncelleyici(durdur_event):
    """Arka planda saniyede bir title.txt dosyasını günceller."""
    while not durdur_event.is_set():
        try:
            with open("title.txt", "w", encoding="utf-8") as f:
                f.write(STREAM_TITLE)
        except Exception:
            pass
        durdur_event.wait(1)

def start_stream():
    while True:
        try:
            print_colored(Colors.GREEN, f"▶ Yayın Başlatılıyor: {STREAM_TITLE}")
            print_colored(Colors.BLUE, f"   Kaynak: {STREAM_SOURCE}")
            print_colored(Colors.BLUE, f"   Hedef: {rtmp_server}")

            durdur_event = threading.Event()
            guncelleyici = threading.Thread(
                target=sure_guncelleyici,
                args=(durdur_event,),
                daemon=True
            )
            guncelleyici.start()

            # FFmpeg komutu - DÜZELTİLDİ
            # Önce tüm input'ları belirt, sonra filtre ve output ayarlarını yap
            command = [
                'ffmpeg',
                '-user_agent', STREAM_USER_AGENT,
                '-re',
                '-i', STREAM_SOURCE,
                # M3U8 için özel parametreler (input'a ait)
                '-analyzeduration', '2147483647',
                '-probesize', '2147483647',
                '-fflags', '+igndts',
            ]
            
            # Logo varsa input olarak ekle
            if os.path.exists('logo.png'):
                command.extend(['-i', 'logo.png'])
                
                filter_str = (
                    '[0:v]scale=1280:720:force_original_aspect_ratio=decrease,'
                    'pad=1280:720:(ow-iw)/2:(oh-ih)/2:black[v0];'
                    '[1:v]scale=-1:90[logo];'
                    '[v0][logo]overlay=W-w-10:10[vlogo];'
                    f'[vlogo]drawtext=fontfile={FONT_PATH}:'
                    'textfile=title.txt:reload=1:'
                    'fontcolor=white:fontsize=20:line_spacing=6:'
                    'x=23:y=h-text_h-20[v]'
                )
            else:
                filter_str = (
                    '[0:v]scale=1280:720:force_original_aspect_ratio=decrease,'
                    'pad=1280:720:(ow-iw)/2:(oh-ih)/2:black[v0];'
                    f'[v0]drawtext=fontfile={FONT_PATH}:'
                    'textfile=title.txt:reload=1:'
                    'fontcolor=white:fontsize=22:line_spacing=6:'
                    'x=20:y=h-text_h-20[v]'
                )
            
            # Filtre ve output parametreleri
            command.extend([
                '-filter_complex', filter_str,
                '-map', '[v]', '-map', '0:a?',
                '-c:v', 'libx264', '-preset', 'veryfast',
                '-pix_fmt', 'yuv420p',
                '-b:v', '2500k', '-maxrate', '2500k', '-bufsize', '5000k',
                '-g', '50',
                '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
                '-f', 'flv', rtmp_server
            ])

            print_colored(Colors.YELLOW, "📹 FFmpeg başlatılıyor...")
            process = subprocess.Popen(command)
            process.wait()

            durdur_event.set()
            guncelleyici.join(timeout=2)

            print_colored(Colors.YELLOW, "⏳ Bağlantı kesildi, 5 saniye sonra yeniden bağlanılıyor...")
            time.sleep(5)
            
        except KeyboardInterrupt:
            print_colored(Colors.RED, "\n⏹ Yayın durduruldu.")
            break
        except Exception as e:
            print_colored(Colors.RED, f"❌ Hata: {e}")
            print_colored(Colors.YELLOW, "⏳ 10 saniye sonra yeniden deneniyor...")
            time.sleep(10)

def main():
    print_colored(Colors.BLUE, "🎬 Telegram RTMP Canlı Yayın Başlatılıyor...")
    print_colored(Colors.BLUE, f"📡 Sunucu: {RTMP_URL}")
    print_colored(Colors.BLUE, f"🔑 Stream Key: {STREAM_KEY[:8]}...")
    print_colored(Colors.BLUE, f"📺 Yayın Kaynağı: {STREAM_SOURCE}")
    check_dependencies()
    download_logo()
    start_stream()

if __name__ == "__main__":
    main()

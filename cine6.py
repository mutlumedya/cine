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

# Direkt yayın kaynağı (M3U8 veya başka bir stream URL'si)
STREAM_SOURCE = "https://cdn.codenet.lol/streamgo/stremgo123/4864.m3u8"  # ⚠️ BURAYI DEĞİŞTİRİN!

# Logo ayarları
LOGO_URL = "https://i.hizliresim.com/uqid8yei.png"  # Logo URL'si
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# FFmpeg için user-agent
STREAM_USER_AGENT = "VLC/3.0.18 LibVLC/3.0.18"

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
    """Logoyu indir veya kontrol et"""
    try:
        if LOGO_URL.startswith('http'):
            response = requests.get(LOGO_URL, timeout=15)
            if response.status_code == 200:
                with open('logo.png', 'wb') as f:
                    f.write(response.content)
                print_colored(Colors.GREEN, "✅ Logo indirildi!")
                return True
        return os.path.exists(LOGO_URL)
    except Exception as e:
        print_colored(Colors.YELLOW, f"⚠️ Logo indirilemedi: {e}")
        return False

def start_stream():
    print_colored(Colors.GREEN, f"▶ Yayın başlatılıyor...")
    print_colored(Colors.BLUE, f"   Kaynak: {STREAM_SOURCE}")
    print_colored(Colors.BLUE, f"   Hedef: {rtmp_server}")
    
    # Logoyu kontrol et
    logo_var = os.path.exists('logo.png')
    if logo_var:
        print_colored(Colors.GREEN, "✅ Logo hazır!")
    else:
        print_colored(Colors.YELLOW, "⚠️ Logo bulunamadı, logoyuz devam ediliyor...")
    
    while True:
        try:
            # FFmpeg komutu - logo ile birlikte
            if logo_var:
                # Logo ile yayın
                command = [
                    'ffmpeg',
                    '-user_agent', STREAM_USER_AGENT,
                    '-re',
                    '-i', STREAM_SOURCE,
                    '-i', 'logo.png',
                    '-filter_complex',
                    f'[0:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black[v0];'
                    f'[1:v]scale=-1:90[logo];'
                    f'[v0][logo]overlay=W-w-10:10[v]',
                    '-map', '[v]',
                    '-map', '0:a?',
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
                    '-pix_fmt', 'yuv420p',
                    '-b:v', '2500k',
                    '-maxrate', '2500k',
                    '-bufsize', '5000k',
                    '-g', '50',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-f', 'flv',
                    rtmp_server
                ]
            else:
                # Logosuz yayın
                command = [
                    'ffmpeg',
                    '-user_agent', STREAM_USER_AGENT,
                    '-re',
                    '-i', STREAM_SOURCE,
                    '-c:v', 'libx264',
                    '-preset', 'veryfast',
                    '-pix_fmt', 'yuv420p',
                    '-b:v', '2500k',
                    '-maxrate', '2500k',
                    '-bufsize', '5000k',
                    '-g', '50',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-ar', '44100',
                    '-f', 'flv',
                    rtmp_server
                ]

            process = subprocess.Popen(command)
            process.wait()

            print_colored(Colors.YELLOW, "🔄 Bağlantı koptu, 5 saniye sonra yeniden bağlanılıyor...")
            time.sleep(5)
            
        except KeyboardInterrupt:
            print_colored(Colors.RED, "\n⏹ Yayın durduruldu.")
            break
        except Exception as e:
            print_colored(Colors.RED, f"❌ Hata: {e}")
            print_colored(Colors.YELLOW, "🔄 10 saniye sonra yeniden deneniyor...")
            time.sleep(10)

def main():
    print_colored(Colors.BLUE, "🎬 Telegram RTMP Yayın Başlatılıyor...")
    print_colored(Colors.BLUE, f"📡 Sunucu: {RTMP_URL}")
    print_colored(Colors.BLUE, f"🔑 Stream Key: {STREAM_KEY[:8]}...")
    
    check_dependencies()
    download_logo()  # Logoyu indir
    start_stream()

if __name__ == "__main__":
    main()

import cv2
import time
import numpy as np
import os
import requests
import threading
from datetime import datetime
import base64

# --- БАПТАУЛАР ---
TOKEN = "8071874921:AAHZn3SdfNc0K29fdnLBbB9quEGnuK6czc4"
CHAT_ID = "5868939793"

# WEB SERVER INTEGRATION
WEB_SERVER_URL = "http://localhost:5000/api/add_violation"

stats = {
    "start_time": time.time(),
    "no_helmet_count": 0,
    "total_captures": 0,
    "staff_total_seconds": 0
}
report_sent_today = False 
violation_history = []
last_update_id = 0
current_frame = None 
auto_mode = True 
staff_start_seen = None # Адамның кадрға кірген уақыты

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': CHAT_ID, 'text': message})
    except: pass

def send_telegram_alert(image_path, message):
    """Send alert to Telegram AND web server"""
    def upload():
        try:
            # 1. Send to Telegram
            url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
            files = {'photo': open(image_path, 'rb')}
            requests.post(url, data={'chat_id': CHAT_ID, 'caption': message}, files=files)
            
            # 2. Send to Web Server
            send_to_web_server(image_path, message)
        except Exception as e:
            print(f"Error in send_telegram_alert: {e}")
    
    threading.Thread(target=upload).start()

def send_to_web_server(image_path, message):
    """Send violation data to web server"""
    try:
        # Read image and convert to base64
        with open(image_path, 'rb') as img_file:
            img_data = img_file.read()
            img_base64 = base64.b64encode(img_data).decode('utf-8')
        
        # Extract timestamp from message
        timestamp = datetime.now().strftime('%H:%M:%S %d.%m.%Y')
        
        # Prepare payload
        payload = {
            'timestamp': timestamp,
            'violation_type': 'No Helmet',
            'object_name': 'Worker',
            'image_base64': img_base64
        }
        
        # Send POST request to web server
        response = requests.post(WEB_SERVER_URL, json=payload, timeout=5)
        
        if response.status_code == 201:
            print(f"✅ Violation sent to web server successfully")
        else:
            print(f"⚠️ Web server response: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("⚠️ Web server is not running. Start Flask server (python app.py)")
    except Exception as e:
        print(f"❌ Error sending to web server: {e}")

def telegram_worker():
    global last_update_id, current_frame, report_sent_today
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 5}
            resp = requests.get(url, params=params).json()
            for result in resp.get('result', []):
                last_update_id = result['update_id']
                if 'message' in result and 'text' in result['message']:
                    if result['message']['text'] == "/photo" and current_frame is not None:
                        path = "snap.jpg"
                        cv2.imwrite(path, current_frame)
                        send_telegram_alert(path, "📸 Сұраныс бойынша скриншот")

            now = datetime.now()
            if now.hour == 18 and now.minute == 0 and not report_sent_today:
                total_hours = stats["staff_total_seconds"] // 3600
                total_mins = (stats["staff_total_seconds"] % 3600) // 60
                report = (
                    f"📊 КҮНДЕЛІКТІ ЕСЕП ({now.strftime('%d.%m.%Y')})\n\n"
                    f"⏱ Жалпы жұмыс уақыты: {total_hours} сағ {total_mins} мин\n"
                    f"⚠️ Каскасыз жүргендер: {stats['no_helmet_count']} рет\n"
                    f"📸 Барлық түсірілген суреттер: {stats['total_captures']}"
                )
                send_telegram_msg(report)
                report_sent_today = True
            
            if now.hour == 0:
                report_sent_today = False
                stats.update({"no_helmet_count": 0, "total_captures": 0, "staff_total_seconds": 0})

        except: pass
        time.sleep(2)

threading.Thread(target=telegram_worker, daemon=True).start()

if not os.path.exists('violations'): os.makedirs('violations')
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cap = cv2.VideoCapture(0)
p_time, last_save_time = 0, 0

print("🚀 Computer Vision System Started")
print("📡 Web Server URL:", WEB_SERVER_URL)
print("🤖 Telegram Integration: Active")
print("\nҚышқылдар:")
print("  Q - Шығу")
print("  M - AUTO/MANUAL режимін ауыстыру")
print("  S - Қолмен сурет түсіру (MANUAL режимінде)")

while True:
    ret, frame = cap.read()
    if not ret: break
    current_frame = frame.copy()
    h, w, _ = frame.shape
    
    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
    hsv_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2HSV)
    
    display_frame = cv2.copyMakeBorder(frame, 0, 0, 0, 300, cv2.BORDER_CONSTANT, value=(20, 20, 20))
    faces = face_cascade.detectMultiScale(gray_small, 1.2, 4)

    # --- 1. ЖҰМЫС УАҚЫТЫН ЕСЕПТЕУ ---
    if len(faces) > 0:
        if staff_start_seen is None:
            staff_start_seen = time.time()
        current_stay = int(time.time() - staff_start_seen)
        stats["staff_total_seconds"] += (1/20) # Болжалды уақытты қосу (әр кадр сайын)
    else:
        staff_start_seen = None
        current_stay = 0

    # --- 2. REC ИНДИКАТОРЫ ---
    if int(time.time()) % 2 == 0:
        cv2.circle(display_frame, (w - 20, 30), 8, (0, 0, 255), -1)
        cv2.putText(display_frame, "REC", (w - 70, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # UI: Статистика панелі
    fps = 1 / (time.time() - p_time + 0.0001)
    p_time = time.time()
    cv2.rectangle(display_frame, (10, 10), (280, 130), (40, 40, 40), -1)
    cv2.putText(display_frame, f"FPS: {int(fps)}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(display_frame, f"Staff in Frame: {len(faces)}", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(display_frame, f"Stay Time: {current_stay}s", (20, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(display_frame, f"MODE: {'AUTO' if auto_mode else 'MANUAL'}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 150, 0), 2)

    # Violation Log
    cv2.putText(display_frame, "VIOLATION LOG", (w + 20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    for i, entry in enumerate(violation_history[-15:]):
        cv2.putText(display_frame, f"- {entry}", (w + 15, 80 + i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    for (sx, sy, sw, sh) in faces:
        x, y, w_f, h_f = sx*2, sy*2, sw*2, sh*2
        cv2.rectangle(display_frame, (x, y), (x + w_f, y + h_f), (255, 0, 0), 2)

       
        helmet_roi = hsv_small[max(0, sy-int(sh*0.5)) : sy, sx : sx + sw]
        has_helmet = False
        if helmet_roi.size > 0:
            mask = cv2.inRange(helmet_roi, np.array([15, 100, 100]), np.array([35, 255, 255]))
            if np.sum(mask) > 1500: has_helmet = True
            
        if not has_helmet:
            cv2.putText(display_frame, "NO HELMET!", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if auto_mode and time.time() - last_save_time > 20:
                stats["no_helmet_count"] += 1
                stats["total_captures"] += 1
                t_str = time.strftime("%H:%M:%S")
                img_path = f"violations/alert_{int(time.time())}.jpg"
                cv2.imwrite(img_path, frame)
                send_telegram_alert(img_path, f"⚠️ {t_str}: Каскасыз жұмысшы!")
                violation_history.append(f"{t_str}: No Helmet")
                last_save_time = time.time()

    cv2.imshow('Safety AI Master System', display_frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): break
    elif key == ord('m'): auto_mode = not auto_mode
    elif key == ord('s') and not auto_mode:
        stats["total_captures"] += 1
        cv2.imwrite(f"violations/manual_{int(time.time())}.jpg", frame)
        send_telegram_alert(f"violations/manual_{int(time.time())}.jpg", "📸 Қолмен сурет")

cap.release()
cv2.destroyAllWindows()

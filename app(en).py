import os
import sys
import atexit
import signal
import time
import serial
import cv2
import numpy as np

# ==================== НАСТРОЙКА BLUETOOTH ====================
# Номер вашего проверенного беспроводного порта
BLUETOOTH_PORT = 'COM3' 
# =============================================================

# --- НАСТРОЙКИ ФИЛЬТРА ДЛЯ КРАСНОГО ЦВЕТА (В диапазоне HSV) ---
red_lower1 = np.array([0, 120, 70])
red_upper1 = np.array([10, 255, 255])
red_lower2 = np.array([170, 120, 70])
red_upper2 = np.array([180, 255, 255])
Last = 0

ser = None

def send_motor_command(port, power):
    """Отправка прямого Bluetooth-пакета управления мотором (БЕЗ ОПРОСА И ОТВЕТА)"""
    if ser is None or not ser.is_open:
        return
    try:
        power = max(-100, min(100, power))
        if power < 0:
            power = 256 + power  
            
        packet = bytearray([
            0x0c, 0x00, 0x80, 0x04, port, power, 
            0x01, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00
        ])
        ser.write(packet)
    except:
        pass

def emergency_stop(*args):
    """Мгновенное беспроводное выключение моторов при выходе из программы"""
    print("\n[System] Stopping robot")
    try:
        send_motor_command(0x00, 0) 
        send_motor_command(0x01, 0) 
        time.sleep(0.1)
        if ser and ser.is_open:
            ser.close()
    except:
        pass
    cv2.destroyAllWindows()
    print("[System] Robot has stopped.")
    os._exit(0)

atexit.register(emergency_stop)
signal.signal(signal.SIGINT, emergency_stop)
signal.signal(signal.SIGTERM, emergency_stop)

try:
    print(f"Opening a wireless comunication channel via {BLUETOOTH_PORT}...")
    print("Please wait...")
    
    ser = serial.Serial(BLUETOOTH_PORT, baudrate=57600, timeout=0.01)
    print("Wireless communication channel activated")
    
    # Посылаем стартовый писк (команда PlayTone, ответ от робота не требуется)
    ser.write(bytearray([0x06, 0x00, 0x80, 0x03, 0x58, 0x02, 0x2c, 0x01]))
    time.sleep(0.4)
    
except Exception as e:
    print(f"\n[Error] Error opening channel via {BLUETOOTH_PORT}: {e}")
    sys.exit()

print("Opening camera")
camera = cv2.VideoCapture(0) 

if not camera.isOpened():
    print("[Error] Error opening camera")
    sys.exit()

print("Robot started")

last_seen = None 
time_lost = 0.0

try:
    while True:
        success, frame = camera.read()
        if not success:
            break
            
        frame = cv2.resize(frame, (400, 300))
        blurred = cv2.GaussianBlur(frame, (11, 11), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        
        mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
        mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
        mask = mask1 + mask2
        mask = cv2.erode(mask, None, iterations=2)
        mask = cv2.dilate(mask, None, iterations=2)
        
        contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        ball_found = False
        
        if len(contours) > 0:
            # ИСПРАВЛЕНО: синтаксис lambda c: cv2.contourArea(c) для Python
            c = max(contours, key=lambda c: cv2.contourArea(c)) 
            ((x, y), radius) = cv2.minEnclosingCircle(c)
            
            if radius > 15:
                ball_found = True
                cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 0), 2)
                screen_center_x = frame.shape[1] / 2
                
                DEAD_ZONE = 65 
                
                # --- БЕСПРОВОДНАЯ ЛОГИКА ДВИЖЕНИЯ (Повороты строго на 60% мощности) ---
                if x < screen_center_x - DEAD_ZONE:
                    print("Turning LEFT")
                    last_seen = 'left'  
                    send_motor_command(0x00, 65)   # Левое колесо вперед
                    send_motor_command(0x01, -65)  # Правое колесо назад
                    Last = 0
                    
                elif x > screen_center_x + DEAD_ZONE:
                    print("Turning RIGHT")
                    last_seen = 'right' 
                    send_motor_command(0x00, -65)  # Левое колесо назад
                    send_motor_command(0x01, 65) # Правое колесо вперед
                    Last = 1
                    
                else:
                    last_seen = None 
                    if radius < 85:  
                        print("FORWARD")
                        send_motor_command(0x00, 70)
                        send_motor_command(0x01, 70)
                    else:  
                        print("STOP")
                        send_motor_command(0x00, 0)
                        send_motor_command(0x01, 0)
                        
        if not ball_found:
            """Ищем шарик"""
            print("The ball is lost.")
            if Last == 0:
                send_motor_command(0x00, 60)  
                send_motor_command(0x01, -60)
            else:
                send_motor_command(0x00, -60)  
                send_motor_command(0x01, 60)
            
            if time_lost == 0.0:
                time_lost = time.time()
                
            if time.time() - time_lost < 0.4:
                if last_seen == 'left':
                    send_motor_command(0x00, 60)
                    send_motor_command(0x01, -60)
                elif last_seen == 'right':
                    send_motor_command(0x00, -60)
                    send_motor_command(0x01, 60)
                else:
                    send_motor_command(0x00, 0)
                    send_motor_command(0x01, 0)
            else:
                send_motor_command(0x00, 0)
                send_motor_command(0x01, 0)
        else:
            time_lost = 0.0
            
        cv2.imshow("Robot camera", frame)
        
        if cv2.waitKey(1) & 0xFF == ord('s'):
            emergency_stop()

except KeyboardInterrupt:
    pass

finally:
    emergency_stop()

import cv2
import numpy as np
import mss
import pygetwindow as gw
import win32api
import win32con
import threading
import time
import math

running = True

def virtual_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def hold_right_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)

def release_right_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def move_mouse_thread():
    while running:
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 2, 0, 0)
        time.sleep(0.01)

def find_roblox_window():
    windows = gw.getWindowsWithTitle('Roblox')
    if not windows:
        return None
    win = windows[0]
    return {'top': win.top, 'left': win.left, 'width': win.width, 'height': win.height}

def is_ball_contour(cnt, frame):
    min_area = 60
    max_area = 700
    min_circularity = 0.6

    area = cv2.contourArea(cnt)
    if area < min_area or area > max_area:
        return False

    perimeter = cv2.arcLength(cnt, True)
    if perimeter == 0:
        return False

    circularity = 4 * np.pi * area / (perimeter * perimeter)
    if circularity < min_circularity:
        return False

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [cnt], -1, 255, -1)
    mean_val = cv2.mean(frame, mask=mask)[2]

    if mean_val < 100:
        return False

    return True

def detect_red_ball(frame, player_box):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 220, 180])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 220, 180])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    px, py, pw, ph = player_box
    px = max(px, 0)
    py = max(py, 0)
    pw = min(pw, frame.shape[1] - px)
    ph = min(ph, frame.shape[0] - py)
    red_mask[py:py+ph, px:px+pw] = 0

    kernel = np.ones((3,3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_cnt = None
    max_area = 0
    for cnt in contours:
        if is_ball_contour(cnt, frame):
            area = cv2.contourArea(cnt)
            if area > max_area:
                max_area = area
                best_cnt = cnt

    if best_cnt is None:
        return None

    M = cv2.moments(best_cnt)
    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)

def detection_thread(capture_area):
    global running
    player_box_w, player_box_h = 115, 55
    box_x = (capture_area['width'] - player_box_w) // 2 - 25
    box_y = (capture_area['height'] - player_box_h) // 2

    last_ball_pos = None
    last_detection_time = 0
    last_click_time = 0
    last_click_pos = None
    ball_was_present = False

    MIN_DEBOUNCE_TIME = 0.20
    MIN_DIST_AFTER_CLICK = 30
    MIN_DIST_TO_REACT = 10
    MIN_COOLDOWN_AFTER_CLICK = 0.5

    with mss.mss() as sct:
        while running:
            sct_img = sct.grab(capture_area)
            frame = np.array(sct_img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            ball_pos = detect_red_ball(frame, (box_x, box_y, player_box_w, player_box_h))
            now = time.time()

            if ball_pos is not None:
                if last_ball_pos is not None and last_detection_time != 0:
                    dt = now - last_detection_time
                    dx = ball_pos[0] - last_ball_pos[0]
                    dy = ball_pos[1] - last_ball_pos[1]
                    dist = math.sqrt(dx*dx + dy*dy)
                    speed = dist / dt if dt > 0 else 0
                else:
                    speed = 305

                if speed > 550:
                    cooldown_delay = min(0.55, 0.3 + (speed - 550) / 800)
                    if (now - last_click_time) < cooldown_delay:
                        continue

                if speed < 255:
                    cooldown = 8
                elif speed < 305:
                    cooldown = 2
                else:
                    cooldown = 0.40
                cooldown = max(cooldown, MIN_DEBOUNCE_TIME)
                cooldown = max(cooldown, MIN_COOLDOWN_AFTER_CLICK)

                dist_since_click = math.sqrt((ball_pos[0] - last_click_pos[0])**2 + (ball_pos[1] - last_click_pos[1])**2) if last_click_pos else 1000
                dist_since_last_pos = math.sqrt((ball_pos[0] - last_ball_pos[0])**2 + (ball_pos[1] - last_ball_pos[1])**2) if last_ball_pos else 1000

                same_spot_as_last_click = dist_since_click < MIN_DIST_AFTER_CLICK
                same_spot_as_last_pos = dist_since_last_pos < MIN_DIST_TO_REACT

                time_since_last_click = now - last_click_time

                print(f"Speed={speed:.2f}, cooldown={cooldown:.2f}, time_since_last_click={time_since_last_click:.2f}, dist_click={dist_since_click:.1f}, dist_last_pos={dist_since_last_pos:.1f}")

                if (time_since_last_click > cooldown) and (not same_spot_as_last_click) and (not same_spot_as_last_pos):
                    print(f"[DEBUG] Clicking at {ball_pos} with speed {speed:.2f}")
                    virtual_click()
                    last_click_time = now
                    last_click_pos = ball_pos
                else:
                    print(f"[DEBUG] Skipping click")

                last_ball_pos = ball_pos
                last_detection_time = now
                ball_was_present = True
            else:
                if ball_was_present:
                    last_ball_pos = None
                    last_detection_time = 0
                    ball_was_present = False

            if cv2.waitKey(1) & 0xFF == 27:
                running = False
                break

def main():
    global running
    cap_area = find_roblox_window()
    if not cap_area:
        print("Roblox window not found.")
        return

    hold_right_click()

    detect_thread = threading.Thread(target=detection_thread, args=(cap_area,))
    mouse_thread = threading.Thread(target=move_mouse_thread)  # <--- Fix here
    detect_thread.start()
    mouse_thread.start()

    try:
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        detect_thread.join()
        release_right_click()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
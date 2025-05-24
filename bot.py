import cv2
import numpy as np
import mss
import pygetwindow as gw
import win32api
import win32con
import threading
import time
import math
import random

running = True

# Scroll & click control variables
scroll_state = 'fast'  # 'fast' or 'slow'
last_scroll_time = 0
scroll_cooldown = 0.3  # seconds to wait after scroll before next action
scrolling_in_progress = False
ready_to_click = False

last_click_time = 0
last_click_pos = None

def virtual_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def hold_right_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)

def release_right_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def move_mouse_thread():
    while running:
        if random.random() < 0.002:
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 2, 0, 0)
        time.sleep(0.01)

def find_roblox_window():
    windows = gw.getWindowsWithTitle('Roblox')
    if not windows:
        return None
    win = windows[0]
    return {'top': win.top, 'left': win.left, 'width': win.width, 'height': win.height}

def is_ball_contour(cnt, frame):
    area = cv2.contourArea(cnt)
    if area < 60 or area > 700:
        return False
    perimeter = cv2.arcLength(cnt, True)
    if perimeter == 0:
        return False
    circularity = 4 * np.pi * area / (perimeter * perimeter)
    if circularity < 0.6:
        return False
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [cnt], -1, 255, -1)
    mean_val = cv2.mean(frame, mask=mask)[2]
    return mean_val >= 100

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
    red_mask[py:py+ph, px:px+pw] = 0  # exclude player box area
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        if is_ball_contour(cnt, frame):
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
    return None

def scroll_mouse(delta):
    global last_scroll_time, scrolling_in_progress, ready_to_click
    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
    last_scroll_time = time.time()
    scrolling_in_progress = True
    ready_to_click = False  # block clicking immediately after scroll

def update_scroll_state(ball_speed):
    global scroll_state, last_scroll_time, scrolling_in_progress, ready_to_click

    now = time.time()
    # If scrolling cooldown passed, allow clicks
    if scrolling_in_progress and (now - last_scroll_time) > scroll_cooldown:
        scrolling_in_progress = False
        ready_to_click = True

    if scrolling_in_progress:
        return  # Do not scroll again while cooldown is active

    # Scroll if needed (only on state change)
    if scroll_state == 'fast' and ball_speed < 299:
        scroll_mouse(-240)  # scroll down to zoom slow
        scroll_state = 'slow'
    elif scroll_state == 'slow' and ball_speed > 300:
        scroll_mouse(240)   # scroll up to zoom fast
        scroll_state = 'fast'

def try_click(ball_pos, ball_speed):
    global last_click_time, last_click_pos, ready_to_click

    if not ready_to_click:
        return

    now = time.time()
    # Dynamic cooldown based on speed
    if ball_speed > 300:
        click_cooldown = 0.25
    elif ball_speed > 299:
        click_cooldown = 0.5
    else:
        click_cooldown = 0.8

    dist = 1000
    if last_click_pos is not None:
        dist = math.hypot(ball_pos[0] - last_click_pos[0], ball_pos[1] - last_click_pos[1])

    if (now - last_click_time) > click_cooldown and dist > 30:
        virtual_click()
        last_click_time = now
        last_click_pos = ball_pos
        ready_to_click = False  # block further clicks until next scroll cooldown

def detection_thread(capture_area):
    global running

    player_box_w, player_box_h = 115, 55
    box_x = (capture_area['width'] - player_box_w) // 2 - 25
    box_y = (capture_area['height'] - player_box_h) // 2

    last_ball_pos = None
    last_detection_time = None

    with mss.mss() as sct:
        while running:
            frame = np.array(sct.grab(capture_area))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            ball_pos = detect_red_ball(frame, (box_x, box_y, player_box_w, player_box_h))
            now = time.time()

            if ball_pos is not None:
                # Calculate ball speed
                if last_ball_pos is not None and last_detection_time is not None:
                    dist = math.hypot(ball_pos[0] - last_ball_pos[0], ball_pos[1] - last_ball_pos[1])
                    time_diff = now - last_detection_time
                    speed = dist / time_diff if time_diff > 0 else 0
                else:
                    speed = 180  # assume fast at first detection

                update_scroll_state(speed)
                try_click(ball_pos, speed)

                last_ball_pos = ball_pos
                last_detection_time = now

            else:
                # No ball detected, reset last detection to avoid false speed calc
                last_ball_pos = None
                last_detection_time = None

            time.sleep(0.01)  # small delay to reduce CPU usage

def main():
    global running
    cap_area = find_roblox_window()
    if not cap_area:
        print("Roblox window not found.")
        return

    hold_right_click()

    threading.Thread(target=detection_thread, args=(cap_area,), daemon=True).start()
    threading.Thread(target=move_mouse_thread, daemon=True).start()

    try:
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        running = False
        release_right_click()

if __name__ == "__main__":
    main()

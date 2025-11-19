#!/usr/bin/env python3
import math
import threading
import time
import argparse
import sys

import pygame
import pygame.freetype

# python-can on vapaaehtoinen (demo toimii ilman)
try:
    import can
except ImportError:
    can = None

# --------------------------------------------------------------------------------------
# KONFIGURAATIO
# --------------------------------------------------------------------------------------

SCREEN_WIDTH = 2000
SCREEN_HEIGHT = 800

MAX_SPEED = 180.0   # km/h
MAX_SOC = 100.0     # %

CAN_CHANNEL = "can0"
CAN_BITRATE = 500000  # vain dokumentaatiota varten

# CAN-ID:t (muuta vastaamaan omaa autoasi)
CAN_ID_SPEED = 0x100       # uint16, km/h * 100
CAN_ID_SOC = 0x200         # uint8, 0–100 %
CAN_ID_GEAR = 0x310        # uint8, 0=P,1=R,2=N,3=D
CAN_ID_MODE = 0x300        # uint8, 0=ECO,1=NORMAL,2=SPORT

BOOT_FADE_SECONDS = 1.0    # boot-animaation kesto

# --------------------------------------------------------------------------------------
# TILA
# --------------------------------------------------------------------------------------

class DashboardState:
    def __init__(self):
        # "Todelliset" arvot CANilta
        self.speed_target = 0.0
        self.soc_target = 80.0
        self.gear_target = "P"
        self.mode_target = "NORMAL"

        # Näytöllä näkyvät arvot (pehmennetty animaatio)
        self.speed_display = 0.0
        self.soc_display = 80.0
        self.gear_display = "P"
        self.mode_display = "NORMAL"

        self.demo = False
        self.running = True
        self._lock = threading.Lock()

    def set_from_can(self, speed=None, soc=None, gear=None, mode=None):
        with self._lock:
            if speed is not None:
                self.speed_target = max(0.0, min(MAX_SPEED, speed))
            if soc is not None:
                self.soc_target = max(0.0, min(MAX_SOC, soc))
            if gear is not None:
                self.gear_target = gear
            if mode is not None:
                self.mode_target = mode

    def get_snapshot(self):
        with self._lock:
            return (
                self.speed_target,
                self.soc_target,
                self.gear_target,
                self.mode_target,
            )

# --------------------------------------------------------------------------------------
# CAN-LUKIJA
# --------------------------------------------------------------------------------------

def can_reader_thread(state: DashboardState):
    if can is None:
        print("[evdash] python-can ei asennettu, CAN-lukijaa ei käynnistetä.")
        return

    try:
        bus = can.interface.Bus(channel=CAN_CHANNEL, bustype="socketcan")
        print(f"[evdash] CAN-väylä auki: {CAN_CHANNEL}")
    except Exception as e:
        print(f"[evdash] CAN-väylän avaus epäonnistui: {e}")
        return

    while state.running:
        try:
            msg = bus.recv(timeout=0.5)
            if msg is None:
                continue

            if msg.arbitration_id == CAN_ID_SPEED and len(msg.data) >= 2:
                raw = int.from_bytes(msg.data[0:2], byteorder="big", signed=False)
                speed = raw / 100.0
                state.set_from_can(speed=speed)

            elif msg.arbitration_id == CAN_ID_SOC and len(msg.data) >= 1:
                soc = msg.data[0]
                state.set_from_can(soc=float(soc))

            elif msg.arbitration_id == CAN_ID_GEAR and len(msg.data) >= 1:
                g = msg.data[0]
                gear_map = {0: "P", 1: "R", 2: "N", 3: "D"}
                gear = gear_map.get(g, "?")
                state.set_from_can(gear=gear)

            elif msg.arbitration_id == CAN_ID_MODE and len(msg.data) >= 1:
                m = msg.data[0]
                mode_map = {0: "ECO", 1: "NORMAL", 2: "SPORT"}
                mode = mode_map.get(m, "?")
                state.set_from_can(mode=mode)

        except Exception as e:
            print(f"[evdash] CAN-lukijavirhe: {e}")
            time.sleep(0.5)


def demo_driver_thread(state: DashboardState):
    """Simuloitu data, kun ajetaan --demo."""
    t0 = time.time()
    while state.running and state.demo:
        t = time.time() - t0

        speed = (math.sin(t * 0.3) * 0.5 + 0.5) * MAX_SPEED
        soc = (math.sin(t * 0.05) * 0.5 + 0.5) * 40 + 40  # ~40–80 %
        modes = ["ECO", "NORMAL", "SPORT"]
        gears = ["D", "R", "N", "P"]
        mode = modes[int((t / 10) % len(modes))]
        gear = gears[int((t / 15) % len(gears))]

        state.set_from_can(speed=speed, soc=soc, gear=gear, mode=mode)
        time.sleep(0.05)

# --------------------------------------------------------------------------------------
# PIIRTOTOIMINNOT
# --------------------------------------------------------------------------------------

def lerp(a, b, t):
    return a + (b - a) * t

def draw_vertical_gradient(surface, top_color, bottom_color):
    width, height = surface.get_size()
    for y in range(height):
        t = y / height
        r = int(lerp(top_color[0], bottom_color[0], t))
        g = int(lerp(top_color[1], bottom_color[1], t))
        b = int(lerp(top_color[2], bottom_color[2], t))
        pygame.draw.line(surface, (r, g, b), (0, y), (width, y))

def create_radial_glow(radius, color, max_alpha=120):
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        alpha = int(max_alpha * (r / radius) ** 2)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), r)
    return surf

def draw_gauge(surface, center, radius, value, max_value,
               title, unit, main_color, accent_color,
               font_large, font_small, current_time):
    cx, cy = center

    pygame.draw.circle(surface, (10, 10, 30), center, radius + 20)
    pygame.draw.circle(surface, (20, 20, 50), center, radius)

    glow = create_radial_glow(radius + 30, main_color)
    glow_rect = glow.get_rect(center=center)
    surface.blit(glow, glow_rect, special_flags=pygame.BLEND_ADD)

    start_angle_deg = 160
    end_angle_deg = 380
    angle_span = end_angle_deg - start_angle_deg

    rect = pygame.Rect(0, 0, radius * 2, radius * 2)
    rect.center = center
    track_color = (40, 40, 90)

    for thickness in range(16, 24):
        pygame.draw.arc(
            surface, track_color, rect,
            math.radians(start_angle_deg),
            math.radians(end_angle_deg),
            thickness,
        )

    t_val = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
    value_angle = start_angle_deg + angle_span * t_val

    for thickness in range(18, 22):
        pygame.draw.arc(
            surface, main_color, rect,
            math.radians(start_angle_deg),
            math.radians(value_angle),
            thickness,
        )

    sweep_pos = (current_time * 60) % angle_span + start_angle_deg
    sweep_rad = math.radians(sweep_pos)
    sx = cx + math.cos(sweep_rad) * (radius - 5)
    sy = cy + math.sin(sweep_rad) * (radius - 5)
    pygame.draw.circle(surface, accent_color, (int(sx), int(sy)), 8)

    needle_angle = math.radians(value_angle)
    nx = cx + math.cos(needle_angle) * (radius - 30)
    ny = cy + math.sin(needle_angle) * (radius - 30)
    pygame.draw.line(surface, (230, 230, 255), (cx, cy), (nx, ny), 4)
    pygame.draw.circle(surface, (15, 15, 35), (cx, cy), 14)
    pygame.draw.circle(surface, accent_color, (cx, cy), 6)

    value_text = f"{int(round(value))}"
    value_rect = font_large.get_rect(value_text)
    value_rect.center = (cx, cy - 10)
    font_large.render_to(surface, value_rect, value_text, (240, 240, 255))

    unit_rect = font_small.get_rect(unit)
    unit_rect.center = (cx, cy + 40)
    font_small.render_to(surface, unit_rect, unit, (160, 190, 255))

    title_rect = font_small.get_rect(title)
    title_rect.center = (cx, cy + radius - 40)
    font_small.render_to(surface, title_rect, title, (180, 180, 200))


def draw_center_hud(surface, rect, speed, gear, mode, soc,
                    font_speed, font_medium, font_small, t):
    x, y, w, h = rect

    card_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    draw_vertical_gradient(card_surf, (10, 10, 40), (5, 5, 20))
    pygame.draw.rect(card_surf, (40, 70, 120), (0, 0, w, h), 2, border_radius=26)

    speed_text = f"{int(round(speed))}"
    speed_rect = font_speed.get_rect(speed_text)
    speed_rect.midtop = (w // 2, 40)
    font_speed.render_to(card_surf, speed_rect, speed_text, (240, 240, 255))

    unit_text = "km/h"
    unit_rect = font_medium.get_rect(unit_text)
    unit_rect.midtop = (w // 2, speed_rect.bottom + 10)
    font_medium.render_to(card_surf, unit_rect, unit_text, (160, 190, 255))

    gear_label = "GEAR"
    gear_label_rect = font_small.get_rect(gear_label)
    gear_label_rect.topleft = (60, h - 120)
    font_small.render_to(card_surf, gear_label_rect, gear_label, (150, 170, 210))

    gear_value_rect = font_medium.get_rect(gear)
    gear_value_rect.topleft = (60, h - 90)
    font_medium.render_to(card_surf, gear_value_rect, gear, (240, 240, 255))

    mode_label = "MODE"
    mode_label_rect = font_small.get_rect(mode_label)
    mode_label_rect.topright = (w - 60, h - 120)
    font_small.render_to(card_surf, mode_label_rect, mode_label, (150, 170, 210))

    if mode == "SPORT":
        mode_color = (255, 90, 110)
    elif mode == "ECO":
        mode_color = (110, 255, 160)
    else:
        mode_color = (200, 220, 255)

    mode_value_rect = font_medium.get_rect(mode)
    mode_value_rect.topright = (w - 60, h - 90)
    font_medium.render_to(card_surf, mode_value_rect, mode, mode_color)

    bar_margin_x = 140
    bar_width = w - bar_margin_x * 2
    bar_height = 24
    bar_x = bar_margin_x
    bar_y = h - 60

    pygame.draw.rect(card_surf, (25, 30, 60),
                     (bar_x, bar_y, bar_width, bar_height),
                     border_radius=12)

    fill_t = max(0.0, min(1.0, soc / 100.0))
    fill_w = int(bar_width * fill_t)

    if soc > 60:
        fill_color = (80, 220, 120)
    elif soc > 30:
        fill_color = (220, 200, 80)
    else:
        fill_color = (230, 80, 90)

    pygame.draw.rect(card_surf, fill_color,
                     (bar_x, bar_y, fill_w, bar_height),
                     border_radius=12)

    soc_text = f"{int(round(soc))}%"
    soc_rect = font_small.get_rect(soc_text)
    soc_rect.center = (w // 2, bar_y + bar_height // 2)
    font_small.render_to(card_surf, soc_rect, soc_text, (10, 10, 20))

    scale = 1.0 + 0.01 * math.sin(t * 1.2)
    scaled_w = int(w * scale)
    scaled_h = int(h * scale)
    scaled_surf = pygame.transform.smoothscale(card_surf, (scaled_w, scaled_h))
    scaled_rect = scaled_surf.get_rect(center=(x + w // 2, y + h // 2))
    surface.blit(scaled_surf, scaled_rect)

# --------------------------------------------------------------------------------------
# PÄÄ
# --------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="evdash – Raspberry Pi EV dashboard")
    parser.add_argument("--demo", action="store_true",
                        help="Aja ilman CAN-väylää (simuloitu data)")
    args = parser.parse_args()

    state = DashboardState()
    state.demo = args.demo

    if not state.demo:
        threading.Thread(target=can_reader_thread,
                         args=(state,), daemon=True).start()
    else:
        threading.Thread(target=demo_driver_thread,
                         args=(state,), daemon=True).start()

    pygame.init()
    pygame.freetype.init()

    screen = pygame.display.set_mode(
        (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN
    )
    pygame.display.set_caption("evdash – EV Dashboard")

    font_main = pygame.freetype.SysFont("Montserrat", 64)
    font_speed = pygame.freetype.SysFont("Montserrat", 120)
    font_medium = pygame.freetype.SysFont("Montserrat", 48)
    font_small = pygame.freetype.SysFont("Montserrat", 30)

    clock = pygame.time.Clock()
    running = True
    start_time = time.time()

    while running:
        dt_ms = clock.tick(60)
        dt = dt_ms / 1000.0
        t = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_d:
                    state.demo = not state.demo
                    if state.demo:
                        threading.Thread(target=demo_driver_thread,
                                         args=(state,), daemon=True).start()

        speed_target, soc_target, gear_target, mode_target = state.get_snapshot()

        smooth_factor = min(1.0, dt * 5.0)
        state.speed_display = lerp(state.speed_display, speed_target, smooth_factor)
        state.soc_display = lerp(state.soc_display, soc_target, smooth_factor)
        state.gear_display = gear_target
        state.mode_display = mode_target

        # Boot fade -kerroin (0 -> 1 ensimmäisen sekunnin aikana)
        fade_factor = max(0.0, min(1.0,
                            (time.time() - start_time) / BOOT_FADE_SECONDS))

        # Piirretään kaikki offscreen-surfaceen ja blendataan alpha:lla
        frame = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        draw_vertical_gradient(frame, (4, 6, 20), (2, 2, 10))
        pygame.draw.rect(frame, (40, 80, 160), (0, 0, SCREEN_WIDTH, 4))

        left_center = (SCREEN_WIDTH // 4, SCREEN_HEIGHT // 2 + 80)
        right_center = (SCREEN_WIDTH * 3 // 4, SCREEN_HEIGHT // 2 + 80)
        gauge_radius = 260

        draw_gauge(
            frame,
            left_center,
            gauge_radius,
            state.speed_display,
            MAX_SPEED,
            "SPEED",
            "km/h",
            main_color=(90, 170, 255),
            accent_color=(120, 220, 255),
            font_large=font_medium,
            font_small=font_small,
            current_time=t,
        )

        draw_gauge(
            frame,
            right_center,
            gauge_radius,
            state.soc_display,
            MAX_SOC,
            "BATTERY",
            "% SOC",
            main_color=(80, 230, 160),
            accent_color=(140, 255, 200),
            font_large=font_medium,
            font_small=font_small,
            current_time=t,
        )

        center_rect = (
            SCREEN_WIDTH // 2 - 350,
            80,
            700,
            400,
        )
        draw_center_hud(
            frame,
            center_rect,
            speed=state.speed_display,
            gear=state.gear_display,
            mode=state.mode_display,
            soc=state.soc_display,
            font_speed=font_speed,
            font_medium=font_medium,
            font_small=font_small,
            t=t,
        )

        bottom_text = "evdash – ESC quit · D demo toggle"
        text_rect = font_small.get_rect(bottom_text)
        text_rect.midbottom = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 20)
        font_small.render_to(frame, text_rect, bottom_text, (120, 130, 170))

        # Boot fade: koko frame blitataan alpha-skaalattuna
        if fade_factor < 1.0:
            temp = frame.copy()
            temp.set_alpha(int(255 * fade_factor))
            screen.blit(temp, (0, 0))
        else:
            screen.blit(frame, (0, 0))

        pygame.display.flip()

    state.running = False
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()

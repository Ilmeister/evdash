import pygame
import pygame.freetype
import can
import math
import threading

WIDTH = 2000
HEIGHT = 800

# ---------------- CAN CONFIG ----------------
can_interface = 'can0'
bus = can.interface.Bus(can_interface, bustype='socketcan')

speed = 0
soc = 0
gear = "P"
drive_mode = "SPORT"

def can_listener():
    global speed, soc, gear, drive_mode

    for msg in bus:
        if msg.arbitration_id == 0x100:
            raw = int.from_bytes(msg.data[0:2], byteorder="big")
            speed = raw / 100.0

        elif msg.arbitration_id == 0x200:
            soc = msg.data[0]

        elif msg.arbitration_id == 0x310:
            g = msg.data[0]
            gear = {0:"P",1:"R",2:"N",3:"D"}.get(g, "?")

        elif msg.arbitration_id == 0x300:
            m = msg.data[0]
            drive_mode = {0:"ECO",1:"NORMAL",2:"SPORT"}.get(m, "?")


listener_thread = threading.Thread(target=can_listener, daemon=True)
listener_thread.start()

# ---------------- DRAWING UTILITIES ----------------

def draw_gauge(surface, x, y, radius, value, max_value, title, color):
    pygame.draw.circle(surface, (40,40,60), (x,y), radius, 6)

    angle = (value / max_value) * 260
    start_angle = 140
    end_angle = start_angle + angle

    for a in range(int(start_angle), int(end_angle)):
        rad = math.radians(a)
        cx = x + math.cos(rad) * radius
        cy = y + math.sin(rad) * radius
        pygame.draw.circle(surface, color, (int(cx), int(cy)), 5)

    font_large.render_to(surface, (x-80, y-40), f"{int(value)}", (255,255,255))
    font_small.render_to(surface, (x-50, y+20), title, (180,180,180))

# ---------------- MAIN ----------------

pygame.init()
pygame.display.set_caption("EV Dashboard")

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
font_large = pygame.freetype.SysFont(None, 100)
font_small = pygame.freetype.SysFont(None, 40)

clock = pygame.time.Clock()

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()

    screen.fill((12, 14, 25))

    # LEFT SPEED GAUGE
    draw_gauge(screen, 500, 400, 300, speed, 260, "km/h", (80,150,255))

    # RIGHT SOC GAUGE
    draw_gauge(screen, 1500, 400, 300, soc, 100, "% SOC", (100,255,100))

    # CENTER INFO
    font_large.render_to(screen, (900, 300), f"G: {gear}", (255,255,255))
    font_small.render_to(screen, (880, 380), f"Mode: {drive_mode}", (200,200,200))

    pygame.display.update()
    clock.tick(30)

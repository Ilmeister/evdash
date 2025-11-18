import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle

import threading
import can

Window.fullscreen = True
Window.clearcolor = (0.03, 0.03, 0.04, 1)  # dark Tesla theme


# ---------- SMOOTHING ----------
def smooth(old, new, factor=0.18):
    return old * (1 - factor) + new * factor


# ---------- BATTERY ----------
class BatteryIcon(BoxLayout):
    """Vertical EV-style battery gauge."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value = 75
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            # Border
            Color(0.3, 0.3, 0.35, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Fill
            level = max(0, min(self.value, 100)) / 100.0
            Color(0.1, 0.8, 0.3, 1)
            Rectangle(
                pos=(self.x, self.y),
                size=(self.width, self.height * level)
            )

    def set_value(self, v):
        self.value = v
        self.redraw()


# ---------- RPM BAR ----------
class BarMeter(BoxLayout):
    """Vertical RPM bar with smoothing."""

    def __init__(self, max_value=8000, **kwargs):
        super().__init__(**kwargs)
        self.max = max_value
        self.smooth_value = 0
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            # background
            Color(0.12, 0.12, 0.15, 1)
            Rectangle(pos=self.pos, size=self.size)

            # fill
            ratio = max(0, min(self.smooth_value, self.max)) / float(self.max)
            Color(0.0, 0.6, 1.0, 1)
            Rectangle(
                pos=(self.x, self.y),
                size=(self.width, self.height * ratio)
            )

    def set_value(self, v):
        self.smooth_value = smooth(self.smooth_value, v)
        self.redraw()


# ---------- MAIN APP ----------
class EVDashboard(App):

    def build(self):
        self.state = {
            "speed": 0,
            "rpm": 0,
            "soc": 70,
            "gear": "P",
            "left": False,
            "right": False,
            "low": False,
            "high": False,
            "bat_temp": 22,
            "motor_temp": 30
        }

        # Smooth UI values
        self.ui = {
            "speed": 0.0,
            "rpm": 0.0,
            "soc": 70.0
        }

        root = BoxLayout(orientation="vertical")

        # ------- TOP STATUS BAR -------
        top = BoxLayout(size_hint_y=0.12, padding=[25, 10], spacing=25)

        self.left_icon = Image(source="icons/left.png", color=(0.2,0.2,0.2,1))
        self.low_icon = Image(source="icons/low.png", color=(0.2,0.2,0.2,1))
        self.high_icon = Image(source="icons/high.png", color=(0.2,0.2,0.2,1))
        self.right_icon = Image(source="icons/right.png", color=(0.2,0.2,0.2,1))

        self.status_label = Label(
            text="READY",
            font_size="28sp",
            color=(0.7, 0.7, 0.8, 1)
        )

        top.add_widget(self.left_icon)
        top.add_widget(self.low_icon)
        top.add_widget(self.status_label)
        top.add_widget(self.high_icon)
        top.add_widget(self.right_icon)

        # ------- CENTER (Tesla style) -------
        center = BoxLayout(orientation="horizontal", padding=[25, 10], spacing=30)

        # LEFT RPM BAR
        self.rpm_bar = BarMeter(max_value=8000, size_hint_x=0.12)

        # SPEED (big number)
        speed_box = BoxLayout(orientation="vertical", size_hint_x=0.5)
        self.speed_label = Label(text="0", font_size="150sp", color=(0.95,0.95,0.98,1))
        self.speed_unit = Label(text="km/h", font_size="32sp", color=(0.5,0.6,0.8,1))

        speed_box.add_widget(self.speed_label)
        speed_box.add_widget(self.speed_unit)

        # RIGHT INFO PANEL
        info = BoxLayout(orientation="vertical", size_hint_x=0.4, spacing=20)

        # Battery icon
        self.batt_icon = BatteryIcon(size_hint_y=0.5)

        # SOC & gear
        soc_gear = BoxLayout(orientation="vertical")
        self.soc_label = Label(text="70 %", font_size="34sp", color=(0.7,0.9,0.7,1))
        self.gear_label = Label(text="P", font_size="70sp", color=(0.9,0.9,1,1))

        soc_gear.add_widget(self.soc_label)
        soc_gear.add_widget(self.gear_label)

        # Temperatures
        self.temp_label = Label(
            text="Bat 22°C   Motor 30°C",
            font_size="26sp",
            color=(0.6,0.7,0.8,1)
        )

        info.add_widget(self.batt_icon)
        info.add_widget(soc_gear)
        info.add_widget(self.temp_label)

        center.add_widget(self.rpm_bar)
        center.add_widget(speed_box)
        center.add_widget(info)

        root.add_widget(top)
        root.add_widget(center)

        # Start CAN thread
        threading.Thread(target=self.read_can, daemon=True).start()

        # UI updater
        Clock.schedule_interval(self.update_ui, 0.05)

        return root


    def update_ui(self, dt):

        # Smooth animations
        self.ui["speed"] = smooth(self.ui["speed"], self.state["speed"])
        self.ui["rpm"] = smooth(self.ui["rpm"], self.state["rpm"])
        self.ui["soc"] = smooth(self.ui["soc"], self.state["soc"])

        # Speed
        self.speed_label.text = str(int(self.ui["speed"]))

        # RPM bar
        self.rpm_bar.set_value(self.ui["rpm"])

        # SOC
        self.batt_icon.set_value(self.ui["soc"])
        self.soc_label.text = f"{int(self.ui['soc'])} %"

        # Gear
        self.gear_label.text = self.state["gear"]

        # Temperatures
        self.temp_label.text = f"Bat {self.state['bat_temp']}°C   Motor {self.state['motor_temp']}°C"

        # Status
        if self.state["gear"] == "P":
            self.status_label.text = "PARK"
        elif self.state["gear"] in ("D", "R"):
            self.status_label.text = "READY"
        else:
            self.status_label.text = self.state["gear"]

        # Icons ON/OFF
        off = (0.2,0.2,0.25,1)

        self.left_icon.color = (0,1,0,1) if self.state["left"] else off
        self.right_icon.color = (0,1,0,1) if self.state["right"] else off
        self.low_icon.color = (1,1,1,1) if self.state["low"] else off
        self.high_icon.color = (0.3,0.6,1,1) if self.state["high"] else off


    # ---------- CAN BUS ----------
    def read_can(self):
        bus = can.interface.Bus(channel="can0", bustype="socketcan")

        for msg in bus:

            if msg.arbitration_id == 0x180:        # speed
                self.state["speed"] = msg.data[0]

            elif msg.arbitration_id == 0x181:      # rpm
                self.state["rpm"] = (msg.data[0] << 8) | msg.data[1]

            elif msg.arbitration_id == 0x182:      # soc
                self.state["soc"] = msg.data[0]

            elif msg.arbitration_id == 0x183:      # gear
                idx = msg.data[0] if msg.data[0] < 4 else 0
                self.state["gear"] = ["P","R","N","D"][idx]

            elif msg.arbitration_id == 0x184:      # lights + blinkers
                flags = msg.data[0]
                self.state["left"]  = bool(flags & 1)
                self.state["right"] = bool(flags & 2)
                self.state["low"]   = bool(flags & 4)
                self.state["high"]  = bool(flags & 8)

            elif msg.arbitration_id == 0x185:      # battery temp
                self.state["bat_temp"] = msg.data[0]

            elif msg.arbitration_id == 0x186:      # motor temp
                self.state["motor_temp"] = msg.data[0]


if __name__ == "__main__":
    EVDashboard().run()

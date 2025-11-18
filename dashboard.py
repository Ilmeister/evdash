import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image

import threading
import can
import math

Window.fullscreen = True
Window.clearcolor = (0.02, 0.02, 0.03, 1)


# --- SMOOTH FUNCTION ---
def smooth(old, new, factor=0.12):
    return old*(1-factor) + new*factor


# --- MODERN ROUND GAUGE WIDGET ---
class RoundGauge(Widget):
    def __init__(self, max_value=100, thickness=18, color=(0,0.6,1), **kwargs):
        super().__init__(**kwargs)
        self.max_value = max_value
        self.value = 0
        self.smooth_value = 0
        self.thickness = thickness
        self.color = color
        self.bind(pos=self.update, size=self.update)

    def set(self, v):
        self.value = v

    def update(self, *args):
        self.smooth_value = smooth(self.smooth_value, self.value)

        cx, cy = self.center
        radius = min(self.size)/2 * 0.9
        angle = 270 * (self.smooth_value / self.max_value)

        self.canvas.clear()
        with self.canvas:
            # background ring
            Color(0.15, 0.15, 0.18)
            Line(circle=(cx, cy, radius), width=self.thickness)

            # value arc
            Color(*self.color)
            Line(circle=(cx, cy, radius, 0, angle), width=self.thickness)


# --- MAIN DASHBOARD ---
class Dashboard(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # state from CAN
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

        # smooth values for UI
        self.ui = {
            "speed": 0.0,
            "rpm": 0.0,
            "soc": 70.0,
        }

        # gauges
        self.rpm_gauge = RoundGauge(max_value=8000, color=(0.3,0.6,1))
        self.soc_gauge = RoundGauge(max_value=100, color=(0.1,0.8,0.3))

        # labels
        self.speed_label = Label(text="0", font_size="140sp", color=(1,1,1,1))
        self.unit_label = Label(text="km/h", font_size="32sp", color=(0.6,0.7,0.9,1))
        self.gear_label = Label(text="P", font_size="80sp", color=(0.9,0.9,1,1))
        self.temp_label = Label(text="Bat 22°C | Motor 30°C", font_size="26sp", color=(0.7,0.7,0.8,1))

        # icons
        self.left_icon = Image(source="icons/left.png", color=(0.25,0.25,0.3,1))
        self.low_icon  = Image(source="icons/low.png",  color=(0.25,0.25,0.3,1))
        self.high_icon = Image(source="icons/high.png", color=(0.25,0.25,0.3,1))
        self.right_icon= Image(source="icons/right.png",color=(0.25,0.25,0.3,1))

        # add everything
        self.add_widget(self.rpm_gauge)
        self.add_widget(self.soc_gauge)
        self.add_widget(self.speed_label)
        self.add_widget(self.unit_label)
        self.add_widget(self.gear_label)
        self.add_widget(self.temp_label)
        self.add_widget(self.left_icon)
        self.add_widget(self.low_icon)
        self.add_widget(self.high_icon)
        self.add_widget(self.right_icon)

        Clock.schedule_interval(self.update_ui, 0.05)


    # ---------- LAYOUT ----------
    def do_layout(self, *args):
        w, h = Window.size

        # gauge positions
        self.rpm_gauge.pos = (w*0.07, h*0.15)
        self.rpm_gauge.size = (w*0.35, w*0.35)

        self.soc_gauge.pos = (w*0.58, h*0.15)
        self.soc_gauge.size = (w*0.35, w*0.35)

        # text
        self.speed_label.pos = (w*0.43, h*0.6)
        self.unit_label.pos = (w*0.46, h*0.52)
        self.gear_label.pos = (w*0.465, h*0.42)
        self.temp_label.pos = (w*0.38, h*0.12)

        # icons top
        self.left_icon.pos  = (w*0.03, h*0.85)
        self.low_icon.pos   = (w*0.20, h*0.85)
        self.high_icon.pos  = (w*0.78, h*0.85)
        self.right_icon.pos = (w*0.90, h*0.85)

        for i in [self.left_icon, self.low_icon, self.high_icon, self.right_icon]:
            i.size = (60, 60)


    # ---------- UI UPDATE ----------
    def update_ui(self, dt):
        self.do_layout()

        # smooth
        self.ui["speed"] = smooth(self.ui["speed"], self.state["speed"])
        self.ui["rpm"]   = smooth(self.ui["rpm"],   self.state["rpm"])
        self.ui["soc"]   = smooth(self.ui["soc"],   self.state["soc"])

        # draw gauges
        self.rpm_gauge.set(self.ui["rpm"])
        self.soc_gauge.set(self.ui["soc"])

        # text updates
        self.speed_label.text = str(int(self.ui["speed"]))
        self.gear_label.text = self.state["gear"]
        self.temp_label.text = f"Bat {self.state['bat_temp']}°C | Motor {self.state['motor_temp']}°C"

        # icons ON/OFF
        off = (0.25,0.25,0.3,1)

        self.left_icon.color  = (0,1,0,1) if self.state["left"]  else off
        self.right_icon.color = (0,1,0,1) if self.state["right"] else off
        self.low_icon.color   = (1,1,1,1) if self.state["low"]   else off
        self.high_icon.color  = (0.3,0.6,1,1) if self.state["high"] else off


# ---------- MAIN APP ----------
class EVDashboardApp(App):
    def build(self):
        self.dashboard = Dashboard()
        threading.Thread(target=self.read_can, daemon=True).start()
        return self.dashboard

    def read_can(self):
        bus = can.interface.Bus(channel="can0", bustype="socketcan")

        for msg in bus:
            s = self.dashboard.state

            if msg.arbitration_id == 0x180:
                s["speed"] = msg.data[0]

            elif msg.arbitration_id == 0x181:
                s["rpm"] = (msg.data[0] << 8) | msg.data[1]

            elif msg.arbitration_id == 0x182:
                s["soc"] = msg.data[0]

            elif msg.arbitration_id == 0x183:
                idx = msg.data[0] if msg.data[0] < 4 else 0
                s["gear"] = ["P","R","N","D"][idx]

            elif msg.arbitration_id == 0x184:
                flags = msg.data[0]
                s["left"]  = bool(flags & 1)
                s["right"] = bool(flags & 2)
                s["low"]   = bool(flags & 4)
                s["high"]  = bool(flags & 8)

            elif msg.arbitration_id == 0x185:
                s["bat_temp"] = msg.data[0]

            elif msg.arbitration_id == 0x186:
                s["motor_temp"] = msg.data[0]


if __name__ == "__main__":
    EVDashboardApp().run()

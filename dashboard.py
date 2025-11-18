import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle

import threading
import can

Window.fullscreen = True
Window.clearcolor = (0.05, 0.05, 0.05, 1)


# ----- SMOOTH FILTER -----
def smooth(old, new, factor=0.15):
    return old * (1 - factor) + new * factor


class BatteryIcon(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value = 80
        self.orientation = "vertical"

    def on_size(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(0.2, 0.2, 0.2, 1)
            Rectangle(pos=self.pos, size=self.size)

            fill_height = self.height * (self.value / 100.0)
            Color(0, 0.8, 0.2, 1)
            Rectangle(pos=(self.x, self.y), size=(self.width, fill_height))

    def set_value(self, v):
        self.value = v
        self.on_size()


class BarMeter(BoxLayout):
    def __init__(self, max_value=100, **kwargs):
        super().__init__(**kwargs)
        self.max = max_value
        self.value = 0
        self.smooth_value = 0

    def on_size(self, *args):
        self.canvas.clear()
        with self.canvas:
            # background
            Color(0.15, 0.15, 0.15, 1)
            Rectangle(pos=self.pos, size=self.size)

            # foreground
            Color(0, 0.6, 1, 1)
            height = self.height * (self.smooth_value / self.max)
            Rectangle(pos=(self.x, self.y), size=(self.width, height))

    def set_value(self, newval):
        self.smooth_value = smooth(self.smooth_value, newval)
        self.on_size()


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
            "battery_temp": 22,
            "motor_temp": 30
        }

        root = BoxLayout(orientation="vertical")

        # --------- TOP ICON BAR ---------
        top = BoxLayout(size_hint_y=0.15)

        self.left_icon  = Image(source="icons/left.png",  color=(0.2,0.2,0.2,1))
        self.low_icon   = Image(source="icons/low.png",   color=(0.2,0.2,0.2,1))
        self.high_icon  = Image(source="icons/high.png",  color=(0.2,0.2,0.2,1))
        self.right_icon = Image(source="icons/right.png", color=(0.2,0.2,0.2,1))

        top.add_widget(self.left_icon)
        top.add_widget(self.low_icon)
        top.add_widget(self.high_icon)
        top.add_widget(self.right_icon)

        # --------- CENTER BLOCK ---------
        center = BoxLayout()

        # left RPM bar
        self.rpm_left = BarMeter(max_value=8000, size_hint_x=0.1)

        # speed
        self.speed_label = Label(text="0", font_size="140sp")

        # middle info block
        mid = BoxLayout(orientation="vertical")

        self.batt_icon = BatteryIcon(size_hint_y=0.5)
        self.temp_label = Label(text="Bat 22°C / Motor 30°C", font_size="30sp")
        self.gear_label = Label(text="P", font_size="100sp")

        mid.add_widget(self.batt_icon)
        mid.add_widget(self.temp_label)
        mid.add_widget(self.gear_label)

        # right RPM bar
        self.rpm_right = BarMeter(max_value=8000, size_hint_x=0.1)

        center.add_widget(self.rpm_left)
        center.add_widget(self.speed_label)
        center.add_widget(mid)
        center.add_widget(self.rpm_right)

        root.add_widget(top)
        root.add_widget(center)

        # CAN thread
        threading.Thread(target=self.read_can, daemon=True).start()

        Clock.schedule_interval(self.update_ui, 0.05)

        return root

    # ----- UI UPDATE -----
    def update_ui(self, dt):
        self.speed_label.text = str(int(self.state["speed"]))

        # Smooth RPM bars
        self.rpm_left.set_value(self.state["rpm"])
        self.rpm_right.set_value(self.state["rpm"])

        # SOC
        self.batt_icon.set_value(self.state["soc"])

        # Temps
        self.temp_label.text = f"Bat {self.state['battery_temp']}°C / Motor {self.state['motor_temp']}°C"

        # Gear
        self.gear_label.text = self.state["gear"]

        # Icons
        on = (0,1,0,1)
        off = (0.2,0.2,0.2,1)

        self.left_icon.color  = on if self.state["left"] else off
        self.right_icon.color = on if self.state["right"] else off
        self.low_icon.color   = (1,1,1,1) if self.state["low"] else off
        self.high_icon.color  = (0.3,0.5,1,1) if self.state["high"] else off

    # ----- CAN BUS READER -----
    def read_can(self):
        bus = can.interface.Bus(channel="can0", bustype="socketcan")

        for msg in bus:
            if msg.arbitration_id == 0x180:
                self.state["speed"] = msg.data[0]

            elif msg.arbitration_id == 0x181:
                self.state["rpm"] = (msg.data[0] << 8) | msg.data[1]

            elif msg.arbitration_id == 0x182:
                self.state["soc"] = msg.data[0]

            elif msg.arbitration_id == 0x183:
                self.state["gear"] = ["P","R","N","D"][msg.data[0]]

            elif msg.arbitration_id == 0x184:
                flags = msg.data[0]
                self.state["left"]  = bool(flags & 1)
                self.state["right"] = bool(flags & 2)
                self.state["low"]   = bool(flags & 4)
                self.state["high"]  = bool(flags & 8)

            elif msg.arbitration_id == 0x185:     # battery temp
                self.state["battery_temp"] = msg.data[0]

            elif msg.arbitration_id == 0x186:     # motor temp
                self.state["motor_temp"] = msg.data[0]


if __name__ == "__main__":
    EVDashboard().run()

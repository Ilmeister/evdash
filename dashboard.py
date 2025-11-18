import kivy
from kivy.app import App
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.uix.boxlayout import Boxlayout
from kivy.clock import Clock
import can
import threading
import time

Window.fullscreen = True  # Make app full-screen

class EVDashboard(App):

    def build(self):
        self.state = {
            "speed": 0,
            "soc": 0,
            "voltage": 0,
            "current": 0
        }

        self.logo_screen = Image(source="logo.png")
        self.dashboard_screen = Boxlayout(orientation='vertical')

        # Dashboard labels
        self.speed_label = Label(text="Speed: 0 km/h", font_size='40sp')
        self.soc_label = Label(text="SOC: 0%", font_size='40sp')
        self.voltage_label = Label(text="Voltage: 0 V", font_size='40sp')
        self.current_label = Label(text="Current: 0 A", font_size='40sp')

        self.dashboard_screen.add_widget(self.speed_label)
        self.dashboard_screen.add_widget(self.soc_label)
        self.dashboard_screen.add_widget(self.voltage_label)
        self.dashboard_screen.add_widget(self.current_label)

        # Show logo first
        Clock.schedule_once(self.show_dashboard, 2.5)

        # Start CAN thread
        threading.Thread(target=self.read_can, daemon=True).start()

        return self.logo_screen

    def show_dashboard(self, dt):
        self.root.clear_widgets()
        self.root.add_widget(self.dashboard_screen)

        # Update labels continuously
        Clock.schedule_interval(self.update_labels, 0.1)

    def update_labels(self, dt):
        self.speed_label.text = f"Speed: {self.state['speed']} km/h"
        self.soc_label.text = f"SOC: {self.state['soc']}%"
        self.voltage_label.text = f"Voltage: {self.state['voltage']} V"
        self.current_label.text = f"Current: {self.state['current']} A"

    def read_can(self):
        bus = can.interface.Bus(channel='can0', bustype='socketcan')

        for msg in bus:
            if msg.arbitration_id == 0x180:  # example voltage
                self.state["voltage"] = ((msg.data[0] << 8) | msg.data[1]) / 10

            elif msg.arbitration_id == 0x181:  # current
                self.state["current"] = ((msg.data[0] << 8) | msg.data[1]) / 10

            elif msg.arbitration_id == 0x182:  # SOC
                self.state["soc"] = msg.data[0]

            elif msg.arbitration_id == 0x183:  # speed
                self.state["speed"] = msg.data[0]

if __name__ == "__main__":
    EVDashboard().run()

import threading
import time

class SimulationControls:
    def __init__(self, speed: float = 1.0):
        self.speed = max(0.1, float(speed))
        self.paused = False
        self.cond = threading.Condition()

    def set_speed(self, speed: float):
        with self.cond:
            self.speed = max(0.1, float(speed))
            self.cond.notify_all()

    def pause(self):
        with self.cond:
            self.paused = True
            self.cond.notify_all()

    def resume(self):
        with self.cond:
            self.paused = False
            self.cond.notify_all()

    def wait_if_paused(self):
        with self.cond:
            while self.paused:
                self.cond.wait(timeout=0.1)


class Config:
    GRID_SIZE = 12
    MIN_VEHICLES = 20
    MAX_VEHICLES = 200
    DEFAULT_GREEN = 5
    DEFAULT_YELLOW = 2
    DEFAULT_RED = 6
    MAX_TRAFFIC_LIGHTS = 15

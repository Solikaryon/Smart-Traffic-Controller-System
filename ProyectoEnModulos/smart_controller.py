import threading
import time
import math
from typing import List, Dict
from city import Intersection

class SmartTrafficController(threading.Thread):
    """Ajusta tiempos de semáforos según congestión local cada intervalo."""
    def __init__(self, city, traffic_lights: List, interval=5):
        super().__init__(daemon=True)
        self.city = city
        self.traffic_lights = traffic_lights
        self.interval = interval
        self.running = True
        self.alpha = 0.3  # factor de suavizado
        self.history: Dict[Intersection, float] = {}
        self.min_green = 3
        self.max_green = 10
        self.min_red = 4
        self.max_red = 12

    def run(self):
        while self.running:
            time.sleep(self.interval)
            self._adapt()

    def stop(self):
        self.running = False

    def _local_pressure(self, intersection: Intersection):
        # presión = vehículos esperando + vehículos cruzados recientes ponderados
        return intersection.waiting_vehicles + (intersection.vehicles_passed * 0.05)

    def _adapt(self):
        for tl in self.traffic_lights:
            inter = tl.intersection
            p = self._local_pressure(inter)
            prev = self.history.get(inter, p)
            smoothed = prev + self.alpha * (p - prev)
            self.history[inter] = smoothed
            # Escalar green en función de presión suavizada
            pressure_norm = min(max(smoothed / 10.0, 0), 1)
            new_green = int(self.min_green + (self.max_green - self.min_green) * pressure_norm)
            new_red = int(self.max_red - (self.max_red - self.min_red) * pressure_norm)
            new_green = max(self.min_green, min(self.max_green, new_green))
            new_red = max(self.min_red, min(self.max_red, new_red))
            tl.dynamic_green = new_green
            tl.dynamic_red = new_red
            tl.dynamic_yellow = tl.yellow_time
            try:
                tl.apply_adaptive_times()
            except Exception:
                pass

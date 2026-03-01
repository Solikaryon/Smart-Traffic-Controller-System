import threading
import time
from typing import Optional
from controls import SimulationControls
from enums import TrafficLightState

class TrafficLight(threading.Thread):
    def __init__(self, intersection, green_time=5, yellow_time=2, red_time=6, controls: Optional[SimulationControls]=None):
        super().__init__(daemon=True)
        self.intersection = intersection
        self.intersection.traffic_light = self
        self.state = TrafficLightState.RED
        self.green_time = green_time
        self.yellow_time = yellow_time
        self.red_time = red_time
        self.running = True
        self.last_change = time.time()
        self.condition = threading.Condition()
        self.controls = controls or SimulationControls()
        # Control manual
        self.manual_override = False
        self.manual_state: Optional[TrafficLightState] = None
        # Ajustes adaptativos
        self.dynamic_green = green_time
        self.dynamic_yellow = yellow_time
        self.dynamic_red = red_time
        self.adaptive_enabled = False
        
        # Estadísticas
        self.state_changes = 0
        self.vehicles_passed = 0
    
    def run(self):
        while self.running:
            # Pausa global
            self.controls.wait_if_paused()
            current_time = time.time()
            elapsed = current_time - self.last_change
            
            with self.condition:
                # Respetar control manual: no cambiar automáticamente si override activo
                if not self.manual_override:
                    if self.state == TrafficLightState.GREEN and elapsed >= self.green_time:
                        self._change_state(TrafficLightState.YELLOW)
                    elif self.state == TrafficLightState.YELLOW and elapsed >= self.yellow_time:
                        self._change_state(TrafficLightState.RED)
                    elif self.state == TrafficLightState.RED and elapsed >= self.red_time:
                        self._change_state(TrafficLightState.GREEN)
                
                self.condition.notify_all()
            
            time.sleep(0.1 / self.controls.speed)
    
    def _change_state(self, new_state):
        self.state = new_state
        self.last_change = time.time()
        self.state_changes += 1
    
    def can_cross(self, direction):
        return self.state == TrafficLightState.GREEN
    
    def stop(self):
        self.running = False
    
    def update_timing(self, green=None, yellow=None, red=None):
        with self.condition:
            if green is not None:
                self.green_time = green
            if yellow is not None:
                self.yellow_time = yellow
            if red is not None:
                self.red_time = red
            # Sincronizar dinámicos cuando se actualiza manualmente
            self.dynamic_green = self.green_time
            self.dynamic_yellow = self.yellow_time
            self.dynamic_red = self.red_time

    def enable_manual(self, state: TrafficLightState):
        with self.condition:
            self.manual_override = True
            self.manual_state = state
            self.state = state
            self.last_change = time.time()
            self.condition.notify_all()

    def cycle_manual(self):
        order = [TrafficLightState.RED, TrafficLightState.GREEN, TrafficLightState.YELLOW]
        with self.condition:
            if not self.manual_override:
                self.manual_override = True
                self.manual_state = TrafficLightState.GREEN
                self.state = TrafficLightState.GREEN
            else:
                idx = order.index(self.state)
                new_state = order[(idx + 1) % len(order)]
                self.manual_state = new_state
                self.state = new_state
            self.last_change = time.time()
            self.condition.notify_all()

    def disable_manual(self):
        with self.condition:
            self.manual_override = False
            self.manual_state = None
            self.last_change = time.time()
            self.condition.notify_all()

    def apply_adaptive_times(self):
        """Actualizar tiempos internos con valores adaptativos."""
        with self.condition:
            self.green_time = self.dynamic_green
            self.yellow_time = self.dynamic_yellow
            self.red_time = self.dynamic_red
            self.condition.notify_all()

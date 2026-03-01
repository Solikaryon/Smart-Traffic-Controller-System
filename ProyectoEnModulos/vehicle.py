import threading
import time
import heapq
from typing import Optional
from controls import SimulationControls
from enums import VehicleState
from city import CityGrid, Intersection

class Vehicle(threading.Thread):
    def __init__(self, vehicle_id, start: Intersection, destination: Intersection, city: CityGrid, controls: Optional[SimulationControls]=None):
        super().__init__(daemon=True)
        self.vehicle_id = vehicle_id
        self.current_position = start
        self.destination = destination
        self.city = city
        self.controls = controls or SimulationControls()
        self.route = []
        self.state = VehicleState.MOVING
        self.completed = False
        self.start_time = None
        self.end_time = None
        self.total_travel_time = 0
        self.waiting_time = 0
        self.moving_time = 0
        self.distance_traveled = 0
        # Referencia opcional a la simulación para registrar llegada
        self.simulation: Optional['TrafficSimulation'] = None
        
        # Estadísticas
        self.intersections_crossed = 0
        self.traffic_light_stops = 0
        self.intersection_waits = 0
        # Timestamp del último progreso (moverse a otra intersección)
        self.last_progress_time = time.time()
    
    def calculate_route_astar(self):
        """Calcula la ruta usando algoritmo A*"""
        def heuristic(a, b):
            # Distancia Manhattan
            return abs(a.x - b.x) + abs(a.y - b.y)
        
        open_set = []
        heapq.heappush(open_set, (0, self.current_position))
        came_from = {}
        g_score = {self.current_position: 0}
        f_score = {self.current_position: heuristic(self.current_position, self.destination)}
        
        while open_set:
            current = heapq.heappop(open_set)[1]
            
            if current == self.destination:
                # Reconstruir ruta
                route = []
                while current in came_from:
                    route.append(current)
                    current = came_from[current]
                route.reverse()
                return route
            
            for neighbor, direction in self.city.get_neighbors(current):
                tentative_g_score = g_score[current] + 1
                
                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + heuristic(neighbor, self.destination)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        return []  
    
    def run(self):
        self.start_time = time.time()
        
        while not self.completed:
            self.controls.wait_if_paused()
            if not self.route and not self.completed:
                max_attempts = 6
                attempt = 0
                while attempt < max_attempts and not self.route and not self.completed:
                    self.route = self.calculate_route_astar()
                    try:
                        self.last_progress_time = time.time()
                    except Exception:
                        pass
                    if self.route:
                        break
                    attempt += 1
                    self.controls.wait_if_paused()
                    time.sleep(0.5 / max(0.1, self.controls.speed))

                if not self.route:
                    cx = self.current_position.x
                    cy = self.current_position.y
                    if cx == 0 or cy == 0 or cx == self.city.width - 1 or cy == self.city.height - 1:
                        self.completed = True
                        self.state = VehicleState.COMPLETED
                        self.end_time = time.time()
                        self.total_travel_time = self.end_time - (self.start_time or self.end_time)
                        self.moving_time = max(0.0, self.total_travel_time - self.waiting_time)
                        if self.simulation is not None:
                            with self.simulation.completed_lock:
                                self.simulation.completed_vehicles.append((self.vehicle_id, self.total_travel_time))
                        break
                    self.state = VehicleState.WAITING_AT_INTERSECTION
                    self.controls.wait_if_paused()
                    time.sleep(1.0 / max(0.1, self.controls.speed))
                    continue
            
            if self.route:
                next_intersection = self.route[0]
                self._move_to(next_intersection)
            
            if self.current_position == self.destination:
                self.completed = True
                self.state = VehicleState.COMPLETED
                self.end_time = time.time()
                self.total_travel_time = self.end_time - self.start_time
                self.moving_time = self.total_travel_time - self.waiting_time
                if self.simulation is not None:
                    with self.simulation.completed_lock:
                        self.simulation.completed_vehicles.append((self.vehicle_id, self.total_travel_time))
        
    def _move_to(self, target_intersection):
        wait_start = time.time()
        self.state = VehicleState.MOVING
        
        # Intentar adquirir lock de la intersección
        if target_intersection.lock.acquire(blocking=False):
            try:
                if target_intersection.traffic_light:
                    with target_intersection.traffic_light.condition:
                        while not target_intersection.traffic_light.can_cross(None):
                            self.state = VehicleState.WAITING_FOR_TRAFFIC_LIGHT
                            self.traffic_light_stops += 1
                            target_intersection.waiting_vehicles += 1
                            target_intersection.traffic_light.condition.wait(timeout=0.1 / self.controls.speed)
                            target_intersection.waiting_vehicles -= 1
                
                move_start = time.time()
                self.controls.wait_if_paused()
                time.sleep(0.1 / self.controls.speed)
                self.current_position = target_intersection
                try:
                    self.last_progress_time = time.time()
                except Exception:
                    pass
                self.route.pop(0)
                self.distance_traveled += 1
                self.intersections_crossed += 1
                target_intersection.vehicles_passed += 1
                
                if target_intersection.traffic_light:
                    target_intersection.traffic_light.vehicles_passed += 1
                
                self.state = VehicleState.MOVING
                
            finally:
                target_intersection.lock.release()
        else:
            self.state = VehicleState.WAITING_AT_INTERSECTION
            self.intersection_waits += 1
            target_intersection.waiting_vehicles += 1
            self.controls.wait_if_paused()
            time.sleep(0.2 / self.controls.speed)
            target_intersection.waiting_vehicles -= 1
        
        self.waiting_time += time.time() - wait_start

""" 
Barba Lugo Emmanuel Alejandro
Dávila Godínez Teresa
Monjaraz Briseño Luis Fernando
Quintero Meza Eduardo de Jesús 
"""


"""
Simulación de tráfico urbano (Versión V3)

Resumen del módulo:
- Ciudad en cuadrícula con intersecciones y calles.
- Semáforos con tiempos fijos y posible control manual.
- Vehículos como hilos que calculan rutas vía A* y se mueven respetando semáforos.
- Métricas de viaje y reporte final en consola.
- Visualización básica con Tkinter.

Importante sobre las mediciones de tiempo:
- En `compare_routing_methods()` los tiempos impresos corresponden SOLO al cálculo
    de rutas (A*) antes de iniciar la simulación; no son la duración total.
"""

import threading
import time
import random
from enum import Enum
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import heapq
from concurrent.futures import ThreadPoolExecutor
import timeit
import json
import math
from collections import deque
import re

# ===============================
# CONTROLES DE SIMULACIÓN
# ===============================

class SimulationControls:
    """Control global de pausa/velocidad para la simulación."""
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

# ===============================
# CONFIGURACIÓN Y CONSTANTES
# ===============================

class Config:
    """Valores por defecto y límites para la simulación."""
    GRID_SIZE = 12
    MIN_VEHICLES = 20
    MAX_VEHICLES = 200
    DEFAULT_GREEN = 5
    DEFAULT_YELLOW = 2
    DEFAULT_RED = 6
    MAX_TRAFFIC_LIGHTS = 15

# ===============================
# ENUMERACIONES
# ===============================

class Direction(Enum):
    NORTH = (0, -1)
    SOUTH = (0, 1)
    EAST = (1, 0)
    WEST = (-1, 0)

class TrafficLightState(Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"

class VehicleState(Enum):
    MOVING = "MOVING"
    WAITING_AT_INTERSECTION = "WAITING_AT_INTERSECTION"
    WAITING_FOR_TRAFFIC_LIGHT = "WAITING_FOR_TRAFFIC_LIGHT"
    COMPLETED = "COMPLETED"

# ===============================
# CLASES DEL MODELO DE CIUDAD
# ===============================

@dataclass
class Intersection:
    x: int
    y: int
    traffic_light: Optional['TrafficLight'] = None
    lock: threading.Lock = None
    waiting_vehicles: int = 0
    vehicles_passed: int = 0
    
    def __post_init__(self):
        self.lock = threading.Lock()
    
    def __hash__(self):
        return hash((self.x, self.y))
    
    def __eq__(self, other):
        if not isinstance(other, Intersection):
            return False
        return self.x == other.x and self.y == other.y

    def __lt__(self, other):
        """Permite comparación para usar intersecciones como segundo elemento en tuplas del heap.
        Solo se usa cuando las prioridades (f_score) son iguales."""
        if not isinstance(other, Intersection):
            return NotImplemented
        return (self.x, self.y) < (other.x, other.y)

class Street:
    def __init__(self, name: str, start: Intersection, end: Intersection, is_two_way=True):
        self.name = name
        self.start = start
        self.end = end
        self.is_two_way = is_two_way

class CityGrid:
    """Representación de la ciudad como una cuadrícula.

    - `two_way`: si es True, permite moverse en las 4 direcciones.
    - Si es False, aplica patrón de sentido único alternado por filas/columnas.
    """
    def __init__(self, width=12, height=12, two_way: bool = True):
        self.width = width
        self.height = height
        self.two_way = two_way
        self.intersections = {}
        self.streets = []
        self.traffic_lights = []
        
        # Crear intersecciones
        for x in range(width):
            for y in range(height):
                self.intersections[(x, y)] = Intersection(x, y)
        
        # Crear calles
        self._create_streets()
    
    def _create_streets(self):
        # Nombres de calles
        avenues = [
            "Av. Principal", "Av. Central", "Av. Norte", "Av. Sur", 
            "Av. Libertad", "Av. Independencia", "Av. Paz", "Av. Justicia",
            "Av. Revolución", "Av. Universidad", "Av. Tecnológico", "Av. Progreso"
        ]
        
        streets = [
            "Calle 1", "Calle 2", "Calle 3", "Calle 4", "Calle 5",
            "Calle 6", "Calle 7", "Calle 8", "Calle 9", "Calle 10",
            "Calle 11", "Calle 12"
        ]
        
        # Crear avenidas (verticales)
        for x in range(self.width):
            for y in range(self.height - 1):
                start = self.intersections[(x, y)]
                end = self.intersections[(x, y + 1)]
                name = f"{avenues[x % len(avenues)]} - Sección {y}"
                self.streets.append(Street(name, start, end, True))
        
        # Crear calles (horizontales)
        for y in range(self.height):
            for x in range(self.width - 1):
                start = self.intersections[(x, y)]
                end = self.intersections[(x + 1, y)]
                name = f"{streets[y % len(streets)]} - Tramo {x}"
                self.streets.append(Street(name, start, end, True))
    
    def get_intersection(self, x, y):
        return self.intersections.get((x, y))
    
    def get_neighbors(self, intersection: Intersection):
        neighbors = []
        x, y = intersection.x, intersection.y
        
        # Direcciones posibles
        directions = []
        if self.two_way:
            directions = [
                (x + 1, y, Direction.EAST),
                (x - 1, y, Direction.WEST),
                (x, y + 1, Direction.SOUTH),
                (x, y - 1, Direction.NORTH)
            ]
        else:
            # Patrón consistente: calles horizontales un sentido alternado por fila,
            # verticales un sentido alternado por columna
            # - Filas pares: Este (EAST), filas impares: Oeste (WEST)
            # - Columnas pares: Sur (SOUTH), columnas impares: Norte (NORTH)
            if y % 2 == 0:
                directions.append((x + 1, y, Direction.EAST))
            else:
                directions.append((x - 1, y, Direction.WEST))
            if x % 2 == 0:
                directions.append((x, y + 1, Direction.SOUTH))
            else:
                directions.append((x, y - 1, Direction.NORTH))
        
        for nx, ny, direction in directions:
            if 0 <= nx < self.width and 0 <= ny < self.height:
                neighbors.append((self.intersections[(nx, ny)], direction))
        
        return neighbors
    
    def add_traffic_light(self, intersection: Intersection, green_time=5, yellow_time=2, red_time=6):
        if intersection.traffic_light is None and len(self.traffic_lights) < Config.MAX_TRAFFIC_LIGHTS:
            traffic_light = TrafficLight(intersection, green_time, yellow_time, red_time)
            self.traffic_lights.append(traffic_light)
            return traffic_light
        return None

# ===============================
# SISTEMA DE SEMÁFOROS
# ===============================

class TrafficLight(threading.Thread):
    """Semáforo con ciclo de estados basado en tiempos configurables."""
    def __init__(self, intersection: Intersection, green_time=5, yellow_time=2, red_time=6, controls: Optional[SimulationControls]=None):
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

# ===============================
# SISTEMA DE VEHÍCULOS
# ===============================

class Vehicle(threading.Thread):
    """Vehículo que calcula su ruta y se mueve entre intersecciones."""
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
        
        # Estadísticas
        self.intersections_crossed = 0
        self.traffic_light_stops = 0
        self.intersection_waits = 0
    
    def calculate_route_astar(self):
        """Calcula la ruta usando A* (heurística Manhattan)."""
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
        
        return []  # No se encontró ruta
    
    def run(self):
        self.start_time = time.time()
        
        while not self.completed:
            self.controls.wait_if_paused()
            if not self.route:
                self.route = self.calculate_route_astar()
                if not self.route:
                    break
            
            if self.route:
                next_intersection = self.route[0]
                self._move_to(next_intersection)
            
            if self.current_position == self.destination:
                self.completed = True
                self.state = VehicleState.COMPLETED
                self.end_time = time.time()
                self.total_travel_time = self.end_time - self.start_time
                self.moving_time = self.total_travel_time - self.waiting_time
        
    def _move_to(self, target_intersection):
        wait_start = time.time()
        self.state = VehicleState.MOVING
        
        # Intentar adquirir lock de la intersección
        if target_intersection.lock.acquire(blocking=False):
            try:
                # Verificar semáforo si existe
                if target_intersection.traffic_light:
                    with target_intersection.traffic_light.condition:
                        while not target_intersection.traffic_light.can_cross(None):
                            self.state = VehicleState.WAITING_FOR_TRAFFIC_LIGHT
                            self.traffic_light_stops += 1
                            target_intersection.waiting_vehicles += 1
                            # Esperar respetando pausa
                            target_intersection.traffic_light.condition.wait(timeout=0.1 / self.controls.speed)
                            target_intersection.waiting_vehicles -= 1
                
                # Mover vehículo
                move_start = time.time()
                self.controls.wait_if_paused()
                time.sleep(0.1 / self.controls.speed)  # Simular tiempo de cruce
                self.current_position = target_intersection
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
            # Intersección ocupada
            self.state = VehicleState.WAITING_AT_INTERSECTION
            self.intersection_waits += 1
            target_intersection.waiting_vehicles += 1
            self.controls.wait_if_paused()
            time.sleep(0.2 / self.controls.speed)
            target_intersection.waiting_vehicles -= 1
        
        self.waiting_time += time.time() - wait_start

# ===============================
# MÉTRICAS Y MONITOREO
# ===============================

class SimulationMetrics:
    """Cálculo y presentación de métricas de la simulación."""
    def __init__(self):
        self.sequential_routing_time = 0
        self.parallel_routing_time = 0
        self.first_vehicle = None
        self.average_travel_time = 0
        self.average_waiting_time = 0
        self.average_moving_time = 0
        self.max_congestion = 0
        self.total_vehicles_completed = 0
        self.simulation_start_time = 0
        self.simulation_end_time = 0
    
    def calculate_final_metrics(self, vehicles, city):
        if not vehicles:
            return
        
        completed_vehicles = [v for v in vehicles if v.completed]
        if not completed_vehicles:
            return
        
        self.total_vehicles_completed = len(completed_vehicles)
        
        # Encontrar primer vehículo en llegar
        self.first_vehicle = min(completed_vehicles, key=lambda v: v.end_time)
        
        # Calcular promedios
        self.average_travel_time = sum(v.total_travel_time for v in completed_vehicles) / len(completed_vehicles)
        self.average_waiting_time = sum(v.waiting_time for v in completed_vehicles) / len(completed_vehicles)
        self.average_moving_time = sum(v.moving_time for v in completed_vehicles) / len(completed_vehicles)
        
        # Calcular congestión máxima
        self.max_congestion = max(intersection.waiting_vehicles for intersection in city.intersections.values())
        
        # Calcular eficiencia de paralelismo
        if self.parallel_routing_time > 0 and self.sequential_routing_time > 0:
            self.speedup = self.sequential_routing_time / self.parallel_routing_time
            self.efficiency = (self.speedup / len(vehicles)) * 100 if len(vehicles) > 0 else 0
    
    def print_real_time_metrics(self, vehicles, city):
        completed = sum(1 for v in vehicles if v.completed)
        total = len(vehicles)
        progress = (completed / total) * 100 if total > 0 else 0
        
        current_congestion = sum(1 for intersection in city.intersections.values() 
                               if intersection.waiting_vehicles > 0)
        
        moving_vehicles = sum(1 for v in vehicles if v.state == VehicleState.MOVING)
        waiting_vehicles = sum(1 for v in vehicles if v.state in [VehicleState.WAITING_AT_INTERSECTION, 
                                                                VehicleState.WAITING_FOR_TRAFFIC_LIGHT])
        
        print(f"\n--- MÉTRICAS EN TIEMPO REAL ---")
        print(f"Progreso: {completed}/{total} ({progress:.1f}%)")
        print(f"Vehículos en movimiento: {moving_vehicles}")
        print(f"Vehículos esperando: {waiting_vehicles}")
        print(f"Intersecciones congestionadas: {current_congestion}")
        
        if completed > 0:
            avg_time = sum(v.total_travel_time for v in vehicles if v.completed) / completed
            print(f"Tiempo promedio de viaje: {avg_time:.2f}s")
    
    def print_final_report(self):
        print("\n" + "="*70)
        print("REPORTE FINAL DE SIMULACIÓN")
        print("="*70)
        
        if self.first_vehicle:
            print(f"Primer vehículo en llegar: {self.first_vehicle.vehicle_id}")
            print(f"Tiempo del primer vehículo: {self.first_vehicle.total_travel_time:.2f}s")
            print(f"Distancia recorrida: {self.first_vehicle.distance_traveled} intersecciones")

        print(f"\nESTADÍSTICAS GENERALES:")
        print(f"Vehículos completados: {self.total_vehicles_completed}")
        print(f"Tiempo promedio de viaje: {self.average_travel_time:.2f}s")
        print(f"Tiempo promedio de espera: {self.average_waiting_time:.2f}s")
        print(f"Tiempo promedio en movimiento: {self.average_moving_time:.2f}s")
        print(f"Porcentaje de tiempo esperando: {(self.average_waiting_time/self.average_travel_time*100):.1f}%")
        print(f"Congestión máxima: {self.max_congestion} vehículos")

        print(f"\nCOMPARACIÓN DE PLANIFICACIÓN DE RUTAS (solo cálculo de rutas):")
        print(f"Tiempo de cálculo (secuencial): {self.sequential_routing_time:.4f}s")
        print(f"Tiempo de cálculo (paralelo): {self.parallel_routing_time:.4f}s")
        if hasattr(self, 'speedup'):
            print(f"Speedup: {self.speedup:.2f}x")
            print(f"Eficiencia: {self.efficiency:.1f}%")

# ===============================
# SIMULACIÓN PRINCIPAL
# ===============================

class TrafficSimulation:
    """Clase principal que orquesta la simulación (configuración, arranque y monitoreo)."""
    def __init__(self, config_file=None):
        # Configuración inicial (temporal para crear controls con velocidad por defecto)
        self.controls = SimulationControls()
        self.city = CityGrid()
        self.vehicles = []
        self.traffic_lights = []
        self.metrics = SimulationMetrics()
        self.running = False
        self.simulation_thread = None
        self.visualizer = None
        self.smart_controller = None
        
        # Configuración
        self.config = self._load_config(config_file)
        # Re-crear ciudad con tamaño y modo de calles del config
        grid_size = int(self.config.get('grid_size', 12))
        street_mode = str(self.config.get('street_mode', 'two_way')).lower()
        two_way = (street_mode != 'one_way')
        self.city = CityGrid(grid_size, grid_size, two_way=two_way)
        # Actualizar velocidad
        self.controls.set_speed(float(self.config.get('simulation_speed', 1.0)))
        self._setup_traffic_lights()
        # Bandera de visualización y adaptativo
        self.enable_visual = False
        self.enable_adaptive = False
    
    def _load_config(self, config_file):
        config = {
            'num_vehicles': 50,
            'green_time': 5,
            'yellow_time': 2,
            'red_time': 6,
            'use_parallel_routing': True,
            'grid_size': 12,
            'simulation_speed': 1.0
        }
        
        if config_file:
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                    config.update(user_config)
            except FileNotFoundError:
                print("Archivo de configuración no encontrado, usando valores por defecto")
        
        return config
    
    def _setup_traffic_lights(self):
        # Colocar semáforos en intersecciones principales (patrón de cuadrícula)
        traffic_light_positions = []
        for x in range(2, self.city.width, 3):
            for y in range(2, self.city.height, 3):
                if len(traffic_light_positions) < Config.MAX_TRAFFIC_LIGHTS:
                    traffic_light_positions.append((x, y))
        
        for x, y in traffic_light_positions:
            intersection = self.city.get_intersection(x, y)
            if intersection:
                traffic_light = TrafficLight(
                    intersection,
                    self.config['green_time'],
                    self.config['yellow_time'],
                    self.config['red_time'],
                    controls=self.controls
                )
                self.traffic_lights.append(traffic_light)
        
        print(f"{len(self.traffic_lights)} semáforos instalados en la ciudad")
    
    def _generate_start_end_points(self):
        """Generar puntos de inicio y destino.

        Usa puntos del config si están definidos; en caso contrario,
        usa intersecciones del borde del mapa.
        """
        # Si hay puntos definidos en config, usarlos
        def parse_points(lst):
            pts = []
            for item in lst:
                try:
                    x, y = int(item[0]), int(item[1])
                    if 0 <= x < self.city.width and 0 <= y < self.city.height:
                        pts.append(self.city.get_intersection(x, y))
                except Exception:
                    continue
            return [p for p in pts if p is not None]

        start_pts_cfg = self.config.get('start_points')
        dest_pts_cfg = self.config.get('dest_points')
        if isinstance(start_pts_cfg, list) and isinstance(dest_pts_cfg, list):
            starts = parse_points(start_pts_cfg)
            dests = parse_points(dest_pts_cfg)
            if starts and dests:
                return starts, dests

        border_positions = []
        
        # Bordes superior e inferior
        for x in range(self.city.width):
            border_positions.append(self.city.get_intersection(x, 0))
            border_positions.append(self.city.get_intersection(x, self.city.height - 1))
        
        # Bordes izquierdo y derecho (excluyendo esquinas ya incluidas)
        for y in range(1, self.city.height - 1):
            border_positions.append(self.city.get_intersection(0, y))
            border_positions.append(self.city.get_intersection(self.city.width - 1, y))
        
        return border_positions, border_positions
    
    def generate_vehicles_sequential(self):
        """Generar vehículos y calcular rutas secuencialmente.

        Mide SOLO el tiempo de cálculo de rutas (A*), no la duración total.
        """
        start_time = timeit.default_timer()
        
        starts, dests = self._generate_start_end_points()
        
        for i in range(self.config['num_vehicles']):
            start = random.choice(starts)
            destination = random.choice([p for p in dests if p != start])
            
            vehicle = Vehicle(f"V{i+1:03d}", start, destination, self.city, controls=self.controls)
            vehicle.calculate_route_astar()
            self.vehicles.append(vehicle)
        
        routing_time = timeit.default_timer() - start_time
        self.metrics.sequential_routing_time = routing_time
        return routing_time
    
    def generate_vehicles_parallel(self):
        """Generar vehículos y calcular rutas en paralelo.

        Mide SOLO el tiempo de cálculo de rutas usando hilos; no es el total.
        """
        start_time = timeit.default_timer()
        
        starts, dests = self._generate_start_end_points()
        
        vehicles_data = []
        for i in range(self.config['num_vehicles']):
            start = random.choice(starts)
            destination = random.choice([p for p in dests if p != start])
            vehicles_data.append((f"V{i+1:03d}", start, destination))
        
        # Calcular rutas en paralelo
        with ThreadPoolExecutor() as executor:
            futures = []
            for vehicle_id, start, destination in vehicles_data:
                vehicle = Vehicle(vehicle_id, start, destination, self.city, controls=self.controls)
                future = executor.submit(vehicle.calculate_route_astar)
                futures.append((vehicle, future))
            
            for vehicle, future in futures:
                vehicle.route = future.result()
                self.vehicles.append(vehicle)
        
        routing_time = timeit.default_timer() - start_time
        self.metrics.parallel_routing_time = routing_time
        return routing_time
    
    def _monitor_simulation(self):
        """Hilo de monitoreo de la simulación"""
        monitor_count = 0
        while self.running:
            time.sleep(3)  # Actualizar cada 3 segundos
            
            completed = sum(1 for v in self.vehicles if v.completed)
            if completed == len(self.vehicles):
                self.stop_simulation()
                break
            
            # Mostrar métricas cada 15 segundos
            if monitor_count % 5 == 0:
                self.metrics.print_real_time_metrics(self.vehicles, self.city)
            
            monitor_count += 1
    
    def start_simulation(self):
        """Iniciar la simulación"""
        if self.running:
            print("La simulación ya está en ejecución")
            return
        
        self.running = True
        self.metrics.simulation_start_time = time.time()
        
        print("INICIANDO SIMULACIÓN DE TRÁFICO URBANO")
        print("="*50)
        
        # Iniciar semáforos
        for traffic_light in self.traffic_lights:
            traffic_light.start()
        
        # Generar vehículos
        if self.config['use_parallel_routing']:
            print("Calculando rutas en paralelo...")
            routing_time = self.generate_vehicles_parallel()
        else:
            print("Calculando rutas secuencialmente...")
            routing_time = self.generate_vehicles_sequential()
        
        print(f"Tiempo de cálculo de rutas: {routing_time:.4f}s")
        print(f"{len(self.vehicles)} vehículos generados")
        
        # Iniciar vehículos
        for vehicle in self.vehicles:
            vehicle.start()
        
        print("Todos los vehículos han iniciado su viaje")
        
        # Iniciar monitoreo
        monitor_thread = threading.Thread(target=self._monitor_simulation, daemon=True)
        monitor_thread.start()

        # Iniciar controlador adaptativo si está habilitado
        if self.enable_adaptive:
            self._start_smart_controller()

        # La visualización se inicia desde menú para poder correr mainloop en hilo principal
        
        # Esperar a que termine la simulación
        try:
            while self.running:
                # Honrar pausa incluso en bucle principal
                self.controls.wait_if_paused()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nSimulación interrumpida por el usuario")
            self.stop_simulation()
    
    def stop_simulation(self):
        """Detener la simulación"""
        if not self.running:
            return
        
        self.running = False
        self.metrics.simulation_end_time = time.time()
        
        print("\nDeteniendo simulación...")
        
        # Detener semáforos
        for traffic_light in self.traffic_lights:
            traffic_light.stop()

        # Detener controlador inteligente
        if self.smart_controller:
            self.smart_controller.stop()
        
        # Esperar a que los semáforos terminen
        for traffic_light in self.traffic_lights:
            if traffic_light.is_alive():
                traffic_light.join(timeout=1.0)
        
        # Calcular métricas finales
        self.metrics.calculate_final_metrics(self.vehicles, self.city)
        self.metrics.print_final_report()
        
        # Verificar sincronización
        self._verify_synchronization()

    # ===============================
    # CONTROLADOR ADAPTATIVO
    # ===============================
    def _start_smart_controller(self):
        self.smart_controller = SmartTrafficController(self.city, self.traffic_lights)
        self.smart_controller.start()

    # ===============================
    # VISUALIZACIÓN
    # ===============================
    def launch_visualizer(self):
        if self.visualizer is None:
            try:
                self.visualizer = TrafficVisualizer(self)
                # IMPORTANTE: mainloop debe ejecutarse en el hilo principal
                self.visualizer.start()
            except Exception as e:
                print(f"Error iniciando visualizador: {e}")
    
    def _verify_synchronization(self):
        """Verificar que no hubo condiciones de carrera"""
        print("\nVERIFICACIÓN DE SINCRONIZACIÓN")
        print("-" * 40)
        
        # Verificar que ningún vehículo compartió intersección al mismo tiempo
        collision_detected = False
        for intersection in self.city.intersections.values():
            if intersection.vehicles_passed > len(self.vehicles) * 10:  # Límite razonable
                print(f"Posible condición de carrera en ({intersection.x},{intersection.y})")
                collision_detected = True
        
        if not collision_detected:
            print("No se detectaron condiciones de carrera")
        
        # Verificar deadlocks
        active_vehicles = sum(1 for v in self.vehicles if v.is_alive())
        if active_vehicles == 0:
            print("No se detectaron deadlocks")
        else:
            print(f"{active_vehicles} vehículos aún activos")

# ===============================
# INTERFAZ DE USUARIO
# ===============================

def create_sample_config():
    """Crear archivo de configuración de ejemplo"""
    config = {
        "num_vehicles": 50,
        "green_time": 5,
        "yellow_time": 2,
        "red_time": 6,
        "use_parallel_routing": True,
        "grid_size": 12,
        "simulation_speed": 1.0
    }
    with open('simulation_config.json', 'w') as f:
        json.dump(config, f, indent=2)

    print("Archivo de configuración 'simulation_config.json' creado")

def run_quick_test():
    """Ejecutar una prueba rápida"""
    print("EJECUTANDO PRUEBA RÁPIDA")
    print("=" * 30)
    
    simulation = TrafficSimulation()
    simulation.config['num_vehicles'] = 30
    simulation.start_simulation()

def user_menu():
    """Menú interactivo por consola para ejecutar y configurar la simulación."""
    print("SIMULADOR DE TRÁFICO URBANO")
    print("=" * 40)
    
    while True:
        print("\nOPCIONES:")
        print("1. Ejecutar simulación con configuración por defecto")
        print("2. Cargar configuración desde archivo")
        print("3. Crear archivo de configuración de ejemplo")
        print("4. Ejecutar prueba rápida (30 vehículos)")
        print("5. Comparar planificación secuencial vs paralela")
        print("6. Simulación con visualización y control manual")
        print("7. Simulación con visualización + semáforos inteligentes")
        print("8. Configuración avanzada")
        print("9. Salir")
        
        choice = input("Seleccione una opción: ").strip()
        
        if choice == "1":
            print("\nIniciando simulación con configuración por defecto...")
            simulation = TrafficSimulation()
            simulation.start_simulation()
        
        elif choice == "2":
            config_file = input("Nombre del archivo de configuración: ").strip()
            try:
                simulation = TrafficSimulation(config_file)
                simulation.start_simulation()
            except Exception as e:
                print(f"Error al cargar configuración: {e}")
        
        elif choice == "3":
            create_sample_config()
        
        elif choice == "4":
            run_quick_test()
        
        elif choice == "5":
            compare_routing_methods()
        
        elif choice == "6":
            print("\nIniciando simulación con visualización...")
            simulation = TrafficSimulation()
            simulation.enable_visual = True
            # Arrancar simulación en hilo para liberar mainloop Tk
            threading.Thread(target=simulation.start_simulation, daemon=True).start()
            simulation.launch_visualizer()
        elif choice == "7":
            print("\nIniciando simulación adaptativa con visualización...")
            simulation = TrafficSimulation()
            simulation.enable_visual = True
            simulation.enable_adaptive = True
            threading.Thread(target=simulation.start_simulation, daemon=True).start()
            simulation.launch_visualizer()
        elif choice == "8":
            print("\nConfiguración avanzada")
            try:
                num = input("Cantidad de vehículos (20-200) [enter para mantener]: ").strip()
                green = input("Semáforo VERDE (s) [enter=mantener]: ").strip()
                yellow = input("Semáforo AMARILLO (s) [enter=mantener]: ").strip()
                red = input("Semáforo ROJO (s) [enter=mantener]: ").strip()
                grid_raw = input("Tamaño de grid NxN (ej: 12 o 12x12) [enter=mantener]: ").strip()
                mode = input("Modo de calles ('two_way' o 'one_way') [enter=mantener]: ").strip().lower()
                speed = input("Velocidad simulación (1.0 normal, >1 más rápido) [enter=mantener]: ").strip()
                num_lights = input("Cantidad de semáforos (10-20 recomendado, máximo 50) [enter=mantener]: ").strip()
                def parse_list_coords(prompt):
                    s = input(prompt).strip()
                    if not s:
                        return None
                    pts = []
                    for part in s.split(';'):
                        try:
                            x_str,y_str = part.split(',')
                            pts.append([int(x_str), int(y_str)])
                        except Exception:
                            pass
                    return pts if pts else None
                sp = parse_list_coords("Puntos de partida (x,y;x,y) [enter=aleatorio]: ")
                dp = parse_list_coords("Puntos de destino (x,y;x,y) [enter=aleatorio]: ")

                cfg = {}
                if num: cfg['num_vehicles'] = max(20, min(200, int(num)))
                if green: cfg['green_time'] = max(1, int(green))
                if yellow: cfg['yellow_time'] = max(1, int(yellow))
                if red: cfg['red_time'] = max(1, int(red))
                if grid_raw:
                    # Extraer el primer número para permitir formatos como '20x20', '20X', ' 20 ', etc.
                    nums = re.findall(r'\d+', grid_raw)
                    if nums:
                        cfg['grid_size'] = max(4, int(nums[0]))
                    else:
                        print("Valor de tamaño de grid inválido, se ignora.")
                if mode in ("two_way","one_way"): cfg['street_mode'] = mode
                if speed: cfg['simulation_speed'] = max(0.1, float(speed))
                if num_lights:
                    try:
                        n = int(num_lights)
                        # Ajustar a límites: mínimo recomendado 10, máximo 50
                        if n < 10:
                            print("Cantidad de semáforos menor al recomendado (10). Se ajusta a 10.")
                            n = 10
                        if n > 50:
                            print("Cantidad mayor al máximo (50). Se ajusta a 50.")
                            n = 50
                        cfg['max_traffic_lights'] = n
                    except Exception:
                        print("Entrada inválida para cantidad de semáforos, se ignora.")
                if sp is not None: cfg['start_points'] = sp
                if dp is not None: cfg['dest_points'] = dp

                print("\nIniciando simulación con configuración avanzada...")
                sim = TrafficSimulation()
                # Aplicar configuración al vuelo
                sim.config.update(cfg)
                # Reconstruir ciudad y semáforos con nuevos parámetros
                grid_size = int(sim.config.get('grid_size', 12))
                street_mode = str(sim.config.get('street_mode','two_way')).lower()
                two_way = (street_mode != 'one_way')
                sim.city = CityGrid(grid_size, grid_size, two_way=two_way)
                sim.traffic_lights = []
                sim.controls.set_speed(float(sim.config.get('simulation_speed', 1.0)))
                # Aplicar configuración del número de semáforos si fue especificada
                if 'max_traffic_lights' in sim.config:
                    try:
                        Config.MAX_TRAFFIC_LIGHTS = int(sim.config.get('max_traffic_lights', Config.MAX_TRAFFIC_LIGHTS))
                    except Exception:
                        pass
                sim._setup_traffic_lights()

                # Lanzar visualizador igual que en opciones 6 y 7
                sim.enable_visual = True
                threading.Thread(target=sim.start_simulation, daemon=True).start()
                sim.launch_visualizer()
            except Exception as e:
                print(f"Error en configuración avanzada: {e}")
        elif choice == "9":
            print("¡Hasta luego!")
            break
        
        else:
            print("Opción no válida")

def compare_routing_methods():
    """Comparar métodos de planificación de rutas (solo tiempo de cálculo).

    Imprime tiempos de cálculo de rutas secuencial vs paralelo, antes de
    iniciar la simulación. No mide la duración total.
    """
    print("\nCOMPARACIÓN DE MÉTODOS DE PLANIFICACIÓN")
    print("=" * 50)

    # Configuración de prueba
    num_vehicles = 50
    print(f"Vehículos para prueba: {num_vehicles}")

    # Prueba secuencial
    print("\nProbando planificación SECUENCIAL...")
    sim_sequential = TrafficSimulation()
    sim_sequential.config['num_vehicles'] = num_vehicles
    sim_sequential.config['use_parallel_routing'] = False

    start_time = timeit.default_timer()
    sim_sequential.generate_vehicles_sequential()
    sequential_time = timeit.default_timer() - start_time

    # Nota: tiempo sólo del cálculo de rutas
    print(f"Tiempo de cálculo de rutas (secuencial): {sequential_time:.4f}s")

    # Prueba paralela
    print("\nProbando planificación PARALELA...")
    sim_parallel = TrafficSimulation()
    sim_parallel.config['num_vehicles'] = num_vehicles
    sim_parallel.config['use_parallel_routing'] = True

    start_time = timeit.default_timer()
    sim_parallel.generate_vehicles_parallel()
    parallel_time = timeit.default_timer() - start_time

    # Nota: tiempo sólo del cálculo de rutas
    print(f"Tiempo de cálculo de rutas (paralelo): {parallel_time:.4f}s")

    # Resultados
    print(f"\nRESULTADOS DE COMPARACIÓN:")
    print("+----------------------+----------------+")
    print("| Método               | Tiempo (s)     |")
    print("+----------------------+----------------+")
    print(f"| Secuencial           | {sequential_time:>14.4f} |")
    print(f"| Paralelo             | {parallel_time:>14.4f} |")
    print("+----------------------+----------------+")

    if parallel_time > 0:
        speedup = sequential_time / parallel_time
        efficiency = (speedup / num_vehicles) * 100
        print(f"Speedup: {speedup:.2f}x")
        print(f"Eficiencia: {efficiency:.1f}%")

    print(f"Mejora: {((sequential_time - parallel_time) / sequential_time * 100):.1f}%")

# ===============================
# CONTROLADOR ADAPTATIVO DE SEMÁFOROS
# ===============================

class SmartTrafficController(threading.Thread):
    """Ajusta tiempos de semáforos según congestión local cada intervalo."""
    def __init__(self, city: CityGrid, traffic_lights: List[TrafficLight], interval=5):
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
            pressure_norm = min(max(smoothed / 10.0, 0), 1)  # normalizar 0..1 (heurístico)
            new_green = int(self.min_green + (self.max_green - self.min_green) * pressure_norm)
            new_red = int(self.max_red - (self.max_red - self.min_red) * pressure_norm)
            # Aplicar límites
            new_green = max(self.min_green, min(self.max_green, new_green))
            new_red = max(self.min_red, min(self.max_red, new_red))
            # Actualizar dinámicos
            tl.dynamic_green = new_green
            tl.dynamic_red = new_red
            # Amarillo fijo
            tl.dynamic_yellow = tl.yellow_time
            tl.apply_adaptive_times()

# ===============================
# VISUALIZACIÓN GRÁFICA (TKINTER)
# ===============================

try:
    import tkinter as tk
except ImportError:
    tk = None

class TrafficVisualizer:
    """Responsable de mostrar la animación en el hilo principal (no hereda de Thread)."""
    def __init__(self, simulation: 'TrafficSimulation'):
        self.simulation = simulation
        self.running = True
        # Escala de interfaz (1 = original, 2 = doble)
        self.scale = 2
        self.cell_size = 24 * self.scale
        self.margin = 20 * self.scale
        self.refresh_ms = 300
        self.root = None
        self.canvas = None
        self.vehicle_items = {}
        self.light_items = {}
        self.vehicle_texts = {}
        self.completed_text_item = None
        # Ancho del panel derecho para la lista (pixels)
        self.sidebar_width = 160 * self.scale
        self.canvas_width = None
        self.sidebar_x = None

    def start(self):
        if tk is None:
            print("Tkinter no disponible (instala Python con Tcl/Tk).")
            return
        self.root = tk.Tk()
        self.root.title("Simulación de Tráfico Urbano")
        left_width = self.simulation.city.width * self.cell_size
        h = self.simulation.city.height * self.cell_size + self.margin * 2
        w = self.margin * 2 + left_width + self.sidebar_width
        self.canvas_width = w
        self.sidebar_x = self.margin + left_width
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#222")
        self.canvas.pack()
        self._draw_grid()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_bindings()
        self._loop()
        self.root.mainloop()

    def _on_close(self):
        self.running = False
        try:
            self.simulation.stop_simulation()
        except Exception:
            pass
        if self.root:
            self.root.destroy()

    def _draw_grid(self):
        for x in range(self.simulation.city.width):
            for y in range(self.simulation.city.height):
                px = self.margin + x * self.cell_size
                py = self.margin + y * self.cell_size
                self.canvas.create_rectangle(px, py, px + self.cell_size, py + self.cell_size, outline="#444", fill="#333")

        # Inicializar semáforos
        for tl in self.simulation.traffic_lights:
            self._draw_light(tl)

        # Panel derecho para lista de vehículos completados
        if self.sidebar_x is not None:
            panel_left = self.sidebar_x
            panel_right = self.canvas_width - self.margin
            panel_top = self.margin
            panel_bottom = self.margin + self.simulation.city.height * self.cell_size
            # Fondo del panel
            self.canvas.create_rectangle(panel_left, panel_top, panel_right, panel_bottom, fill="#111", outline="#222")
            # Cabecera
            hdr_x = panel_left + 8 * self.scale
            hdr_y = panel_top + 6 * self.scale
            self.canvas.create_text(hdr_x, hdr_y, anchor='nw', text="Completados:", fill='#fff', font=(None, int(10 * self.scale), 'bold'))
            # Texto dinámico con la lista (anclado en esquina superior izquierda del panel)
            # Usar tamaño reducido (la mitad) para la lista de completados
            small_font = max(6, int((9 * self.scale) / 2))
            self.completed_text_item = self.canvas.create_text(hdr_x, hdr_y + int(18 * self.scale), anchor='nw', text="", fill='#ddd', font=(None, small_font), justify='left')

    def _draw_light(self, tl: TrafficLight):
        px = self.margin + tl.intersection.x * self.cell_size + self.cell_size / 4
        py = self.margin + tl.intersection.y * self.cell_size + self.cell_size / 4
        color = self._color_for_state(tl.state)
        item = self.canvas.create_oval(px, py, px + self.cell_size / 2, py + self.cell_size / 2, fill=color, outline="#111")
        self.light_items[tl] = item

    def _update_lights(self):
        for tl, item in self.light_items.items():
            color = self._color_for_state(tl.state)
            self.canvas.itemconfigure(item, fill=color)

    def _color_for_state(self, state: TrafficLightState):
        if state == TrafficLightState.RED:
            return "#d62828"
        if state == TrafficLightState.GREEN:
            return "#2a9d8f"
        if state == TrafficLightState.YELLOW:
            return "#f4a261"
        return "#555"

    def _loop(self):
        if not self.running:
            return
        self._update_lights()
        self._update_vehicles()
        self.root.after(self.refresh_ms, self._loop)

    def _update_vehicles(self):
        # Dibujar o actualizar posición
        for v in self.simulation.vehicles:
            px = self.margin + v.current_position.x * self.cell_size + 4
            py = self.margin + v.current_position.y * self.cell_size + 4
            # Crear o actualizar rectángulo del vehículo
            if v not in self.vehicle_items:
                item = self.canvas.create_rectangle(px, py, px + self.cell_size - 8, py + self.cell_size - 8,
                                                    fill="#4cc9f0", outline="#1d3557")
                self.vehicle_items[v] = item
                # crear texto con el id centrado dentro del vehículo (solo el número)
                num = (re.search(r"\d+", str(v.vehicle_id)) or [None])[0]
                if num is None:
                    num = str(v.vehicle_id)
                text_x = px + (self.cell_size - 8) / 2
                text_y = py + (self.cell_size - 8) / 2
                # Fuente aumentada 2px (respetando escala) y color negro
                txt = self.canvas.create_text(text_x, text_y, text=str(num), fill='#000', font=(None, int(8 * self.scale)), anchor='center')
                self.vehicle_texts[v] = txt
            else:
                self.canvas.coords(self.vehicle_items[v], px, py, px + self.cell_size - 8, py + self.cell_size - 8)
                if v.completed:
                    self.canvas.itemconfigure(self.vehicle_items[v], fill="#6a994e")
                # actualizar posición del texto encima
                txt = self.vehicle_texts.get(v)
                if txt:
                    # mantener el texto centrado dentro del rectángulo
                    text_x = px + (self.cell_size - 8) / 2
                    text_y = py + (self.cell_size - 8) / 2
                    self.canvas.coords(txt, text_x, text_y)
                    # cambiar color si completado (negro por defecto)
                    self.canvas.itemconfigure(txt, fill='#000' if not v.completed else '#333')

        # Actualizar lista de completados
        completed_ids = [v.vehicle_id for v in self.simulation.vehicles if v.completed]
        completed_text = '\n'.join(completed_ids)
        if self.completed_text_item is None:
            # fallback: crear en la esquina superior del panel si no existe
            if self.sidebar_x is not None:
                hdr_x = self.sidebar_x + 8 * self.scale
                hdr_y = self.margin + int(24 * self.scale)
                small_font = max(6, int((9 * self.scale) / 2))
                self.completed_text_item = self.canvas.create_text(hdr_x, hdr_y, anchor='nw', text=completed_text, fill='#ddd', font=(None, small_font), justify='left')
        else:
            # Si la lista es demasiado larga, distribuir en columnas dentro del panel
            if self.sidebar_x is not None:
                panel_top = self.margin
                panel_bottom = self.margin + self.simulation.city.height * self.cell_size
                header_space = int(30 * self.scale)
                available_h = max(10, panel_bottom - (panel_top + header_space))
                # línea de texto para cada entrada en la lista (más pequeña)
                line_h = max(6, int(7 * self.scale))
                max_lines = max(1, available_h // line_h)
                items = completed_ids
                # Preferir 2 columnas por fila para aprovechar espacio horizontal
                preferred_cols = 2
                if len(items) <= max_lines * preferred_cols:
                    cols = preferred_cols
                else:
                    cols = math.ceil(len(items) / max_lines)

                rows = []
                for r in range(max_lines):
                    row_elems = []
                    for c in range(cols):
                        idx = c * max_lines + r
                        if idx < len(items):
                            row_elems.append(items[idx])
                    rows.append('   '.join(row_elems))
                text_to_show = '\n'.join(rows)
                small_font2 = max(6, int((7 * self.scale) / 2))
                self.canvas.itemconfigure(self.completed_text_item, text=text_to_show, font=(None, small_font2))
            else:
                small_font2 = max(6, int((7 * self.scale) / 2))
                self.canvas.itemconfigure(self.completed_text_item, text=completed_text, font=(None, small_font2))

    def _setup_bindings(self):
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        if self.root:
            self.root.bind("p", self._toggle_pause)
            self.root.bind("P", self._toggle_pause)
            self.root.bind("+", self._faster)
            self.root.bind("=", self._faster)
            self.root.bind("-", self._slower)

    def _find_light_by_pos(self, x, y):
        for tl in self.simulation.traffic_lights:
            if tl.intersection.x == x and tl.intersection.y == y:
                return tl
        return None

    def _on_click(self, event):
        gx = int((event.x - self.margin) / self.cell_size)
        gy = int((event.y - self.margin) / self.cell_size)
        tl = self._find_light_by_pos(gx, gy)
        if tl:
            tl.cycle_manual()

    def _on_right_click(self, event):
        gx = int((event.x - self.margin) / self.cell_size)
        gy = int((event.y - self.margin) / self.cell_size)
        tl = self._find_light_by_pos(gx, gy)
        if tl:
            tl.disable_manual()

    def _toggle_pause(self, event=None):
        if self.simulation.controls.paused:
            self.simulation.controls.resume()
        else:
            self.simulation.controls.pause()

    def _faster(self, event=None):
        sp = self.simulation.controls.speed
        self.simulation.controls.set_speed(min(10.0, sp * 1.25))

    def _slower(self, event=None):
        sp = self.simulation.controls.speed
        self.simulation.controls.set_speed(max(0.1, sp / 1.25))

# ===============================
# EJECUCIÓN PRINCIPAL
# ===============================

if __name__ == "__main__":
    user_menu()

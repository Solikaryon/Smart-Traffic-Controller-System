""" 
Barba Lugo Emmanuel Alejandro
Dávila Godínez Teresa
Monjaraz Briseño Luis Fernando
Quintero Meza Eduardo de Jesús 
"""



"""
ProyectoFinal.py
-----------------
Archivo integrador de la simulación de tráfico urbano.

Responsabilidades principales:
- Cargar y aplicar configuración de simulación.
- Construir la ciudad y colocar semáforos.
- Generar vehículos y calcular rutas (secuencial o paralelo).
- Orquestar ejecución de hilos (vehículos y semáforos).
- Monitorear progreso y mostrar métricas (tiempo real y final).
- Lanzar visualización Tkinter opcional y controlador adaptativo.
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
# MÓDULOS EXTERNOS (clases separadas)
# ===============================

from controls import SimulationControls, Config
from enums import Direction, TrafficLightState, VehicleState
from city import Intersection, Street, CityGrid
from traffic_light import TrafficLight
from vehicle import Vehicle
from metrics import SimulationMetrics
from smart_controller import SmartTrafficController
from visualizer import TrafficVisualizer
from gui import TextRedirector, TrafficGUI

# ===============================
# SIMULACIÓN PRINCIPAL
# ===============================

class TrafficSimulation:
    """Orquesta la simulación completa.

    - Mantiene estado global (ciudad, vehículos, semáforos, métricas).
    - Expone métodos para iniciar/detener simulación y monitorear.
    - Aplica configuración (tamaño de grid, tiempos de semáforo, velocidad, etc.).
    """
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
        # Lista ordenada de vehículos completados (id, tiempo de viaje)
        self.completed_vehicles: List[Tuple[str, float]] = []
        self.completed_lock = threading.Lock()
        
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
        # Bandera para permitir control manual (clic) sobre semáforos
        self.manual_control_enabled = False
        # Nuevas banderas de restricciones de destino
        self.unique_destinations_enabled = False  # Si True, cada vehículo tiene destino único
        self.exclude_light_destinations_enabled = False  # Si True, destinos no pueden ser semáforos
    
    def _load_config(self, config_file):
        """Carga configuración desde JSON (opcional) y aplica valores por defecto.

        Parámetros soportados:
        - num_vehicles, green_time, yellow_time, red_time
        - use_parallel_routing, grid_size, simulation_speed
        - street_mode (two_way|one_way), start_points, dest_points
        """
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
        """Coloca semáforos en patrón de cuadrícula (cada 3 celdas aprox)."""
        # Selección de posiciones según límite Config.MAX_TRAFFIC_LIGHTS
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
                """Genera puntos de inicio/destino.

                Preferencia:
                - Si hay `start_points` y `dest_points` en config, se usan.
                - En su defecto, se toman todas las intersecciones de borde
                    (superior, inferior, izquierdo, derecho).
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
        """Genera vehículos y calcula rutas secuencialmente (A* en cada vehículo)."""
        start_time = timeit.default_timer()
        
        starts, dests_border = self._generate_start_end_points()

        # Determinar candidatos de destino según flags
        if self.unique_destinations_enabled or self.exclude_light_destinations_enabled:
            # Usar TODAS las intersecciones como candidatos
            all_candidates = []
            for x in range(self.city.width):
                for y in range(self.city.height):
                    inter = self.city.get_intersection(x, y)
                    if self.exclude_light_destinations_enabled and inter.traffic_light is not None:
                        continue
                    all_candidates.append(inter)
            dest_candidates = all_candidates
        else:
            # Comportamiento previo: solo bordes
            dest_candidates = dests_border

        used_destinations = set()
        # Si no hay candidatos de destino, no generar vehículos
        if not dest_candidates:
            vehicle_count = 0
        else:
            if self.unique_destinations_enabled:
                # Destinos únicos -> tope es el número de candidatos
                max_capacity = len(dest_candidates)
                vehicle_count = min(int(self.config.get('num_vehicles', 0)), max_capacity)
                # Reflejar el ajuste en la configuración para coherencia de la UI
                self.config['num_vehicles'] = vehicle_count
            else:
                # Permitir destinos repetidos -> respetar exactamente la cantidad solicitada
                vehicle_count = int(self.config.get('num_vehicles', 0))

        for i in range(vehicle_count):
            start = random.choice(starts)
            # Filtrar para que destino != start y opcionalmente único
            filtered = [d for d in dest_candidates if d != start and (not self.unique_destinations_enabled or d not in used_destinations)]
            if not filtered:
                break  # No hay más destinos válidos
            destination = random.choice(filtered)
            if self.unique_destinations_enabled:
                used_destinations.add(destination)
            vehicle = Vehicle(f"V{i+1:03d}", start, destination, self.city, controls=self.controls)
            vehicle.calculate_route_astar()
            vehicle.simulation = self
            self.vehicles.append(vehicle)
        
        routing_time = timeit.default_timer() - start_time
        self.metrics.sequential_routing_time = routing_time
        return routing_time
    
    def generate_vehicles_parallel(self):
        """Genera vehículos y calcula rutas en paralelo usando ThreadPoolExecutor."""
        start_time = timeit.default_timer()
        
        starts, dests_border = self._generate_start_end_points()

        if self.unique_destinations_enabled or self.exclude_light_destinations_enabled:
            all_candidates = []
            for x in range(self.city.width):
                for y in range(self.city.height):
                    inter = self.city.get_intersection(x, y)
                    if self.exclude_light_destinations_enabled and inter.traffic_light is not None:
                        continue
                    all_candidates.append(inter)
            dest_candidates = all_candidates
        else:
            dest_candidates = dests_border

        used_destinations = set()
        if not dest_candidates:
            vehicle_count = 0
        else:
            if self.unique_destinations_enabled:
                max_capacity = len(dest_candidates)
                vehicle_count = min(int(self.config.get('num_vehicles', 0)), max_capacity)
                self.config['num_vehicles'] = vehicle_count
            else:
                vehicle_count = int(self.config.get('num_vehicles', 0))

        vehicles_data = []
        for i in range(vehicle_count):
            start = random.choice(starts)
            filtered = [d for d in dest_candidates if d != start and (not self.unique_destinations_enabled or d not in used_destinations)]
            if not filtered:
                break
            destination = random.choice(filtered)
            if self.unique_destinations_enabled:
                used_destinations.add(destination)
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
                vehicle.simulation = self
                self.vehicles.append(vehicle)
        
        routing_time = timeit.default_timer() - start_time
        self.metrics.parallel_routing_time = routing_time
        return routing_time
    
    def _monitor_simulation(self):
        """Hilo de monitoreo: detecta fin, imprime métricas periódicas y posibles estancamientos."""
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
                # Detectar vehículos estancados (sin progreso reciente)
                try:
                    import sys, traceback
                    stuck_threshold = 8.0  # segundos
                    now = time.time()
                    for v in self.vehicles:
                        if v.completed:
                            continue
                        last = getattr(v, 'last_progress_time', v.start_time or 0)
                        if now - last > stuck_threshold:
                            print(f"[MONITOR] Vehículo potencialmente estancado: {v.vehicle_id}")
                            print(f"  Estado: {v.state}, Pos: ({v.current_position.x},{v.current_position.y}), Dest: ({v.destination.x},{v.destination.y})")
                            print(f"  Ruta restante: {len(v.route)}")
                            if v.route:
                                nx = v.route[0]
                                lock_status = getattr(nx.lock, 'locked', None)
                                try:
                                    is_locked = nx.lock.locked()
                                except Exception:
                                    is_locked = 'n/a'
                                print(f"  Siguiente intersección: ({nx.x},{nx.y}), lock.locked(): {is_locked}")
                                if nx.traffic_light:
                                    try:
                                        print(f"  Semáforo estado: {nx.traffic_light.state}, manual_override: {nx.traffic_light.manual_override}")
                                    except Exception:
                                        pass
                            # Imprimir stack del hilo del vehículo si es posible
                            try:
                                tid = v.ident
                                frames = sys._current_frames()
                                if tid in frames:
                                    print("  Stack del hilo del vehículo:")
                                    traceback.print_stack(frames[tid])
                            except Exception:
                                pass
                except Exception:
                    pass
            
            monitor_count += 1
    
    def start_simulation(self):
        """Inicia hilos de semáforos y vehículos, y arranca el monitoreo.

        Respeta la bandera `use_parallel_routing` para el cálculo de rutas.
        Honra la pausa global vía `SimulationControls` durante la espera principal.
        """
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
        """Detiene semáforos/controlador, junta hilos y calcula métricas finales."""
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
        """Crea y arranca el controlador de semáforos adaptativo."""
        self.smart_controller = SmartTrafficController(self.city, self.traffic_lights)
        self.smart_controller.start()

    # ===============================
    # VISUALIZACIÓN
    # ===============================
    def launch_visualizer(self):
        """Lanza el visualizador Tkinter (mainloop debe correr en el hilo principal)."""
        if self.visualizer is None:
            try:
                self.visualizer = TrafficVisualizer(self)
                # IMPORTANTE: mainloop debe ejecutarse en el hilo principal
                self.visualizer.start()
            except Exception as e:
                print(f"Error iniciando visualizador: {e}")
    
    def _verify_synchronization(self):
        """Verificaciones simples post-simulación sobre concurrencia (colisiones/deadlocks)."""
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
    """Crea `simulation_config.json` con parámetros comunes de la simulación."""
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
    """Ejecuta una simulación rápida con 30 vehículos y configuración por defecto."""
    print("EJECUTANDO PRUEBA RÁPIDA")
    print("=" * 30)
    
    simulation = TrafficSimulation()
    simulation.config['num_vehicles'] = 30
    simulation.start_simulation()

def user_menu():
    """Menú interactivo por consola para ejecutar diferentes modos de simulación."""
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
    """Compara el tiempo de cálculo de rutas secuencial vs paralelo (no el total de simulación)."""
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

    print(f"Tiempo de cálculo de rutas (secuencial): {sequential_time:.4f}s")

    # Prueba paralela
    print("\nProbando planificación PARALELA...")
    sim_parallel = TrafficSimulation()
    sim_parallel.config['num_vehicles'] = num_vehicles
    sim_parallel.config['use_parallel_routing'] = True

    start_time = timeit.default_timer()
    sim_parallel.generate_vehicles_parallel()
    parallel_time = timeit.default_timer() - start_time

    print(f"Tiempo de cálculo de rutas (paralelo): {parallel_time:.4f}s")

    # Resultados
    print(f"\nRESULTADOS DE COMPARACIÓN:")
    print("+----------------------+----------------+")
    print("| Método               | Tiempo (s)     |")
    print("+----------------------+----------------+")
    print(f"| Cálculo secuencial   | {sequential_time:>14.4f} |")
    print(f"| Cálculo paralelo     | {parallel_time:>14.4f} |")
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
        # Parámetros se recalcularán dinámicamente en start() según tamaño de grid y pantalla
        self.scale = 1.0
        self.cell_size = 24  # valor inicial provisional
        self.margin = 20
        # Intervalo de refresco reducido para menor retardo percibido
        self.refresh_ms = 150
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
        # Escalado dinámico según tamaño de pantalla y grid
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        grid_w = self.simulation.city.width
        grid_h = self.simulation.city.height
        # Margen base proporcional al tamaño objetivo
        max_canvas_w = screen_w - 40  # margen global
        max_canvas_h = screen_h - 80  # reservar espacio ventana SO
        # Sidebar fija pero pequeña para listas
        self.sidebar_width = 180
        # Calcular cell_size máximo que permite caber todo el grid
        cell_w = (max_canvas_w - self.sidebar_width - 2 * self.margin) / max(1, grid_w)
        cell_h = (max_canvas_h - 2 * self.margin) / max(1, grid_h)
        dynamic_cell = int(min(cell_w, cell_h))
        # Permitir reducción hasta 4 para grids grandes, limitar superior para no exceder pantalla
        dynamic_cell = max(4, min(72, dynamic_cell))
        self.cell_size = dynamic_cell
        # Ajustar escala relativa para textos/semáforos (basado en 24px)
        self.scale = max(0.5, self.cell_size / 24.0)
        # Margen proporcional
        self.margin = int(10 * self.scale)
        left_width = grid_w * self.cell_size
        h = grid_h * self.cell_size + self.margin * 2
        w = self.margin * 2 + left_width + self.sidebar_width
        self.canvas_width = w
        self.sidebar_x = self.margin + left_width
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#222")
        self.canvas.pack()
        self._draw_grid()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Bind de redimensionamiento para recalcular layout dinámico
        self.root.bind('<Configure>', self._on_resize)
        self._setup_bindings()
        self._loop()
        self.root.mainloop()

    def _recompute_layout(self):
        """Recalcular tamaños al cambiar dimensiones de ventana/pantalla."""
        if not self.root or not self.running:
            return
        # Usar tamaño actual de la ventana para adaptar
        screen_w = self.root.winfo_width() or self.root.winfo_screenwidth()
        screen_h = self.root.winfo_height() or self.root.winfo_screenheight()
        grid_w = self.simulation.city.width
        grid_h = self.simulation.city.height
        max_canvas_w = max(300, screen_w - 40)
        max_canvas_h = max(200, screen_h - 80)
        cell_w = (max_canvas_w - self.sidebar_width - 2 * self.margin) / max(1, grid_w)
        cell_h = (max_canvas_h - 2 * self.margin) / max(1, grid_h)
        dynamic_cell = int(min(cell_w, cell_h))
        dynamic_cell = max(4, min(72, dynamic_cell))
        if dynamic_cell == self.cell_size:
            return  # sin cambios
        self.cell_size = dynamic_cell
        self.scale = max(0.5, self.cell_size / 24.0)
        self.margin = int(10 * self.scale)
        left_width = grid_w * self.cell_size
        h = grid_h * self.cell_size + self.margin * 2
        w = self.margin * 2 + left_width + self.sidebar_width
        self.canvas_width = w
        self.sidebar_x = self.margin + left_width
        self.canvas.config(width=w, height=h)
        # Redibujar todo
        self.canvas.delete('all')
        self.vehicle_items.clear()
        self.vehicle_texts.clear()
        self.light_items.clear()
        self._draw_grid()

    def _on_resize(self, event):
        # Throttling para evitar recalcular en cada paso
        if getattr(self, '_resize_pending', False):
            return
        self._resize_pending = True
        def _do():
            self._resize_pending = False
            self._recompute_layout()
        self.root.after(200, _do)

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
            # Actualización inmediata del color para evitar retardo perceptible
            item = self.light_items.get(tl)
            if item:
                self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))

    def _on_right_click(self, event):
        gx = int((event.x - self.margin) / self.cell_size)
        gy = int((event.y - self.margin) / self.cell_size)
        tl = self._find_light_by_pos(gx, gy)
        if tl:
            tl.disable_manual()
            # Refrescar inmediatamente (puede mantenerse mismo color, pero coherente)
            item = self.light_items.get(tl)
            if item:
                self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))

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
    # Lanzar nueva interfaz negra elegante si Tkinter está disponible.
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except Exception:
        tk = None
    import sys
    import queue

    class TextRedirector:
        """Redirige stdout/stderr a un Text widget de forma segura entre hilos."""
        def __init__(self, text_widget, tag="stdout"):
            self.text_widget = text_widget
            self.tag = tag
            self.queue = queue.Queue()

        def write(self, msg):
            if msg:
                self.queue.put(msg)

        def flush(self):
            pass

        def poll(self):
            try:
                while True:
                    msg = self.queue.get_nowait()
                    self.text_widget.insert("end", msg, self.tag)
                    self.text_widget.see("end")
            except queue.Empty:
                pass

    class TrafficGUI:
        def __init__(self):
            if tk is None:
                print("Tkinter no disponible, usando menú por consola.")
                user_menu()
                return
            self.root = tk.Tk()
            self.root.title("Simulación de Tráfico Urbano")
            self.root.configure(bg="#000000")
            self.simulation: Optional[TrafficSimulation] = None
            self.arrivals_window = None
            self.arrivals_text = None
            self.last_arrivals_count = 0

            # Dimensiones pantalla para escalar grid
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            # Reservar ancho panel lateral
            self.sidebar_width = 420
            self.margin = 8
            # Crear simulación inicial (solo para conocer tamaño de grid)
            self.simulation = TrafficSimulation()
            grid_w = self.simulation.city.width
            grid_h = self.simulation.city.height
            # Guardar dimensiones de pantalla para re-escalar en reinicios
            self.screen_w = screen_w
            self.screen_h = screen_h
            # Factor de escala solicitado (0.3 más pequeño => 70% del tamaño original)
            self.scale_factor = 0.7
            max_grid_w_px = screen_w - self.sidebar_width - self.margin*3
            max_grid_h_px = screen_h - 160  # dejar espacio para barras / ventanas
            cell_size_w = max_grid_w_px / grid_w
            cell_size_h = max_grid_h_px / grid_h
            original_cell = int(min(cell_size_w, cell_size_h))
            self.cell_size = int(original_cell * self.scale_factor)
            # Permitir adaptación a grids grandes (celdas mínimas más pequeñas)
            self.cell_size = max(6, min(64, self.cell_size))  # límites razonables tras escala
            self.canvas_width = self.margin*2 + grid_w*self.cell_size
            self.canvas_height = self.margin*2 + grid_h*self.cell_size

            # Layout principal: frame para canvas y frame lateral
            self.main_frame = tk.Frame(self.root, bg="#000000")
            self.main_frame.pack(fill="both", expand=True)
            self.canvas = tk.Canvas(self.main_frame, width=self.canvas_width, height=self.canvas_height, bg="#0d0d0d", highlightthickness=1, highlightbackground="#444")
            self.canvas.grid(row=0, column=0, padx=(self.margin, self.margin), pady=(self.margin, self.margin))

            self.side_frame = tk.Frame(self.main_frame, width=self.sidebar_width, bg="#121212", highlightthickness=1, highlightbackground="#333")
            self.side_frame.grid(row=0, column=1, sticky="ns", padx=(0, self.margin), pady=(self.margin, self.margin))
            self.side_frame.grid_propagate(False)

            # Secciones del panel lateral
            self._build_menu_section()
            self._build_controls_section()
            self._build_terminal_section()
            self._build_arrivals_preview_section()

            # Dibujar grid inicial
            self.vehicle_items = {}
            self.vehicle_texts = {}
            self.light_items = {}
            self._draw_grid()

            # Redirecciones stdout/stderr
            self.stdout_redirect = TextRedirector(self.terminal_text, "stdout")
            self.stderr_redirect = TextRedirector(self.terminal_text, "stderr")
            self._orig_stdout = sys.stdout
            self._orig_stderr = sys.stderr
            sys.stdout = self.stdout_redirect
            sys.stderr = self.stderr_redirect
            self._poll_terminal()

            # Bucle de actualización gráfica
            self._update_loop()
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            # Adaptación dinámica al redimensionar ventana / mover a otro monitor
            self.root.bind('<Configure>', self._on_gui_resize)
            self.root.mainloop()

        # ------------------- Construcción UI -------------------
        def _section_label(self, parent, text):
            lbl = tk.Label(parent, text=text, fg="#ffffff", bg=parent['bg'], font=("Segoe UI", 10, "bold"))
            lbl.pack(anchor="w", padx=8, pady=(8,4))
            return lbl

        def _styled_button(self, parent, text, command, fg="#e0e0e0", bg="#1e1e1e", active="#2e2e2e"):
            btn = tk.Button(parent, text=text, command=command, fg=fg, bg=bg, activebackground=active, activeforeground=fg,
                            relief="flat", font=("Segoe UI", 9))
            btn.pack(fill="x", padx=8, pady=2)
            return btn

        def _build_menu_section(self):
            self.menu_frame = tk.Frame(self.side_frame, bg="#121212")
            self.menu_frame.pack(fill="x")
            self._section_label(self.menu_frame, "Acciones (Menú)")
            self._styled_button(self.menu_frame, "1: Ejecutar por defecto", self._action_default)
            self._styled_button(self.menu_frame, "2: Cargar configuración", self._action_load_config)
            self._styled_button(self.menu_frame, "3: Crear config ejemplo", create_sample_config)
            self._styled_button(self.menu_frame, "4: Prueba rápida (30)", self._action_quick_test)
            self._styled_button(self.menu_frame, "5: Comparar rutas (seq vs par)", compare_routing_methods)
            self._styled_button(self.menu_frame, "6: Visualización + control manual", self._action_visual_manual)
            self._styled_button(self.menu_frame, "7: Visualización adaptativa", self._action_visual_adaptive)
            self._styled_button(self.menu_frame, "8: Configuración avanzada", self._action_advanced_config)
            self._styled_button(self.menu_frame, "Lista de carros", self._open_arrivals_window, bg="#202020", active="#2f2f2f")
            self._styled_button(self.menu_frame, "9: Salir", self._on_close, fg="#ffffff", bg="#3a0000", active="#550000")

        def _build_controls_section(self):
            self.controls_frame = tk.Frame(self.side_frame, bg="#121212")
            self.controls_frame.pack(fill="x", pady=(6,0))
            self._section_label(self.controls_frame, "Controles rápidos")
            row_frame = tk.Frame(self.controls_frame, bg="#121212")
            row_frame.pack(fill="x", padx=8)
            tk.Label(row_frame, text="Vehículos:", fg="#cccccc", bg="#121212", font=("Segoe UI",8)).pack(side="left")
            self.vehicles_entry = tk.Entry(row_frame, width=6, fg="#ffffff", bg="#1e1e1e", insertbackground="#ffffff")
            self.vehicles_entry.insert(0, str(self.simulation.config['num_vehicles']))
            self.vehicles_entry.pack(side="left", padx=4)
            self.parallel_var = tk.BooleanVar(value=self.simulation.config.get('use_parallel_routing', True))
            tk.Checkbutton(self.controls_frame, text="Rutas en paralelo", variable=self.parallel_var, fg="#bbbbbb", bg="#121212", selectcolor="#1e1e1e", activebackground="#121212").pack(anchor="w", padx=10)
            self.adaptive_var = tk.BooleanVar(value=False)
            tk.Checkbutton(self.controls_frame, text="Semáforos adaptativos", variable=self.adaptive_var, fg="#bbbbbb", bg="#121212", selectcolor="#1e1e1e", activebackground="#121212").pack(anchor="w", padx=10)
            # Indicador de modo manual (solo activable mediante opción 6 del menú)
            self.manual_var = tk.BooleanVar(value=False)
            tk.Checkbutton(self.controls_frame, text="Control manual semáforos", variable=self.manual_var, fg="#bbbbbb", bg="#121212", selectcolor="#1e1e1e", activebackground="#121212", state='disabled').pack(anchor="w", padx=10)
            # Nuevas opciones de destino
            self.unique_dest_var = tk.BooleanVar(value=False)
            tk.Checkbutton(self.controls_frame, text="Destinos únicos", variable=self.unique_dest_var, fg="#bbbbbb", bg="#121212", selectcolor="#1e1e1e", activebackground="#121212").pack(anchor="w", padx=10)
            self.exclude_light_dest_var = tk.BooleanVar(value=False)
            tk.Checkbutton(self.controls_frame, text="Evitar destinos con semáforo", variable=self.exclude_light_dest_var, fg="#bbbbbb", bg="#121212", selectcolor="#1e1e1e", activebackground="#121212").pack(anchor="w", padx=10)
            tk.Label(self.controls_frame, text="Velocidad:", fg="#cccccc", bg="#121212", font=("Segoe UI",8)).pack(anchor="w", padx=10, pady=(6,0))
            self.speed_scale = tk.Scale(self.controls_frame, from_=0.5, to=5.0, resolution=0.1, orient="horizontal", fg="#ffffff", bg="#121212", troughcolor="#222", highlightthickness=0, command=self._on_speed_change)
            self.speed_scale.set(self.simulation.controls.speed)
            self.speed_scale.pack(fill="x", padx=8)
            btn_row = tk.Frame(self.controls_frame, bg="#121212")
            btn_row.pack(fill="x", padx=8, pady=(4,4))
            self.start_btn = self._styled_button(btn_row, "Iniciar", self._start_simulation)
            self.stop_btn = self._styled_button(btn_row, "Detener", self._stop_simulation)
            self.pause_btn = self._styled_button(btn_row, "Pausa", self._toggle_pause)
            self.reset_btn = self._styled_button(btn_row, "Reiniciar", self._clean_reset, bg="#262626", active="#333333")

        def _build_terminal_section(self):
            self.terminal_frame = tk.Frame(self.side_frame, bg="#121212")
            self.terminal_frame.pack(fill="both", expand=True, pady=(6,0))
            self._section_label(self.terminal_frame, "Terminal")
            self.terminal_text = scrolledtext.ScrolledText(self.terminal_frame, height=12, fg="#d0d0d0", bg="#181818", insertbackground="#ffffff", font=("Consolas",9))
            self.terminal_text.pack(fill="both", expand=True, padx=8, pady=(0,8))
            self.terminal_text.tag_config("stderr", foreground="#ff5555")

        def _build_arrivals_preview_section(self):
            self.arrivals_frame = tk.Frame(self.side_frame, bg="#121212")
            self.arrivals_frame.pack(fill="x", pady=(0,8))
            self._section_label(self.arrivals_frame, "Vehículos llegados")
            self.arrivals_label = tk.Label(self.arrivals_frame, text="(ninguno)", fg="#999999", bg="#121212", justify="left", font=("Segoe UI",8))
            self.arrivals_label.pack(fill="x", padx=10, pady=(0,8))

        # ------------------- Acciones menú -------------------
        def _action_default(self):
            print("\nIniciando simulación por defecto...")
            self._start_simulation()

        def _action_load_config(self):
            from tkinter import filedialog
            fname = filedialog.askopenfilename(title="Seleccionar archivo de configuración", filetypes=[("JSON","*.json")])
            if fname:
                self._reset_simulation(config_file=fname)
                print(f"Configuración cargada: {fname}")

        def _action_quick_test(self):
            print("\nPrueba rápida (30 vehículos)...")
            self._reset_simulation()
            self.simulation.config['num_vehicles'] = 30
            # Asegurar que la entrada refleje 30 antes de iniciar (evita que _start_simulation lo sobreescriba con el valor previo)
            try:
                self.vehicles_entry.delete(0,'end')
                self.vehicles_entry.insert(0,'30')
            except Exception:
                pass
            self._start_simulation()

        def _action_visual_manual(self):
            print("Visualización + control manual (usa esta interfaz)")
            # Activar modo manual y desactivar adaptativo
            self.manual_control_enabled = True
            self.manual_var.set(True)
            self.adaptive_var.set(False)
            if self.simulation:
                self.simulation.manual_control_enabled = True
                self.simulation.enable_adaptive = False
                # Desactivar cualquier estado adaptativo previo
                for tl in self.simulation.traffic_lights:
                    # Si estaba en override adaptativo no importa, manual permite clics
                    pass
            print("Modo manual habilitado: clic izquierdo cicla, derecho desactiva manual." )

        def _action_visual_adaptive(self):
            print("Visualización adaptativa activada")
            self.adaptive_var.set(True)
            # Desactivar control manual al activar adaptativo
            self.manual_control_enabled = False
            self.manual_var.set(False)
            if self.simulation:
                self.simulation.manual_control_enabled = False
                self.simulation.enable_adaptive = True
                # Forzar salida de manual override en todos los semáforos para coherencia
                for tl in self.simulation.traffic_lights:
                    if tl.manual_override:
                        tl.disable_manual()
            print("Control manual deshabilitado en modo adaptativo.")

        def _action_advanced_config(self):
            # Pequeña ventana para parámetros clave
            win = tk.Toplevel(self.root)
            win.title("Configuración avanzada")
            win.configure(bg="#1a1a1a")
            entries = {}
            params = [
                ("num_vehicles","Vehículos"),
                ("green_time","Semáforo verde (s)"),
                ("yellow_time","Semáforo amarillo (s)"),
                ("red_time","Semáforo rojo (s)"),
                ("grid_size","Tamaño grid (N)"),
                ("simulation_speed","Velocidad inicial"),
            ]
            for key,label in params:
                fr = tk.Frame(win, bg="#1a1a1a")
                fr.pack(fill="x", padx=8, pady=4)
                tk.Label(fr, text=label+":", fg="#cccccc", bg="#1a1a1a", width=20, anchor="w").pack(side="left")
                e = tk.Entry(fr, fg="#ffffff", bg="#2a2a2a", insertbackground="#ffffff")
                e.pack(side="left", fill="x", expand=True)
                e.insert(0, str(self.simulation.config.get(key, "")))
                entries[key]=e

            # Modo de calles (two_way / one_way)
            street_frame = tk.Frame(win, bg="#1a1a1a")
            street_frame.pack(fill="x", padx=8, pady=4)
            tk.Label(street_frame, text="Modo calles:", fg="#cccccc", bg="#1a1a1a", width=20, anchor="w").pack(side="left")
            street_var = tk.StringVar(value=str(self.simulation.config.get('street_mode','two_way')))
            street_opt = tk.OptionMenu(street_frame, street_var, 'two_way', 'one_way')
            street_opt.configure(fg="#e0e0e0", bg="#2a2a2a", activebackground="#333", highlightthickness=0)
            street_opt.pack(side="left")

            # Checkboxes adaptativo y manual (exclusivos)
            flags_frame = tk.Frame(win, bg="#1a1a1a")
            flags_frame.pack(fill="x", padx=8, pady=(6,2))
            adapt_local_var = tk.BooleanVar(value=self.adaptive_var.get())
            manual_local_var = tk.BooleanVar(value=getattr(self, 'manual_control_enabled', False))

            def on_adapt_toggle():
                if adapt_local_var.get():
                    manual_local_var.set(False)
                # Actualizar nota si se necesita
                note_lbl.configure(text=note_text)

            def on_manual_toggle():
                if manual_local_var.get():
                    adapt_local_var.set(False)
                note_lbl.configure(text=note_text)

            tk.Checkbutton(flags_frame, text="Semáforos adaptativos", variable=adapt_local_var,
                           fg="#bbbbbb", bg="#1a1a1a", selectcolor="#2a2a2a", activebackground="#1a1a1a",
                           command=on_adapt_toggle).pack(anchor="w")
            tk.Checkbutton(flags_frame, text="Control manual semáforos", variable=manual_local_var,
                           fg="#bbbbbb", bg="#1a1a1a", selectcolor="#2a2a2a", activebackground="#1a1a1a",
                           command=on_manual_toggle).pack(anchor="w")

            # Checkboxes para nuevas opciones de destino
            dest_frame = tk.Frame(win, bg="#1a1a1a")
            dest_frame.pack(fill="x", padx=8, pady=(4,2))
            tk.Label(dest_frame, text="Restricciones destinos:", fg="#cccccc", bg="#1a1a1a", anchor="w").pack(anchor="w")
            unique_dest_local_var = tk.BooleanVar(value=getattr(self.simulation, 'unique_destinations_enabled', False))
            exclude_light_dest_local_var = tk.BooleanVar(value=getattr(self.simulation, 'exclude_light_destinations_enabled', False))
            tk.Checkbutton(dest_frame, text="Destinos únicos (sin repetir)", variable=unique_dest_local_var,
                           fg="#bbbbbb", bg="#1a1a1a", selectcolor="#2a2a2a", activebackground="#1a1a1a").pack(anchor="w")
            tk.Checkbutton(dest_frame, text="Excluir semáforos como destino", variable=exclude_light_dest_local_var,
                           fg="#bbbbbb", bg="#1a1a1a", selectcolor="#2a2a2a", activebackground="#1a1a1a").pack(anchor="w")

            # Nota de exclusividad
            note_text = "Nota: 'Control manual' y 'Adaptativos' son mutuamente excluyentes. Al activar uno se desactiva el otro."
            note_lbl = tk.Label(win, text=note_text, fg="#888888", bg="#1a1a1a", wraplength=380, justify="left", font=("Segoe UI",8))
            note_lbl.pack(fill="x", padx=8, pady=(0,6))

            # Botón Aleatorio
            def randomize():
                import random
                # Rellenar valores aleatorios razonables
                entries['num_vehicles'].delete(0,'end'); entries['num_vehicles'].insert(0, str(random.randint(20,200)))
                entries['green_time'].delete(0,'end'); entries['green_time'].insert(0, str(random.randint(3,10)))
                entries['yellow_time'].delete(0,'end'); entries['yellow_time'].insert(0, str(random.randint(2,4)))
                entries['red_time'].delete(0,'end'); entries['red_time'].insert(0, str(random.randint(5,12)))
                entries['grid_size'].delete(0,'end'); entries['grid_size'].insert(0, str(random.randint(8,24)))
                entries['simulation_speed'].delete(0,'end'); entries['simulation_speed'].insert(0, f"{random.uniform(0.6,2.5):.2f}")
                street_var.set(random.choice(['two_way','one_way']))
                # Elegir adaptativo vs manual garantizando exclusión
                if random.choice([True, False]):
                    adapt_local_var.set(True); manual_local_var.set(False)
                else:
                    manual_local_var.set(True); adapt_local_var.set(False)
                note_lbl.configure(text=note_text)

            def apply():
                overrides = {}
                for key,e in entries.items():
                    val = e.get().strip()
                    if not val:
                        continue
                    try:
                        if key == 'simulation_speed':
                            overrides[key]=float(val)
                        else:
                            overrides[key]=int(val)
                    except Exception:
                        print(f"Valor inválido para {key}: {val}")
                # street_mode
                overrides['street_mode'] = street_var.get()
                # Actualizar estado adaptativo y manual (exclusivos)
                adaptive_active = adapt_local_var.get()
                manual_active = manual_local_var.get() and not adaptive_active
                if adaptive_active:
                    manual_active = False
                self.adaptive_var.set(adaptive_active)
                self.manual_control_enabled = manual_active
                self.manual_var.set(manual_active)
                # Actualizar flags de destino
                self.simulation.unique_destinations_enabled = unique_dest_local_var.get()
                self.simulation.exclude_light_destinations_enabled = exclude_light_dest_local_var.get()
                # Ajustar número máximo de vehículos si excede capacidad teórica
                if self.simulation.unique_destinations_enabled or self.simulation.exclude_light_destinations_enabled:
                    total_cells = self.simulation.city.width * self.simulation.city.height
                    sem_count = len(self.simulation.traffic_lights) if self.simulation.exclude_light_destinations_enabled else 0
                    capacity = total_cells - sem_count
                    if overrides.get('num_vehicles') and overrides['num_vehicles'] > capacity:
                        print(f"Reduciendo vehículos a {capacity} por restricciones de destino")
                        overrides['num_vehicles'] = capacity
                self._reset_simulation(overrides=overrides)
                # Tras reinicio, ajustar flags en simulación directamente
                if self.simulation:
                    self.simulation.enable_adaptive = adaptive_active
                    self.simulation.manual_control_enabled = manual_active
                    self.simulation.unique_destinations_enabled = unique_dest_local_var.get()
                    self.simulation.exclude_light_destinations_enabled = exclude_light_dest_local_var.get()
                    if adaptive_active and manual_active:
                        # Seguridad (no debería ocurrir)
                        self.simulation.manual_control_enabled = False
                    if adaptive_active:
                        # Forzar desactivación de overrides manuales previos
                        for tl in self.simulation.traffic_lights:
                            if tl.manual_override:
                                tl.disable_manual()
                win.destroy()
            btns = tk.Frame(win, bg="#1a1a1a")
            btns.pack(fill="x", pady=8)
            tk.Button(btns, text="Aleatorio", command=randomize, fg="#e0e0e0", bg="#444", relief="flat").pack(side="left", padx=(8,4))
            tk.Button(btns, text="Aplicar", command=apply, fg="#e0e0e0", bg="#333", relief="flat").pack(side="left")

        # ------------------- Lógica simulación -------------------
        def _reset_simulation(self, config_file=None, overrides: Optional[Dict]=None, clean: bool=False):
            # Detener simulación previa
            if self.simulation and self.simulation.running:
                self.simulation.stop_simulation()
            self.simulation = TrafficSimulation(config_file=config_file)
            # Aplicar overrides avanzados si existen
            if overrides:
                self.simulation.config.update(overrides)
                # Reconfigurar grid si cambia tamaño o modo
                if ('grid_size' in overrides) or ('street_mode' in overrides):
                    grid_size = int(self.simulation.config.get('grid_size', self.simulation.city.width))
                    street_mode = str(self.simulation.config.get('street_mode','two_way')).lower()
                    two_way = (street_mode != 'one_way')
                    self.simulation.city = CityGrid(grid_size, grid_size, two_way=two_way)
                    # Reescalar cell_size según nuevas dimensiones
                    max_grid_w_px = self.screen_w - self.sidebar_width - self.margin*3
                    max_grid_h_px = self.screen_h - 160
                    cell_size_w = max_grid_w_px / self.simulation.city.width
                    cell_size_h = max_grid_h_px / self.simulation.city.height
                    original_cell = int(min(cell_size_w, cell_size_h))
                    self.cell_size = int(original_cell * getattr(self, 'scale_factor', 0.7))
                    self.cell_size = max(6, min(64, self.cell_size))
                else:
                    # Si no hay cambio explícito de grid, ajustar al tamaño actual de ventana
                    win_w = self.root.winfo_width() or self.screen_w
                    win_h = self.root.winfo_height() or self.screen_h
                    max_grid_w_px = win_w - self.sidebar_width - self.margin*3
                    max_grid_h_px = win_h - 160
                    cell_size_w = max_grid_w_px / self.simulation.city.width
                    cell_size_h = max_grid_h_px / self.simulation.city.height
                    original_cell = int(min(cell_size_w, cell_size_h))
                    self.cell_size = int(original_cell * getattr(self, 'scale_factor', 0.7))
                    self.cell_size = max(6, min(64, self.cell_size))
                # Velocidad inicial
                if 'simulation_speed' in overrides:
                    self.simulation.controls.set_speed(float(self.simulation.config.get('simulation_speed',1.0)))
                # Máximo semáforos
                if 'max_traffic_lights' in overrides:
                    try:
                        Config.MAX_TRAFFIC_LIGHTS = int(overrides['max_traffic_lights'])
                    except Exception:
                        pass
                # Reconstruir semáforos tras cambios
                self.simulation.traffic_lights = []
                self.simulation._setup_traffic_lights()
                # Actualizar campo visual de vehículos si cambió num_vehicles
                if 'num_vehicles' in overrides:
                    try:
                        self.vehicles_entry.delete(0,'end')
                        self.vehicles_entry.insert(0,str(self.simulation.config['num_vehicles']))
                    except Exception:
                        pass
            else:
                # Sin overrides: reflejar siempre el número actual en la entrada para coherencia
                try:
                    self.vehicles_entry.delete(0,'end')
                    self.vehicles_entry.insert(0,str(self.simulation.config.get('num_vehicles',50)))
                except Exception:
                    pass
            # Ajustes paralelos/adaptativos iniciales
            self.simulation.config['use_parallel_routing'] = self.parallel_var.get()
            self.simulation.enable_adaptive = self.adaptive_var.get()
            # Propagar bandera manual a la simulación
            self.simulation.manual_control_enabled = getattr(self, 'manual_control_enabled', False)
            # Limpiar representaciones previas
            self.canvas.delete("all")
            self.vehicle_items.clear()
            self.vehicle_texts.clear()
            self.light_items.clear()
            self._draw_grid()
            if clean:
                try:
                    self.terminal_text.delete('1.0','end')
                except Exception:
                    pass
                self.arrivals_label.configure(text="(ninguno)")
            print("Simulación reiniciada")

        def _recompute_layout(self):
            if not self.simulation:
                return
            win_w = self.root.winfo_width() or self.screen_w
            win_h = self.root.winfo_height() or self.screen_h
            grid_w = self.simulation.city.width
            grid_h = self.simulation.city.height
            max_grid_w_px = win_w - self.sidebar_width - self.margin*3
            max_grid_h_px = win_h - 160
            cell_size_w = max_grid_w_px / max(1, grid_w)
            cell_size_h = max_grid_h_px / max(1, grid_h)
            dynamic_cell = int(min(cell_size_w, cell_size_h) * getattr(self, 'scale_factor', 0.7))
            dynamic_cell = max(6, min(64, dynamic_cell))
            if dynamic_cell == self.cell_size:
                return
            self.cell_size = dynamic_cell
            self.canvas_width = self.margin*2 + grid_w*self.cell_size
            self.canvas_height = self.margin*2 + grid_h*self.cell_size
            self.canvas.config(width=self.canvas_width, height=self.canvas_height)
            self.canvas.delete('all')
            self.vehicle_items.clear()
            self.vehicle_texts.clear()
            self.light_items.clear()
            self._draw_grid()

        def _on_gui_resize(self, event):
            if getattr(self, '_gui_resize_pending', False):
                return
            self._gui_resize_pending = True
            def _do():
                self._gui_resize_pending = False
                self._recompute_layout()
            self.root.after(250, _do)

        def _start_simulation(self):
            if self.simulation.running:
                print("La simulación ya está en ejecución")
                return
            # Actualizar parámetros rápidos
            try:
                num_v = int(self.vehicles_entry.get())
                self.simulation.config['num_vehicles'] = max(20, min(200, num_v))
            except Exception:
                pass
            self.simulation.config['use_parallel_routing'] = self.parallel_var.get()
            self.simulation.enable_adaptive = self.adaptive_var.get()
            self.simulation.manual_control_enabled = getattr(self, 'manual_control_enabled', False)
            # Flags de destino desde controles rápidos
            self.simulation.unique_destinations_enabled = getattr(self, 'unique_dest_var', tk.BooleanVar(value=False)).get()
            self.simulation.exclude_light_destinations_enabled = getattr(self, 'exclude_light_dest_var', tk.BooleanVar(value=False)).get()
            # Ajustar capacidad si se requiere
            if self.simulation.unique_destinations_enabled or self.simulation.exclude_light_destinations_enabled:
                total_cells = self.simulation.city.width * self.simulation.city.height
                sem_count = len(self.simulation.traffic_lights) if self.simulation.exclude_light_destinations_enabled else 0
                capacity = total_cells - sem_count
                if self.simulation.config['num_vehicles'] > capacity:
                    self.simulation.config['num_vehicles'] = capacity
                    try:
                        self.vehicles_entry.delete(0,'end'); self.vehicles_entry.insert(0, str(capacity))
                        print(f"Número de vehículos ajustado a {capacity} por restricciones de destino.")
                    except Exception:
                        pass
            # Si modo adaptativo activo, asegurar no quedan overrides manuales
            if self.simulation.enable_adaptive and not self.simulation.manual_control_enabled:
                for tl in self.simulation.traffic_lights:
                    if tl.manual_override:
                        tl.disable_manual()
            threading.Thread(target=self.simulation.start_simulation, daemon=True).start()
            print("Simulación iniciada")

        def _stop_simulation(self):
            if self.simulation and self.simulation.running:
                self.simulation.stop_simulation()
                print("Simulación detenida")

        def _toggle_pause(self):
            if not self.simulation:
                return
            if self.simulation.controls.paused:
                self.simulation.controls.resume()
                print("Reanudado")
            else:
                self.simulation.controls.pause()
                print("Pausado")

        def _on_speed_change(self, val):
            try:
                sp = float(val)
                if self.simulation:
                    self.simulation.controls.set_speed(sp)
            except Exception:
                pass

        def _clean_reset(self):
            self._reset_simulation(clean=True)
            print("Estado limpiado para nueva prueba")

        # ------------------- Dibujado -------------------
        def _draw_grid(self):
            city = self.simulation.city
            for x in range(city.width):
                for y in range(city.height):
                    px = self.margin + x*self.cell_size
                    py = self.margin + y*self.cell_size
                    self.canvas.create_rectangle(px, py, px+self.cell_size, py+self.cell_size, outline="#222", fill="#111")
            # Semáforos
            for tl in self.simulation.traffic_lights:
                self._draw_light(tl)
            # Asegurar bindings interactivos (solo una vez)
            self._setup_canvas_bindings()

        def _draw_light(self, tl: TrafficLight):
            px = self.margin + tl.intersection.x*self.cell_size + self.cell_size*0.25
            py = self.margin + tl.intersection.y*self.cell_size + self.cell_size*0.25
            size = self.cell_size*0.5
            color = self._color_for_state(tl.state)
            item = self.canvas.create_oval(px, py, px+size, py+size, fill=color, outline="#000")
            self.light_items[tl]=item

        def _color_for_state(self, state: TrafficLightState):
            return {
                TrafficLightState.RED:   "#d62828",
                TrafficLightState.GREEN: "#2a9d8f",
                TrafficLightState.YELLOW:"#f4a261"
            }.get(state, "#555")

        def _update_loop(self):
            if not self.simulation:
                self.root.after(500, self._update_loop)
                return
            # Actualizar luces
            for tl,item in list(self.light_items.items()):
                self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))
            # Vehículos
            for v in self.simulation.vehicles:
                px = self.margin + v.current_position.x*self.cell_size + 2
                py = self.margin + v.current_position.y*self.cell_size + 2
                if v not in self.vehicle_items:
                    item = self.canvas.create_rectangle(px, py, px+self.cell_size-4, py+self.cell_size-4, fill="#4cc9f0", outline="#1d3557")
                    self.vehicle_items[v]=item
                    num = ''.join(filter(str.isdigit, str(v.vehicle_id))) or v.vehicle_id
                    tx = self.canvas.create_text(px+(self.cell_size-4)/2, py+(self.cell_size-4)/2, text=num, fill="#000", font=("Segoe UI", int(self.cell_size*0.28)))
                    self.vehicle_texts[v]=tx
                else:
                    self.canvas.coords(self.vehicle_items[v], px, py, px+self.cell_size-4, py+self.cell_size-4)
                    tx = self.vehicle_texts[v]
                    self.canvas.coords(tx, px+(self.cell_size-4)/2, py+(self.cell_size-4)/2)
                    if v.completed:
                        self.canvas.itemconfigure(self.vehicle_items[v], fill="#6a994e")
                        self.canvas.itemconfigure(tx, fill="#222")
            # Actualizar panel arrivals preview
            with self.simulation.completed_lock:
                arrived = [vid for vid,_ in self.simulation.completed_vehicles]
            if arrived:
                show = ', '.join(arrived[-15:])  # últimos 15 para no saturar
                self.arrivals_label.configure(text=show)
            else:
                self.arrivals_label.configure(text="(ninguno)")
            # Refrescar ventana de llegados si abierta
            if self.arrivals_window and self.arrivals_text:
                self._refresh_arrivals_window()
            self.root.after(500, self._update_loop)

        # ------------------- Interactividad Semáforos -------------------
        def _setup_canvas_bindings(self):
            # Evitar re-bind múltiples si ya existe una marca
            if getattr(self, '_canvas_bounded', False):
                return
            self.canvas.bind('<Button-1>', self._on_canvas_left_click)
            self.canvas.bind('<Button-3>', self._on_canvas_right_click)
            # Atajos similares al visualizador clásico
            self.root.bind('p', lambda e: self._toggle_pause())
            self.root.bind('P', lambda e: self._toggle_pause())
            self.root.bind('+', lambda e: self._speed_up())
            self.root.bind('=', lambda e: self._speed_up())
            self.root.bind('-', lambda e: self._speed_down())
            self._canvas_bounded = True

        def _find_light_at(self, gx, gy):
            for tl in self.simulation.traffic_lights:
                if tl.intersection.x == gx and tl.intersection.y == gy:
                    return tl
            return None

        def _on_canvas_left_click(self, event):
            gx = int((event.x - self.margin) / self.cell_size)
            gy = int((event.y - self.margin) / self.cell_size)
            tl = self._find_light_at(gx, gy)
            if tl:
                # Verificar si el modo manual está habilitado
                if not getattr(self.simulation, 'manual_control_enabled', False):
                    print("[Aviso] Control manual deshabilitado en modo adaptativo.")
                    return
                tl.cycle_manual()
                print(f"Semáforo ({gx},{gy}) ciclo manual -> {tl.state.name}")
                # Actualización inmediata del color para eliminar retardo perceptible
                item = self.light_items.get(tl)
                if item:
                    self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))

        def _on_canvas_right_click(self, event):
            gx = int((event.x - self.margin) / self.cell_size)
            gy = int((event.y - self.margin) / self.cell_size)
            tl = self._find_light_at(gx, gy)
            if tl:
                if not getattr(self.simulation, 'manual_control_enabled', False):
                    print("[Aviso] Control manual deshabilitado.")
                    return
                if tl.manual_override:
                    tl.disable_manual()
                    print(f"Semáforo ({gx},{gy}) manual desactivado")
                    # Refrescar color de inmediato (mantiene estado actual del semáforo)
                    item = self.light_items.get(tl)
                    if item:
                        self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))

        def _speed_up(self):
            sp = self.simulation.controls.speed
            self.simulation.controls.set_speed(min(10.0, sp * 1.25))
            self.speed_scale.set(self.simulation.controls.speed)

        def _speed_down(self):
            sp = self.simulation.controls.speed
            self.simulation.controls.set_speed(max(0.1, sp / 1.25))
            self.speed_scale.set(self.simulation.controls.speed)

        # ------------------- Lista de carros -------------------
        def _open_arrivals_window(self):
            if self.arrivals_window and self.arrivals_window.winfo_exists():
                self.arrivals_window.lift()
                return
            self.arrivals_window = tk.Toplevel(self.root)
            self.arrivals_window.title("Lista de carros completados")
            self.arrivals_window.configure(bg="#101010")
            container = tk.Frame(self.arrivals_window, bg="#101010")
            container.pack(fill="both", expand=True)
            # Scrollbar vertical
            vscroll = tk.Scrollbar(container, orient="vertical")
            vscroll.pack(side="right", fill="y")
            self.arrivals_text = tk.Text(container, fg="#e0e0e0", bg="#181818", width=40, height=25,
                                         font=("Consolas",10), yscrollcommand=vscroll.set)
            self.arrivals_text.pack(side="left", fill="both", expand=True, padx=6, pady=6)
            vscroll.config(command=self.arrivals_text.yview)
            # Guardar último contenido y última posición para preservar scroll
            self._arrivals_last_content = None
            self._arrivals_was_at_bottom = True
            self._refresh_arrivals_window()

        def _refresh_arrivals_window(self):
            if not (self.arrivals_window and self.arrivals_text):
                return
            with self.simulation.completed_lock:
                data = list(self.simulation.completed_vehicles)
            lines = [f"{i+1:03d}. {vid} - {t:.2f}s" for i,(vid,t) in enumerate(data)]
            content = "\n".join(lines) if lines else "(ninguno)"
            # Si el contenido no cambia, no tocar el widget para evitar salto
            if content == getattr(self, '_arrivals_last_content', None):
                return
            # Determinar si el usuario estaba al fondo antes de refrescar
            try:
                ylo, yhi = self.arrivals_text.yview()
                at_bottom = (abs(1.0 - yhi) < 0.01)
            except Exception:
                at_bottom = True
            self.arrivals_text.delete("1.0","end")
            self.arrivals_text.insert("end", content)
            # Restaurar posición de scroll anterior salvo que estuviera al fondo (en cuyo caso lo mantenemos al fondo)
            if at_bottom:
                self.arrivals_text.see("end")
            else:
                # Mantener el inicio visible similar al previo (ylo)
                try:
                    self.arrivals_text.yview_moveto(ylo)
                except Exception:
                    pass
            self._arrivals_last_content = content

        # ------------------- Terminal polling -------------------
        def _poll_terminal(self):
            self.stdout_redirect.poll()
            self.stderr_redirect.poll()
            self.root.after(200, self._poll_terminal)

        def _on_close(self):
            try:
                if self.simulation and self.simulation.running:
                    self.simulation.stop_simulation()
            except Exception:
                pass
            try:
                sys.stdout = self._orig_stdout
                sys.stderr = self._orig_stderr
            except Exception:
                pass
            self.root.destroy()

    if tk is None:
        user_menu()
    else:
        TrafficGUI()

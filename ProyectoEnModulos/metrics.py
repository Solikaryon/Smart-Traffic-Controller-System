from typing import List, Tuple
from enums import VehicleState

class SimulationMetrics:
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

        print(f"\nCOMPARACIÓN DE PLANIFICACIÓN DE RUTAS:")
        print(f"Tiempo de cálculo de rutas (secuencial): {self.sequential_routing_time:.4f}s")
        print(f"Tiempo de cálculo de rutas (paralelo): {self.parallel_routing_time:.4f}s")
        if hasattr(self, 'speedup'):
            print(f"Speedup: {self.speedup:.2f}x")
            print(f"Eficiencia: {self.efficiency:.1f}%")

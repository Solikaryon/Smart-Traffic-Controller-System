import threading
from dataclasses import dataclass
from typing import Optional

# Para evitar importaciones circulares, TrafficLight se importa localmente cuando es necesario

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
        
        for x in range(self.width):
            for y in range(self.height - 1):
                start = self.intersections[(x, y)]
                end = self.intersections[(x, y + 1)]
                name = f"{avenues[x % len(avenues)]} - Sección {y}"
                self.streets.append(Street(name, start, end, True))
        
        for y in range(self.height):
            for x in range(self.width - 1):
                start = self.intersections[(x, y)]
                end = self.intersections[(x + 1, y)]
                name = f"{streets[y % len(streets)]} - Tramo {x}"
                self.streets.append(Street(name, start, end, True))
    
    def get_intersection(self, x, y):
        return self.intersections.get((x, y))
    
    def get_neighbors(self, intersection: Intersection):
        from enums import Direction
        neighbors = []
        x, y = intersection.x, intersection.y
        directions = []
        if self.two_way:
            directions = [
                (x + 1, y, Direction.EAST),
                (x - 1, y, Direction.WEST),
                (x, y + 1, Direction.SOUTH),
                (x, y - 1, Direction.NORTH)
            ]
        else:
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
        # Importar en tiempo de ejecución para evitar ciclos
        from traffic_light import TrafficLight
        from controls import Config
        if intersection.traffic_light is None and len(self.traffic_lights) < Config.MAX_TRAFFIC_LIGHTS:
            traffic_light = TrafficLight(intersection, green_time, yellow_time, red_time)
            self.traffic_lights.append(traffic_light)
            return traffic_light
        return None

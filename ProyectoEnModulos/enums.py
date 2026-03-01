from enum import Enum

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

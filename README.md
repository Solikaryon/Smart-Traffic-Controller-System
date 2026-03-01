# Smart Traffic Controller System

## Author
Luis Fernando Monjaraz Briseño

## Description
This is a comprehensive project simulating an intelligent traffic management system. The system controls traffic lights, monitors vehicle flow, and implements smart algorithms to optimize traffic flow in an urban environment.

## Project Structure

### Main Components

#### gui.py
Graphical user interface for the traffic control system
- Display of traffic status
- Real-time visualization of vehicles and traffic lights
- User controls for system parameters

#### smart_controller.py
Core intelligent traffic management algorithm
- Analyzes traffic patterns
- Makes decisions about traffic light timing
- Optimizes vehicle flow
- Implements adaptive strategies

#### traffic_light.py
Traffic light management
- State management (Red, Yellow, Green)
- Timing control
- Phase transitions

#### vehicle.py
Vehicle simulation
- Vehicle behavior on roads
- Speed control based on traffic lights
- Route management
- Collision avoidance

#### city.py
Urban environment representation
- Road network definition
- Intersection management
- Zone definitions
- City layout

#### visualizer.py
Data visualization and monitoring
- Real-time traffic metrics
- Performance analysis
- Statistical displays

#### metrics.py
Performance measurement and analytics
- Traffic flow statistics
- Vehicle delay calculation
- Efficiency metrics
- System performance analysis

#### controls.py
User input and system control interface
- Command processing
- Parameter adjustment
- System management

#### enums.py
Enumeration definitions for the system
- Traffic light states
- Vehicle types
- Road categories
- System states

#### main.py
Main entry point of the application
- Initializes the system
- Coordinates all components
- Runs the simulation loop

## Versions

### ProyectoPresentadoEnClase (Class Presentation Version)
Single-file implementation suitable for classroom demonstration

### ProyectoEnModulos (Modular Version)
Complete, well-organized modular implementation with separated concerns

### ProyectoSinInterfaz (Non-GUI Version)
Command-line version without graphical interface for backend testing

## Features
- **Intelligent Traffic Management**: Adaptive light timing based on traffic flow
- **Vehicle Simulation**: Realistic vehicle behavior and movement
- **Real-time Monitoring**: Live traffic metrics and statistics
- **Scalable Architecture**: Modular design for easy expansion
- **Optimization**: Minimizes vehicle delays and improves traffic flow

## How to Run

### Modular Version (Recommended)
```bash
cd ProyectoEnModulos
python main.py
```

### Class Presentation Version
```bash
cd "1 ProyectoPresentadoEnClase Principal"
python ProyectoPresentadoEnClase.py
```

### Non-GUI Version
```bash
cd ProyectoSinInterfaz
python ProyectoSinInterfaz.py
```

## Requirements
- Python 3.6 or higher
- Dependencies (as specified in project files):
  - tkinter (for GUI version)
  - numpy (for numerical operations)
  - matplotlib (for visualization)

## Key Concepts Implemented
- **Thread Management**: Concurrent execution of traffic controllers
- **Queue Management**: Vehicle queue management at intersections
- **State Machines**: Traffic light state transitions
- **Data Structures**: Efficient road network representation
- **Algorithms**: Optimization algorithms for traffic management

## Learning Objectives
- Understanding traffic management systems
- Multi-threaded programming
- System design and architecture
- Real-time simulation
- Performance optimization

## License
Educational project

## Future Improvements
- Support for more complex road networks
- Machine learning-based optimization
- Multi-agent coordination
- Real-world data integration
- Advanced visualization features

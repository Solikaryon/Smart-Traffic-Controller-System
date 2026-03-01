# Proyecto Final

Este repositorio contiene tres variantes del proyecto, organizadas en carpetas separadas. La carpeta principal es:

- 1 ProyectoPresentadoEnClase Principal → Esta es la carpeta principal presentada en clase.

A continuación se describe cada carpeta, su propósito, estructura y cómo ejecutarla.

## 1) 1 ProyectoPresentadoEnClase Principal (Carpeta principal)

- **Propósito:** Versión compacta del proyecto presentada en clase.
- **Contenido:**
  - `ProyectoPresentadoEnClase.py`: Script principal que ejecuta la demostración.

  # Ejecutar el script
  python "1 ProyectoPresentadoEnClase Principal/ProyectoPresentadoEnClase.py"
  ```

## 2) ProyectoEnModulos

- **Propósito:** Implementación modular con separación por componentes (ciudad, vehículos, semáforos, GUI, métricas).
- **Contenido principal:**
  - `main.py`: Punto de entrada recomendado. SE EJECUTA DESDE ESTE ARCHIVO.
  - `city.py`, `traffic_light.py`, `vehicle.py`: Lógica del mundo y agentes.
  - `smart_controller.py`, `controls.py`: Controladores y reglas de decisión.
  - `metrics.py`: Cálculo de métricas y reportes.
  - `visualizer.py`, `gui.py`: Visualización/Interfaz.
  - `enums.py`: Enumeraciones y constantes del sistema.


## 3) ProyectoSinInterfaz

- **Propósito:** Versión simplificada sin GUI para pruebas rápidas o ejecución en entornos sin entorno gráfico.
- **Contenido:**
  - `ProyectoSinInterfaz.py`: Script principal que corre la simulación sin interfaz.



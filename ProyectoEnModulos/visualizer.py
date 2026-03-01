import math
import re
try:
    import tkinter as tk
except Exception:
    tk = None

from enums import TrafficLightState

class TrafficVisualizer:
    """Responsable de mostrar la animación en el hilo principal (no hereda de Thread)."""
    def __init__(self, simulation):
        self.simulation = simulation
        self.running = True
        self.scale = 1.0
        self.cell_size = 24
        self.margin = 20
        self.refresh_ms = 150
        self.root = None
        self.canvas = None
        self.vehicle_items = {}
        self.light_items = {}
        self.vehicle_texts = {}
        self.completed_text_item = None
        self.sidebar_width = 160 * self.scale
        self.canvas_width = None
        self.sidebar_x = None

    def start(self):
        if tk is None:
            print("Tkinter no disponible (instala Python con Tcl/Tk).")
            return
        self.root = tk.Tk()
        self.root.title("Simulación de Tráfico Urbano")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        grid_w = self.simulation.city.width
        grid_h = self.simulation.city.height
        max_canvas_w = screen_w - 40
        max_canvas_h = screen_h - 80
        self.sidebar_width = 180
        cell_w = (max_canvas_w - self.sidebar_width - 2 * self.margin) / max(1, grid_w)
        cell_h = (max_canvas_h - 2 * self.margin) / max(1, grid_h)
        dynamic_cell = int(min(cell_w, cell_h))
        dynamic_cell = max(4, min(72, dynamic_cell))
        self.cell_size = dynamic_cell
        self.scale = max(0.5, self.cell_size / 24.0)
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
        self.root.bind('<Configure>', self._on_resize)
        self._setup_bindings()
        self._loop()
        self.root.mainloop()

    def _recompute_layout(self):
        if not self.root or not self.running:
            return
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
            return
        self.cell_size = dynamic_cell
        self.scale = max(0.5, self.cell_size / 24.0)
        self.margin = int(10 * self.scale)
        left_width = grid_w * self.cell_size
        h = grid_h * self.cell_size + self.margin * 2
        w = self.margin * 2 + left_width + self.sidebar_width
        self.canvas_width = w
        self.sidebar_x = self.margin + left_width
        self.canvas.config(width=w, height=h)
        self.canvas.delete('all')
        self.vehicle_items.clear()
        self.vehicle_texts.clear()
        self.light_items.clear()
        self._draw_grid()

    def _on_resize(self, event):
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

        for tl in self.simulation.traffic_lights:
            self._draw_light(tl)

        if self.sidebar_x is not None:
            panel_left = self.sidebar_x
            panel_right = self.canvas_width - self.margin
            panel_top = self.margin
            panel_bottom = self.margin + self.simulation.city.height * self.cell_size
            self.canvas.create_rectangle(panel_left, panel_top, panel_right, panel_bottom, fill="#111", outline="#222")
            hdr_x = panel_left + 8 * self.scale
            hdr_y = panel_top + 6 * self.scale
            self.canvas.create_text(hdr_x, hdr_y, anchor='nw', text="Completados:", fill='#fff', font=(None, int(10 * self.scale), 'bold'))
            small_font = max(6, int((9 * self.scale) / 2))
            self.completed_text_item = self.canvas.create_text(hdr_x, hdr_y + int(18 * self.scale), anchor='nw', text="", fill='#ddd', font=(None, small_font), justify='left')

    def _draw_light(self, tl):
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
        for v in self.simulation.vehicles:
            px = self.margin + v.current_position.x * self.cell_size + 4
            py = self.margin + v.current_position.y * self.cell_size + 4
            if v not in self.vehicle_items:
                item = self.canvas.create_rectangle(px, py, px + self.cell_size - 8, py + self.cell_size - 8,
                                                    fill="#4cc9f0", outline="#1d3557")
                self.vehicle_items[v] = item
                num = (re.search(r"\d+", str(v.vehicle_id)) or [None])[0]
                if num is None:
                    num = str(v.vehicle_id)
                text_x = px + (self.cell_size - 8) / 2
                text_y = py + (self.cell_size - 8) / 2
                txt = self.canvas.create_text(text_x, text_y, text=str(num), fill='#000', font=(None, int(8 * self.scale)), anchor='center')
                self.vehicle_texts[v] = txt
            else:
                self.canvas.coords(self.vehicle_items[v], px, py, px + self.cell_size - 8, py + self.cell_size - 8)
                if v.completed:
                    self.canvas.itemconfigure(self.vehicle_items[v], fill="#6a994e")
                txt = self.vehicle_texts.get(v)
                if txt:
                    text_x = px + (self.cell_size - 8) / 2
                    text_y = py + (self.cell_size - 8) / 2
                    self.canvas.coords(txt, text_x, text_y)
                    self.canvas.itemconfigure(txt, fill='#000' if not v.completed else '#333')

        completed_ids = [v.vehicle_id for v in self.simulation.vehicles if v.completed]
        completed_text = '\n'.join(completed_ids)
        if self.completed_text_item is None:
            if self.sidebar_x is not None:
                hdr_x = self.sidebar_x + 8 * self.scale
                hdr_y = self.margin + int(24 * self.scale)
                small_font = max(6, int((9 * self.scale) / 2))
                self.completed_text_item = self.canvas.create_text(hdr_x, hdr_y, anchor='nw', text=completed_text, fill='#ddd', font=(None, small_font), justify='left')
        else:
            if self.sidebar_x is not None:
                panel_top = self.margin
                panel_bottom = self.margin + self.simulation.city.height * self.cell_size
                header_space = int(30 * self.scale)
                available_h = max(10, panel_bottom - (panel_top + header_space))
                line_h = max(6, int(7 * self.scale))
                max_lines = max(1, available_h // line_h)
                items = completed_ids
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
        if self.canvas:
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
            item = self.light_items.get(tl)
            if item:
                self.canvas.itemconfigure(item, fill=self._color_for_state(tl.state))

    def _on_right_click(self, event):
        gx = int((event.x - self.margin) / self.cell_size)
        gy = int((event.y - self.margin) / self.cell_size)
        tl = self._find_light_by_pos(gx, gy)
        if tl:
            tl.disable_manual()
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

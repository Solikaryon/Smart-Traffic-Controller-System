import queue
try:
    import tkinter as tk
    from tkinter import scrolledtext
except Exception:
    tk = None

class TextRedirector:
    """Redirige stdout/stderr a un Text widget de forma segura entre hilos.

    Uso:
    - Reemplazar `sys.stdout`/`sys.stderr` por instancias de esta clase.
    - Los mensajes se encolan y se vuelcan con `poll()` en el hilo de GUI.
    """
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
    """Interfaz gráfica básica.

    - Panel izquierdo: `ScrolledText` para logs (stdout/stderr).
    - Panel derecho: contenedor desplazable (Canvas+Scrollbar) para controles/secciones.
    - Redirección de salida y polling para mostrar mensajes en tiempo real.
    """
    def __init__(self, title: str = "Simulación de Tráfico"):
        if tk is None:
            raise RuntimeError("Tkinter no está disponible en este entorno")

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="#111")

        # Contenedor principal
        frame = tk.Frame(self.root, bg="#111")
        frame.pack(fill="both", expand=True)

        # LAYOUT: panel izquierdo (texto/logs) y panel derecho scrollable
        left_frame = tk.Frame(frame, bg="#111")
        left_frame.pack(side="left", fill="both", expand=True)

        right_container = tk.Frame(frame, bg="#111")
        right_container.pack(side="right", fill="y")

        # Canvas + scrollbar para hacer el panel derecho desplazable
        self.sidebar_canvas = tk.Canvas(right_container, bg="#111", highlightthickness=0, width=320)
        self.sidebar_scrollbar = tk.Scrollbar(right_container, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_canvas.pack(side="left", fill="y", expand=False)
        self.sidebar_scrollbar.pack(side="right", fill="y")

        # Frame interno que contendrá widgets del panel derecho
        self.sidebar_frame = tk.Frame(self.sidebar_canvas, bg="#111")
        # Crear window dentro del canvas
        self.sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar_frame, anchor="nw")

        # Actualizar región de scroll cuando cambie el tamaño del contenido
        def _update_scrollregion(event=None):
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        self.sidebar_frame.bind("<Configure>", _update_scrollregion)

        # ScrolledText proporciona Text + Scrollbar integrada en el panel izquierdo
        self.text = scrolledtext.ScrolledText(
            left_frame,
            wrap="word",
            width=100,
            height=30,
            bg="#1e1e1e",
            fg="#dcdcdc",
            insertbackground="#dcdcdc",
            relief="flat"
        )
        self.text.pack(fill="both", expand=True, padx=8, pady=8)

        # Tags de estilo
        self.text.tag_configure("stdout", foreground="#dcdcdc")
        self.text.tag_configure("stderr", foreground="#ff6b6b")

        # Redirectores
        self.stdout_redirector = TextRedirector(self.text, tag="stdout")
        self.stderr_redirector = TextRedirector(self.text, tag="stderr")

        # Intervalo de polling en ms
        self.poll_interval_ms = 100

        # Cerrar ordenado
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Ejemplo de contenido en panel derecho (títulos/controles) para demostrar el scroll.
        # Sustituye o expande estos widgets con las secciones reales del proyecto.
        hdr = tk.Label(self.sidebar_frame, text="Panel lateral (scroll)", fg="#fff", bg="#111", font=(None, 11, "bold"))
        hdr.pack(anchor="w", padx=8, pady=(8,4))
        for i in range(20):
            tk.Label(self.sidebar_frame, text=f"Elemento {i+1}", fg="#ddd", bg="#111").pack(anchor="w", padx=12, pady=2)

        # Ajuste del ancho del frame interno cuando cambie el tamaño del canvas
        def _on_canvas_resize(event):
            try:
                self.sidebar_canvas.itemconfigure(self.sidebar_window, width=event.width)
            except Exception:
                pass
        self.sidebar_canvas.bind("<Configure>", _on_canvas_resize)

    def attach_streams(self):
        """Adjunta los redirectores a sys.stdout/sys.stderr."""
        import sys
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector

    def start(self):
        """Inicia el loop principal y el polling de colas."""
        # Primer disparo
        self._poll_queues()
        self.root.mainloop()

    def _poll_queues(self):
        """Vacía colas de stdout/stderr hacia el Text y rearma el temporizador."""
        try:
            self.stdout_redirector.poll()
            self.stderr_redirector.poll()
        finally:
            # Reprogramar
            self.root.after(self.poll_interval_ms, self._poll_queues)

    def _on_close(self):
        # Intentar restaurar stdout/stderr
        try:
            import sys
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        self.root.destroy()

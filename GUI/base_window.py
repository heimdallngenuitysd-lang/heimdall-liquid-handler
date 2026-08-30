import sys
import cv2
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinter import scrolledtext as st
import threading
from printer_controller import PrinterController, PrinterAction
from esp_comm import ESPMotorController
from vlm_controller import VLMController
from gcode_helper import GCodeHelper as g
from equipment import YAMLHelper as y

# Colors
BG = "#1a1b26"
CARD = "#24283b"
ACCENT = "#7aa2f7"
ACCENT_HOVER = "#89b4fa"
SELECTED = "#9ece6a"
TEXT = "#ffffff"
TEXT_DIM = "#565f89"
DISABLED_COL = "#3b3d4e"

# Assignment colors (cycling palette)
ASSIGNMENT_COLORS = [
    "#9ece6a",  # Green
    "#7aa2f7",  # Blue
    "#bb9af7",  # Purple
    "#f7768e",  # Red
    "#e0af68",  # Yellow/Orange
    "#73daca",  # Cyan
    "#ff9e64",  # Orange
    "#2ac3de",  # Light Blue
]

# Mixing indicator (well in multiple assignments)
MIXING_COLOR = "#ff007c"
MIXING_BORDER = 3

class PrinterConnector(tk.Frame):
    def __init__(self, parent, generate_func=None, camera_callback=None, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)

        self.pack(fill=tk.X, padx=5, pady=(12, 8))
        self.generate_func = generate_func
        self.camera_callback = camera_callback
        self._init_variables()
        self._build_ui()

    # ── State ────────────────────────────────────────────────────────────
    def _init_variables(self):
        self.user_configs = y.open_user()
        ports = PrinterController.list_ports()
        cameras = self.list_camera_ports()
        self.connected = False
        self.printer = PrinterController()
        self.printer_port_var = tk.StringVar(
            value=self.user_configs["printer-port"] 
            if self.user_configs["printer-port"] in ports 
            else (ports[0] if ports else "")
        )
        self.esp_port_var = tk.StringVar(
            value=self.user_configs["esp-port"] 
            if self.user_configs["esp-port"] in ports 
            else (ports[0] if ports else ""))
        self.esp_motor_controller = ESPMotorController()
        self.baud_var = tk.StringVar(value="115200")
        self.printer_status_var = tk.StringVar(value="● Disconnected")

        self.camera_var = tk.StringVar(
            value=self.user_configs["camera"] 
            if self.user_configs["camera"] in cameras
            else (cameras[0] if cameras else "")
        )
        self.generate_func = self.generate_func

        printers = list(y.list_printers())

        if printers:
            self.printer_config = y.open_printer()[printers[0]]
        else:
            print("No printers found")

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Row 0 layout
        # [Title] [Port] [Dropdown] [Refresh] [Baud] [Entry] [Connect] [Status]

        # Title
        tk.Label(
            self,
            text="Printer Connection",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=BG
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 16))

        # Camera Port
        tk.Label(self, text="Camera:", fg=TEXT, bg=BG)\
            .grid(row=0, column=1, sticky=tk.W, padx=(0, 8))

        

        self.camera_combo = ttk.Combobox(
            self,
            textvariable=self.camera_var,
            values=self.list_camera_ports(),
            width=13,
            state="readonly"
        )
        # Bind the selection event
        self.camera_combo.bind("<<ComboboxSelected>>", self.on_camera_change)

        self.camera_combo.grid(
            row=0,
            column=2,
            sticky=tk.W,
            padx=(0, 4)
        )

        # Port
        tk.Label(self, text="Printer Port:", fg=TEXT, bg=BG)\
            .grid(row=0, column=3, sticky=tk.W, padx=(0, 8))

        self.printer_port_combo = ttk.Combobox(
            self,
            textvariable=self.printer_port_var,
            values=PrinterController.list_ports(),
            width=13,
            state="readonly"
        )
        self.printer_port_combo.grid(row=0, column=4, sticky=tk.W, padx=(0, 4))
        self.printer_port_combo.bind("<<ComboboxSelected>>", self.on_printer_select)


        tk.Label(self, text="ESP Port:", fg=TEXT, bg=BG)\
            .grid(row=0, column=5, sticky=tk.W, padx=(0, 8))

        self.esp_port_combo = ttk.Combobox(
            self,
            textvariable=self.esp_port_var,
            values=PrinterController.list_ports(),
            width=13,
            state="readonly"
        )
        self.esp_port_combo.bind("<<ComboboxSelected>>", self.on_esp_select)
        self.esp_port_combo.grid(row=0, column=6, sticky=tk.W, padx=(0, 4))
        
        

        # Refresh button
        tk.Button(
            self,
            text="↻ refresh ports",
            command=self.refresh_ports,
            bg=CARD,
            fg=TEXT,
            relief=tk.FLAT,
            cursor="hand2",
            font=("Segoe UI", 10)
        ).grid(row=0, column=7, padx=(0, 16))

        # Baud
        tk.Label(self, text="Baud:", fg=TEXT, bg=BG)\
            .grid(row=0, column=8, sticky=tk.W, padx=(0, 8))

        tk.Entry(
            self,
            textvariable=self.baud_var,
            width=10,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT
        ).grid(row=0, column=9, sticky=tk.W, padx=(0, 16))

        # Connect button
        self.btn_connect = tk.Button(
            self,
            text="Connect",
            command=self.toggle_connection,
            bg=ACCENT,
            fg=BG,
            activebackground=ACCENT_HOVER,
            activeforeground=BG,
            relief=tk.FLAT,
            padx=12,
            pady=6,
            cursor="hand2"
        )
        self.btn_connect.grid(row=0, column=10, padx=(0, 10))



    def list_camera_ports(self,max_ports=10):
        available = []
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        for i in range(max_ports):
            cap = None
            try:
                cap = cv2.VideoCapture(i, backend)
                if cap.isOpened():
                    available.append(f"Camera {i}")
            except Exception:
                pass
            finally:
                if cap is not None:
                    cap.release()
        return available
    
    def on_printer_select(self, event=None):
        self.refresh_user()
        self.user_configs["printer-port"] = self.printer_port_var.get()
        print(self.user_configs)
        y.write_yaml(self.user_configs, r"configs\\user.yaml")
    
    def on_esp_select(self, event=None):
        self.refresh_user()
        self.user_configs["esp-port"] = self.esp_port_var.get()
        y.write_yaml(self.user_configs, r"configs\\user.yaml")
        # self.esp_motor_controller.set_port(self.esp_port_var.get())


    def on_camera_change(self, event=None):
        """Callback function triggered when the selection changes."""
        selection = int(self.camera_var.get()[-1])
        self.refresh_user()
        self.user_configs["camera"] = int(self.camera_var.get()[-1])
        y.write_yaml(self.user_configs, r"configs\\user.yaml")
        if self.camera_callback:
            self.camera_callback(selection)
        

    # ── Actions ──────────────────────────────────────────────────────────
    def refresh_ports(self):
        self.camera_combo["values"] = self.list_camera_ports()
        ports = PrinterController.list_ports()
        self.printer_port_combo["values"] = ports
        self.esp_port_combo["values"] = ports

        if ports:
            self.printer_port_var.set(ports[0])

    def toggle_connection(self):
        if not self.connected:
            if self.printer_port_var.get() == self.esp_port_var.get():
                messagebox.showwarning("Warning", "Printer port and ESP port must be different")
                return
            # Placeholder logic — you should connect this to MainApp/PrinterController
            printer_status, printer_message = self.printer.connect(self.printer_port_var.get())
            print("Printer connection status:", printer_status, printer_message)
            self.esp_motor_controller.connect(self.esp_port_var.get())
            if printer_status:
                self.printer_status_var.set("● Connected")
                self.btn_connect.config(text="Disconnect")
                self.connected = True
        else:
            if self.printer.is_connected:
                self.printer.disconnect()
            if self.esp_motor_controller.is_connected:
                self.esp_motor_controller.disconnect()
            self.connected = False
            self.printer_status_var.set("● Disconnected")
            self.btn_connect.config(text="Connect")
    
    def refresh_user(self):
        self.user_configs = y.open_user()

    # ── External API ──────────────────────────────────────────────────────
    def get_port(self):
        return self.printer_port_var.get()

    def get_baud(self):
        return int(self.baud_var.get())

    def send_gcode(self, gcode, log_callback=None):

        def safe_log(msg):
            if log_callback:
                self.after(0, lambda: log_callback(msg))

        def worker():

            flag, msg = self.printer.send_sequence(
                gcode,
                log_callback=safe_log
            )

            if not flag:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Printer error",
                        msg
                    )
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()
    
    def printer_callback(self, printer):
        self.printer_config = printer
        self.esp_motor_controller.printer_config = printer
    

    


class ManualUI(tk.Frame):
    def __init__(self, parent, print_func=None, **kwargs):
        kwargs.setdefault("bg", BG)
        self.parent = parent
        self.print_func = print_func
        self.printer = y.open_default_printer()
        self.step_size = tk.DoubleVar(value=1)
        self.vlm_controller = VLMController()
        self.esp_motor_controller = None
        super().__init__(parent, **kwargs)
        self._build_ui()
    
    def _build_ui(self):
        PAD = dict(padx=6, pady=6)

        def mkbtn(p, text, cmd, bg="#3d3d3d", fg="white", width=4, fsize=13):
            return tk.Button(p, text=text, command=cmd, bg=bg, fg=fg,
                             activebackground="#555555", relief="flat",
                             width=width, font=("Segoe UI", fsize, "bold"),
                             cursor="hand2")

        left = tk.Frame(self.parent, bg=BG)
        left.pack(side="left", fill="both", padx=6, pady=6)

        d_pad = tk.Frame(left, bg=BG)
        d_pad.grid(row=0, column=0, **PAD, sticky="n")

        # ── Left: XY jog ─────────────────────────────────────────────────────
        xy_card = tk.LabelFrame(d_pad, text=" XY Movement ", bg=BG, fg=TEXT_DIM,
                                font=("Segoe UI", 10))
        xy_card.grid(row=0, column=0, **PAD, sticky="n")

        arrow_cfg = [
            ("", None, 0, 0),
            ("▲", lambda: self.send_gcode(g.move_relative([0,self.step_size.get(),0]), log_callback=self._console_log), 0, 1),
            ("", None, 0, 2),
            ("◀", lambda: self.send_gcode(g.move_relative([-self.step_size.get(),0,0]), log_callback=self._console_log),1,0),
            ("⌂", lambda: self.send_gcode([g.setup()]),1,1),
            ("▶", lambda: self.send_gcode(g.move_relative([self.step_size.get(),0,0]), log_callback=self._console_log), 1, 2),
            ("", None, 2, 0),
            ("▼", lambda: self.send_gcode(g.move_relative([0,-self.step_size.get(),0]), log_callback=self._console_log), 2, 1),
            ("", None, 2, 2),
        ]
        for text, cmd, r, c in arrow_cfg:
            if text:
                mkbtn(xy_card, text, cmd, fsize=14).grid(row=r, column=c, padx=3, pady=3)
            else:
                tk.Label(xy_card, bg=BG, width=4).grid(row=r, column=c)

        # ── Middle: Z jog ────────────────────────────────────────────────────
        z_card = tk.LabelFrame(d_pad, text=" Z Movement ", bg=BG, fg=TEXT_DIM,
                               font=("Segoe UI", 10))
        z_card.grid(row=0, column=1, **PAD, sticky="n")

        mkbtn(z_card, "▲", lambda: self.send_gcode(g.move_relative([0,0,self.step_size.get()]), log_callback=self._console_log)).pack(**PAD)
        tk.Label(z_card, text="Z", bg=BG, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(pady=2)
        mkbtn(z_card, "▼", lambda: self.send_gcode(g.move_relative([0,0,-self.step_size.get()]), log_callback=self._console_log)).pack(**PAD)

        # ── Right: step size + actions ────────────────────────────────────────
        step_col = tk.Frame(d_pad, bg=BG)
        step_col.grid(row=1, column=1, **PAD, sticky="n")

        step_card = tk.LabelFrame(step_col, text=" Step Size (mm) ", bg=BG,
                                  fg=TEXT_DIM, font=("Segoe UI", 10))
        step_card.pack(fill="x", pady=(0, 8))
        for size in [0.1, 1, 10]:
            tk.Radiobutton(step_card, text=f"{size} mm", variable=self.step_size,
                           value=size, bg=BG, fg=TEXT, selectcolor=CARD,
                           activebackground=BG,
                           font=("Segoe UI", 10)).pack(anchor="w", padx=6)

        # ── XYZ Move Control ────────────────────────────────────────────────
        
        move_card = tk.LabelFrame(
            left,
            text=" Move To Position ",
            bg=BG,
            fg=TEXT_DIM,
            font=("Segoe UI", 10)
        )
        move_card.grid(row=1, column=0, columnspan=3, pady=10, padx=15, sticky="w")
        
        xyz_card = tk.Frame(move_card, bg=BG)

        xyz_card.grid(row=0, column=0, pady=10, sticky="w")


        # Variables
        self.x_var = tk.DoubleVar(value=0.0)
        self.y_var = tk.DoubleVar(value=0.0)
        self.z_var = tk.DoubleVar(value=0.0)


        # Inputs
        tk.Label(xyz_card, text="X:", bg=BG, fg=TEXT).grid(row=0, column=0, padx=2, pady=6)
        tk.Entry(xyz_card, textvariable=self.x_var, width=8).grid(row=0, column=1, padx=4)

        tk.Label(xyz_card, text="Y:", bg=BG, fg=TEXT).grid(row=0, column=2, padx=2, pady=6)
        tk.Entry(xyz_card, textvariable=self.y_var, width=8).grid(row=0, column=3, padx=4)

        tk.Label(xyz_card, text="Z:", bg=BG, fg=TEXT).grid(row=0, column=4, padx=2, pady=6)
        tk.Entry(xyz_card, textvariable=self.z_var, width=8).grid(row=0, column=5, padx=4)

        btn_card = tk.Frame(move_card, bg=BG, )
        btn_card.grid(row=1, column=0)
        # Move button
        mkbtn(
            btn_card,
            "Move",
            self._move_to_xyz,
            bg="#3498db",
            width=5
        ).grid(row=0, column=0, padx=8, pady=8)

        # Move button
        mkbtn(
            btn_card,
            "Get",
            self._get_xyz,
            bg="#3498db",
            width=5
        ).grid(row=0, column=1, padx=8, pady=8)

        

        act_card = tk.LabelFrame(left, text=" Actions ", bg=BG, fg=TEXT_DIM,
                                 font=("Segoe UI", 10))
        act_card.grid(row=0, column=2, sticky="n", padx=6, pady=6)

        mkbtn(act_card, "Home All", lambda: self.send_gcode([g.setup_motors(),g.home("z"), g.home("x"), g.home("y")], log_callback=self._console_log), bg="#8e44ad", width=12).pack(fill="x", padx=6, pady=3)

        # Individual axis home buttons
        home_axis_row = tk.Frame(act_card, bg=BG)
        home_axis_row.pack(fill="x", padx=6, pady=3)
        mkbtn(home_axis_row, "Home X", lambda: self.send_gcode([g.setup_motors(),g.home("x")], log_callback=self._console_log), bg="#2471a3", width=8).pack(side="left", padx=(0, 4))
        mkbtn(home_axis_row, "Home Y", lambda: self.send_gcode([g.setup_motors(),g.home("y")], log_callback=self._console_log), bg="#2471a3", width=8).pack(side="left", padx=(0, 4))
        mkbtn(home_axis_row, "Home Z", lambda: self.send_gcode([g.setup_motors(),g.home("z")], log_callback=self._console_log), bg="#2471a3", width=8).pack(side="left")

        mkbtn(act_card, "Motors ON", lambda: self.send_gcode(g.motors_on(), log_callback=self._console_log), bg="#27ae60", width=12).pack(fill="x", padx=6, pady=3)
        mkbtn(act_card, "Motors OFF", lambda: self.send_gcode(g.motors_off(None), log_callback=self._console_log), bg="#e74c3c", width=12).pack(fill="x", padx=6, pady=3)
        mkbtn(
            act_card,
            "Prime",
            self.prime,
            bg="#f39c12",
            width=12
        ).pack(fill="x", padx=6, pady=3)

        mkbtn(
            act_card,
            "Aspirate",
            self.aspirate,
            bg="#3498db",
            width=12
        ).pack(fill="x", padx=6, pady=3)

        mkbtn(
            act_card,
            "Dispense",
            self.dispense,
            bg="#2ecc71",
            width=12
        ).pack(fill="x", padx=6, pady=3)
        
        # mkbtn(act_card, "Pipette", lambda:self.send_gcode(g.trigger_pipette(extruder=self.printer["extruder"])),bg="#f39c12", width=12).pack(fill="x", padx=6, pady=3)

        pipette_card = tk.LabelFrame(left, text=" Pipette Control ", bg=BG, fg=TEXT_DIM,
                                     font=("Segoe UI", 10))
        pipette_card.grid(row=1, column=1, columnspan=3, pady=10)

        self.volume_var = tk.DoubleVar()

        self.volume_entry = tk.Entry(pipette_card, textvariable=self.volume_var, width=14)
        self.volume_entry.grid(row=0, column=0)

        mkbtn(pipette_card, "Adjust Volume",
              self.adjust_volume, bg="#27ae60",
            width=14
            ).grid(row=0,column=1, padx=6, pady=6)

        mkbtn(
            pipette_card,
            "Increase Volume",
            lambda: self.send_gcode(g.turn_extruder(0.2)),
            bg="#27ae60",
            width=14
        ).grid(row=1,column=0, padx=6, pady=6)

        mkbtn(
            pipette_card,
            "Decrease Volume",
            lambda: self.send_gcode(g.turn_extruder(-0.2)),
            bg="#e67e22",
            width=14
        ).grid(row=1,column=1, padx=6, pady=6)

        self.speed_var = tk.IntVar(value=3000)
        self.accel_var = tk.IntVar(value=1000)
        self.hold_var = tk.IntVar(value=5)
        self.motor_var = tk.IntVar(value=1)

        # ==========================
        # Profile / Arm Controls
        # ==========================

        

        # ── Custom G-code entry ───────────────────────────────────────────────
        right_col = tk.Frame(self.parent, bg=BG)
        right_col.pack(side="right", fill="y", padx=6, pady=6)
        cmd_frame = tk.Frame(right_col, bg=BG)
        cmd_frame.pack(fill="x", pady=(0, 6))
        tk.Label(cmd_frame, text="G-code:", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        self.manual_entry = tk.Entry(cmd_frame, bg=CARD, fg=TEXT,
                                     insertbackground="white",
                                     font=("Segoe UI", 10), relief="flat")
        self.manual_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=6)
        self.manual_entry.bind("<Return>", lambda event: self.send_gcode(self.manual_entry.get()))
        mkbtn(cmd_frame, "Send", lambda: self.send_gcode(self.manual_entry.get()), bg=ACCENT, fg=BG,
              width=6).pack(side=tk.LEFT)

        # ── Serial console log ────────────────────────────────────────────────
        self.manual_console = st.ScrolledText(
            right_col, height=12, bg="#0d0d0d", fg="#00ff88",
            font=("Courier", 9), state="disabled", relief="flat")
        self.manual_console.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._console_log("Manual control ready. Connect to printer to begin.")

        
    def _move_to_xyz(self):
        self.send_gcode(g.move_absolute([self.x_var.get(),self.y_var.get(), self.z_var.get()]))

    def _get_xyz(self):
        def extract_xyz(msg):
            """
            Extract X, Y, Z values from messages like:
            'X:180.00 Y:80.00 Z:220.00 E:0.00 Count X:14400 Y:6400 Z:88000'

            Ignores:
            - messages starting with 'ok'
            - messages not starting with 'X'
            """

            msg = msg.strip()

            # filter unwanted lines
            if msg.startswith("<< ok"):
                return None

            if not msg.startswith("<< X"):
                return None

            pattern = r"X:([-+]?\d*\.?\d+)\s+Y:([-+]?\d*\.?\d+)\s+Z:([-+]?\d*\.?\d+)"

            match = re.search(pattern, msg)

            if not match:
                return None

            x, y, z = map(float, match.groups())

            self.x_var.set(x)
            self.y_var.set(y)
            self.z_var.set(z)
        self.send_gcode(["M114"], log_callback=extract_xyz)

    def adjust_volume(self):
        vol = self.volume_var.get()
        if vol < self.printer["min_vol"] or vol > self.printer["max_vol"]:
            messagebox.showerror("Error", f"Volume must be between {self.printer["min_vol"]} or {self.printer["max_vol"]}")
            return
        out = [PrinterAction(lambda printer_controller, log_callback:
                       self.vlm_controller.adjust(vol, printer_controller,log_callback), name=f"Adjust pipette to {vol}")]
        self.send_gcode(out)
        return
    
    def prime(self):
        if self.esp_motor_controller:
            self.send_gcode([self.esp_motor_controller.prime(log_callback=self._console_log)], log_callback=self._console_log)
        else:
            self.send_gcode(g.trigger_pipette(self.printer["extruder"]), log_callback=self._console_log)
    
    def aspirate(self):
        if self.esp_motor_controller:
            self.send_gcode([self.esp_motor_controller.aspirate(log_callback=self._console_log)], log_callback=self._console_log)
        else:
            self.send_gcode(g.trigger_pipette(self.printer["extruder"]), log_callback=self._console_log)

    def dispense(self):
        if self.esp_motor_controller:
            self.send_gcode(self.esp_motor_controller.dispense(log_callback=self._console_log), log_callback=self._console_log)
        else:
            self.send_gcode(g.trigger_pipette(self.printer["extruder"]), log_callback=self._console_log)


    def camera_callback(self, camera):
        self.vlm_controller.camera = camera
    
    def send_gcode(self, gcode, log_callback=None):
        if not log_callback:
            log_callback = self._console_log
        if self.print_func:
            if isinstance(gcode, str):
                gcode = [gcode]
            else:
                from gcode_helper import GCodeHelper as g
                gcode = g.flatten(gcode)

            for g in gcode:
                self._console_log(g)
            out = self.print_func(gcode, log_callback=log_callback)
            if out:
                self._console_log(out[1])
        else:
            raise ValueError("No print func defined")
    
    def _console_log(self, msg: str):
        """Thread-safe log to manual console."""
        # Ensure it is a string before scheduling the UI thread update
        log_text = str(msg) if not isinstance(msg, str) else msg

        def _append():
            self.manual_console.config(state="normal")
            self.manual_console.insert(tk.END, log_text + "\n")
            self.manual_console.see(tk.END)
            self.manual_console.config(state="disabled")

        self.after(0, _append)


    def set_printer(self, printer):
        self.printer = printer
        self.vlm_controller.printer_callback(printer)

    def arm(self):
        if self.esp_motor_controller:
            self.send_gcode([self.esp_motor_controller.arm_printer_action(log_callback=self._console_log)], log_callback=self._console_log)
        else:
            messagebox.showerror("Error", "ESP Motor Controller not connected")
    
    
    def estop(self):
        if self.esp_motor_controller:
            self.send_gcode([self.esp_motor_controller.stop_printer_action(log_callback=self._console_log)], log_callback=self._console_log)
        else:
            messagebox.showerror("Error", "ESP Motor Controller not connected")

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Manual UI Test")
    root.geometry("900x400")

    pc = PrinterConnector(parent=root)
    manual_ui = ManualUI(root, print_func=pc.send_gcode)
    root.mainloop()
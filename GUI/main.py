import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from base_window import PrinterConnector, ManualUI
from assignment_window import AssignmentTab
from configuration_window import EquipmentWindow

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
SPLASH_MIN_MS = 1500


def _asset_path(filename: str) -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / filename)
        candidates.append(Path(sys.executable).resolve().parent / "assets" / filename)
    candidates.append(Path(__file__).resolve().parent / "assets" / filename)
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]


def _apply_window_icon(root: tk.Tk) -> None:
    png = _asset_path("logo.png")
    ico = _asset_path("logo.ico")
    try:
        if sys.platform == "win32" and ico.exists():
            root.iconbitmap(default=str(ico))
    except tk.TclError:
        pass
    try:
        if png.exists():
            icon = tk.PhotoImage(file=str(png))
            root.iconphoto(True, icon)
            root._brand_icon = icon
    except tk.TclError:
        pass


def _create_splash(root: tk.Tk):
    png = _asset_path("logo.png")
    if not png.exists():
        return None
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="white")
    try:
        img = tk.PhotoImage(file=str(png))
        factor = 1
        while img.width() // factor > 560 or img.height() // factor > 560:
            factor += 1
        if factor > 1:
            img = img.subsample(factor, factor)
        label = tk.Label(splash, image=img, bg="white", bd=0)
        label.image = img
        label.pack(padx=28, pady=28)
    except tk.TclError:
        splash.destroy()
        return None
    splash.update_idletasks()
    width, height = splash.winfo_reqwidth(), splash.winfo_reqheight()
    x = max((splash.winfo_screenwidth() - width) // 2, 0)
    y = max((splash.winfo_screenheight() - height) // 2, 0)
    splash.geometry(f"{width}x{height}+{x}+{y}")
    try:
        splash.attributes("-topmost", True)
    except tk.TclError:
        pass
    splash.lift()
    splash.update()
    return splash


class App:
    def __init__(self):
        self._app_dir = os.path.dirname(os.path.abspath(__file__))

        self.root = tk.Tk()
        self.root.title("Liquid Handler Controller")
        _apply_window_icon(self.root)
        self.root.withdraw()
        self._splash = _create_splash(self.root)
        self._splash_started = time.monotonic()
        # Printer controller
        self.printer = PrinterConnector(self.root)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        # Create tab frames
        self.config_tab = tk.Frame(self.notebook)
        self.equipment_ui = EquipmentWindow(self.config_tab, printer=self.printer)
        self.notebook.add(self.config_tab, text="Configure Plate")
        self.manual_tab = tk.Frame(self.notebook)
        self.assignment_tab = tk.Frame(self.notebook)
        self.manual_ui = ManualUI(self.manual_tab, self.printer.send_gcode)
        self.assignment_ui = AssignmentTab(self.assignment_tab, example=False)
        self.notebook.add(self.assignment_tab, text="Assignment")
        self.printer.generate_func = self.assignment_ui.generate_gcode
        self.printer.camera_callback = self.camera_callback
        self.equipment_ui.printer_callback = self.printer_callback
        self.equipment_ui._on_printer_select(None)
        self.assignment_ui.assignment._remove_assignment()
        self.assignment_ui.assignment._add_assignment()
        self.assignment_ui.console.send_func = self.printer.send_gcode
        self.esp_motor_controller()
        self.manual_ui.vlm_controller = self.assignment_ui.assignment.vlm_controller


        self.notebook.add(self.manual_tab, text="Manual Control")


        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.equipment_ui._on_printer_select(None)
        remaining_ms = SPLASH_MIN_MS - int((time.monotonic() - self._splash_started) * 1000)
        self.root.after(max(remaining_ms, 200), self._show_main_window)
        self.root.mainloop()

    def _show_main_window(self):
        if self._splash is not None:
            try:
                self._splash.destroy()
            except tk.TclError:
                pass
            self._splash = None
        self.root.deiconify()
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry(
                f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0"
            )
        self.root.lift()
        self.root.focus_force()

    def esp_motor_controller(self):
        self.manual_ui.esp_motor_controller = self.printer.esp_motor_controller
        self.assignment_ui.esp_motor_controller = self.printer.esp_motor_controller

    def printer_callback(self, printer):
        self.assignment_ui.printer_callback(printer)
        self.manual_ui.set_printer(printer)
        self.printer.printer_callback(printer)

    def camera_callback(self, camera):
        self.assignment_ui.camera_callback(camera)
        self.manual_ui.camera_callback(camera)
    def on_tab_changed(self,event):
        selected = self.notebook.select()
        name = self.notebook.tab(selected, "text")
        if name != "Configure Plate":
            self.assignment_ui.set_plate(self.equipment_ui.get_equipment())
            self.assignment_ui.printer_config = self.equipment_ui.get_printer()
            self.manual_ui.set_printer(self.equipment_ui.get_printer())

if __name__ == "__main__":
    try:
        App()
    except Exception:
        import traceback
        from tkinter import messagebox
        err = traceback.format_exc()
        print(err)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Liquid Handler failed to start", err)
        except Exception:
            pass
        raise

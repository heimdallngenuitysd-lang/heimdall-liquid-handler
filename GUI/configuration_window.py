import tkinter as tk
from tkinter import ttk,simpledialog, messagebox
from equipment import YAMLHelper as y
from equipment import Source, Equipment, TipRack, Target
from assignment_window import PlateUI
from gcode_helper import GCodeHelper as g
import re

# ─────────────────────────────────────────────
# Colours
# ─────────────────────────────────────────────
BG = "#1a1b26"
CARD = "#24283b"
ACCENT = "#7aa2f7"
ACCENT_HOVER = "#89b4fa"
SELECTED = "#9ece6a"
TEXT = "#ffffff"
TEXT_DIM = "#565f89"
DISABLED_COL = "#3b3d4e"

class EquipmentMenu(tk.Frame):
    # ── Dropdown options ──────────────────────────────
    type_options = ["Source", "Target", "TipHolder"]
    equipment_options = y.open_equipment()
    source_options = y.get_sources()
    target_options =y.get_targets()
    tipholder_options = y.get_tipholders()
    origin_options = y.open_origin()

    @staticmethod
    def refresh_options():
        EquipmentMenu.equipment_options = y.open_equipment()
        EquipmentMenu.source_options = y.get_sources()
        EquipmentMenu.target_options =y.get_targets()
        EquipmentMenu.tipholder_options = y.get_tipholders()
        EquipmentMenu.origin_options = y.open_origin()

    def equipment_keys():
        return list(EquipmentMenu.equipment_options.keys())

    def source_keys():
        return list(EquipmentMenu.source_options.keys())

    def target_keys():
        return list(EquipmentMenu.target_options.keys())

    def tipholder_keys():
        return list(EquipmentMenu.tipholder_options.keys())
    

    def origin_keys():
        return list(EquipmentMenu.origin_options.keys())+ ["new"]

    def __init__(self, parent, e_type=None, equipment=None, origin=None, *args, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=2, highlightbackground=CARD, bd=0)


        self.select_callback = None
        self.printer_callback = None

        # ── Dropdown variables ─────────────────────────────
        e_type = e_type or EquipmentMenu.type_options[0]
        self.type_var = tk.StringVar(value=e_type)
        equipment = equipment or EquipmentMenu.equipment_keys()[0]
        self.equipment_var = tk.StringVar(value=equipment)
        origin = origin or EquipmentMenu.origin_keys()[0]
        self.origin_var = tk.StringVar(value=origin)

        # ── Coordinate variables ──────────────────────────
        self.x_var = tk.DoubleVar(value=0.0)
        self.y_var = tk.DoubleVar(value=0.0)
        self.z_var = tk.DoubleVar(value=0.0)
        self.printer = None

        self.equipment_callback = None
        self.save_callback = None

        # ── Type ──────────────────────────────────────────
        tk.Label(self, text="Type" , bg=CARD, fg=TEXT).grid(
            row=0, column=0, padx=5, pady=5, sticky="w"
        )

        ttk.OptionMenu(
            self,
            self.type_var,
            self.type_var.get(),
            *EquipmentMenu.type_options,
            command=self._on_type_select
        ).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # ── equipment ──────────────────────────────────────────
        tk.Label(self, text="Equipment", bg=CARD, fg=TEXT).grid(
            row=0, column=2, padx=5, pady=5, sticky="w"
        )

        self.equipment_menu = ttk.OptionMenu(
            self,
            self.equipment_var,
            self.equipment_var.get(),
            *EquipmentMenu.equipment_keys(),
            command=self._on_equipment_select
        )

        self.equipment_menu.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # ── Origin ────────────────────────────────────────
        tk.Label(self, text="Origin", bg=CARD, fg=TEXT).grid(
            row=0, column=4, padx=5, pady=5, sticky="w"
        )

        self.origin_menu = ttk.OptionMenu(
            self,
            self.origin_var,
            self.origin_var.get(),
            *EquipmentMenu.origin_keys(),
            command=self._on_origin_select
        )
        self.origin_menu.grid(row=0, column=5, padx=5, pady=5, sticky="ew")
        self._on_origin_select(None)

        # ── XYZ Entries ───────────────────────────────────
        tk.Label(self, text="X", bg=CARD, fg=TEXT).grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )

        tk.Entry(self, textvariable=self.x_var).grid(
            row=1, column=1, padx=5, pady=5, sticky="ew"
        )

        tk.Label(self, text="Y", bg=CARD, fg=TEXT).grid(
            row=1, column=2, padx=5, pady=5, sticky="e"
        )

        tk.Entry(self, textvariable=self.y_var).grid(
            row=1, column=3, padx=5, pady=5, sticky="ew"
        )

        tk.Label(self, text="Z", bg=CARD, fg=TEXT).grid(
            row=1, column=4, padx=5, pady=5, sticky="e"
        )

        tk.Entry(self, textvariable=self.z_var).grid(
            row=1, column=5, padx=5, pady=5, sticky="ew"
        )

        # ── Buttons ───────────────────────────────────────

        tk.Button(
            self,
            text="Move",
            command=self.move_to_position,
            bg=CARD,
            fg=TEXT

        ).grid(
            row=2, column=1, padx=5, pady=5, sticky="ew"
        )


        tk.Button(
            self,
            text="Set",
            command=self.set_position,
            bg=CARD,
            fg=TEXT
        ).grid(
            row=2, column=3, padx=5, pady=5, sticky="ew"
        )

        

        tk.Button(
            self,
            text="Save",
            command=self.save_position,
            bg=CARD,
            fg=TEXT
        ).grid(
            row=2, column=5, padx=5, pady=5, sticky="ew"
        )


        self.bind("<Button-1>", self._on_select)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._on_select)
        # allow resizing
        # self.grid_columnconfigure(1, weight=1)

    def _on_type_select(self, event):
        self.type = self.type_var.get()
        if self.type == "Source":
            options = EquipmentMenu.source_options
        elif self.type == "Target":
            options = EquipmentMenu.target_options
        elif self.type == "TipHolder":
            options = EquipmentMenu.tipholder_options
        options = list(options.keys())
        if self.type not in self.getType():
            EquipmentMenu.update_option_menu(self.equipment_menu, self.equipment_var, 
                                             options, self._on_equipment_select)
        else:
            EquipmentMenu.update_option_menu(self.equipment_menu, self.equipment_var, 
                                             options, self._on_equipment_select, selected=self.equipment_var.get())
            
    def _on_equipment_select(self, event):
        if self.equipment_callback:
            self.equipment_callback()
        return
    

    def _on_origin_select(self, event):
        if self.origin_var.get() == "new":
            self.x_var.set(0)
            self.y_var.set(0)
            self.z_var.set(0)
            return
        origin = EquipmentMenu.origin_options[self.origin_var.get()]
        self.x_var.set(origin["x"])
        self.y_var.set(origin["y"])
        self.z_var.set(origin["z"])



        if self.equipment_callback:
            self.equipment_callback()
        return

    def getType(self):
        equipment = self.equipment_var.get()

        return EquipmentMenu.equipment_options[equipment]["type"]

    # ── Example callbacks ────────────────────────────────
    def move_to_position(self):
        if self.printer:
            self.printer.send_gcode(g.move_absolute([self.x_var.get(), self.y_var.get(), self.z_var.get()]))

    def set_position(self):
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
        if self.printer:
            self.printer.send_gcode(["M114"], log_callback=extract_xyz)

    def save_position(self):
        if self.origin_var.get() != "new":
            confirm = messagebox.askyesno(
                "Confirm Overwrite",
                f"Overwrite existing point '{self.origin_var.get()}'?"
            )

            if not confirm:
                return
            EquipmentMenu.origin_options[self.origin_var.get()] = {
                "x": self.x_var.get(),
                "y": self.y_var.get(),
                "z": self.z_var.get()
            }
        else:
            while True:
                name = simpledialog.askstring(
                    "Save Point",
                    "Enter name for this point:"
                )

                if name in EquipmentMenu.origin_keys():
                    messagebox.showwarning("Warning!", f"{name} has been used")
                else:
                    break
            
            if not name:
                    return  # user cancelled or empty

            EquipmentMenu.origin_options[name] = {
                "x": self.x_var.get(),
                "y": self.y_var.get(),
                "z": self.z_var.get()
            }
            EquipmentMenu.update_option_menu(self.origin_menu, self.origin_var, 
                                             EquipmentMenu.origin_keys(), self._on_origin_select, name)
            messagebox.showinfo("Saved", f"Point '{name}' saved successfully")
        y.write_yaml(EquipmentMenu.origin_options, r"configs\\points.yaml")
        if self.equipment_callback:
            self.equipment_callback()
        if self.save_callback:
            self.save_callback()
        

    def get_equipment(self):
        name = self.equipment_var.get()
        origin = self.origin_var.get()
        if self.type_var.get() == "Source":
            return Source(name, name, origin)
        elif self.type_var.get() == "Target":
            return Target(name, name, origin)
        elif self.type_var.get() == "TipHolder":
            return TipRack(name, name, origin)

    def refresh_menus(self):
        EquipmentMenu.refresh_options()
        EquipmentMenu.update_option_menu(self.equipment_menu, self.equipment_var, 
                                         EquipmentMenu.equipment_keys(), self._on_equipment_select, self.equipment_var.get())
        EquipmentMenu.update_option_menu(self.origin_menu, self.origin_var, 
                                         EquipmentMenu.origin_keys(), self._on_origin_select, self.origin_var.get())

    def update_option_menu(menu, variable, options, command, selected=None):
        m = menu["menu"]
        m.delete(0, "end")

        for option in options:
            m.add_command(
                label=option,
                command=tk._setit(variable, option, command)
            )

        # set selected value
        if selected in options:
            variable.set(selected)
        elif options:
            variable.set(options[0])
        else:
            variable.set("")

    def _on_select(self, event):
        if self.select_callback:
            self.select_callback(self)
    
    def set_selected(self, selected: bool):
        if selected:
            self.config(highlightbackground=ACCENT, highlightthickness=2)
        else:
            self.config(highlightbackground=CARD, highlightthickness=2)


class EquipmentWindow(tk.Frame):

    def __init__(self, parent, printer=None, master=None, *args, **kwargs):
        super().__init__(parent, bg=BG, *args, **kwargs)

        self.equipment = []
        self.printer = printer
        self.selected_equipment = None
        self.printer_configs = y.open_printer()
        self.preset_configs = y.open_preset()
        self.user_configs = y.open_user()

        self.pack(fill="both", expand=True)
        self.printer_callback = None

        # ── Main layout container ─────────────────────
        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)

        # ── Left panel (1/3 width) ────────────────────
        # Left panel: 0 → 1/3
        self.left_panel = tk.Frame(self.container, bg=CARD)
        self.left_panel.place(relx=0, rely=0, relwidth=0.5, relheight=1)


        self.left_panel.pack_propagate(False)  # keep fixed width

        # ── Right panel (remaining space) ─────────────
        # Right panel: 1/3 → 1
        self.right_panel = tk.Frame(self.container, bg=BG)
        self.right_panel.place(relx=0.5, rely=0, relwidth=0.5, relheight=1)

        self.plate = PlateUI(master=master, parent=self.right_panel)
        self.build_button_bar()

    def refresh_user(self):
        self.user_configs = y.open_user()

    def refresh_plate(self):
        self.plate.clear_plate()
        for e in self.equipment:
            equipment = e.get_equipment()
            if isinstance(equipment, Source):
                self.plate.add_equipment(e.get_equipment(), command=self.configure_source)
            else:
                self.plate.add_equipment(e.get_equipment())


    def get_equipment(self):
        return self.plate.get_equipment()

    def get_printer(self):
        return self.printer_configs[self.printer_var.get()]


    def build_button_bar(self):
        # ── Top button bar ────────────────────────────
        self.button_bar = tk.Frame(self.left_panel, bg=CARD)
        self.button_bar.pack(fill="x", padx=10, pady=10)

        tk.Button(
            self.button_bar,
            text="Add",
            bg=ACCENT,
            fg=TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            command=self.add_item
        ).pack(side="left", padx=(0, 5))

        tk.Button(
            self.button_bar,
            text="Delete",
            bg="#f7768e",
            fg=TEXT,
            activebackground="#ff8899",
            activeforeground=TEXT,
            relief="flat",
            command=self.delete_item
        ).pack(side="left", padx=(5, 0))


        # ── Printer variable ───────────────────────────
        tk.Label(self.button_bar, bg=BG, fg=TEXT, text="Printer").pack(side="left", padx=(10, 10))
        self.printer_var = tk.StringVar(value="Select")

        # assume you have this from YAML or config
        printer_options = y.list_printers()
        self.printer_var = tk.StringVar(value= self.user_configs["printer"] if self.user_configs["printer"] in printer_options else list(printer_options)[0])

        self.printer_menu = ttk.OptionMenu(
            self.button_bar,
            self.printer_var,
            self.printer_var.get(),
            *printer_options,
            command=self._on_printer_select
        )

        self.printer_menu.pack(side="left", padx=(0, 10))
        # ── Printer variable ───────────────────────────
        tk.Label(self.button_bar, bg=BG, fg=TEXT, text="Preset").pack(side="left", padx=(10, 10))
        
        # assume you have this from YAML or config
        preset_options = list(y.list_preset()) + ["(new)"]
        self.preset_var =  tk.StringVar(value=(self.get_printer().get("preset", None) or list(preset_options)[0]))

        self.preset_menu = ttk.OptionMenu(
            self.button_bar,
            self.preset_var,
            self.preset_var.get(),
            *preset_options,
            command=self._on_preset_select
        )

        self.preset_menu.pack(side="left", padx=(0, 10))
        self._on_preset_select(None)

        tk.Button(
            self.button_bar,
            text="Save Preset",
            bg=ACCENT,
            fg=TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            command=self.save_preset
        ).pack(side="left", padx=(0, 5))

        tk.Button(
            self.button_bar,
            text="Reset Volume",
            bg=ACCENT,
            fg=TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            command=self.reset_set_volume
        ).pack(side="left", padx=(0, 5))

    def _on_printer_select(self, event):
        # assume you have this from YAML or config
        preset_options = list(y.list_preset()) + ["(new)"]
        self.preset_var.set((self.get_printer().get("preset", None) or list(preset_options)[0]))
        self._on_preset_select(None)
        self.refresh_user()
        self.user_configs["printer"] = self.printer_var.get()
        y.write_yaml(self.user_configs, r"configs\\user.yaml")
        if self.printer_callback:
            self.printer_callback(y.open_printer()[self.printer_var.get()])
        return
    
    def _on_preset_select(self, event):
        preset = self.preset_var.get()
        if preset == "(new)":
            return
        preset = y.open_preset().get(preset, None)
        if preset == None:
            return
        for e in self.equipment:
            e.destroy()
        self.equipment.clear()
        self.selected_equipment = None
        for e in preset.keys():
            e = preset[e]
            self.add_item(e_type=e["type"], equipment=e["equipment"], origin=e["origin"])
        
        self.update_last_preset()

        return

    def add_item(self, e_type=None, equipment=None, origin=None):
        if len(self.equipment) > 4:
            return
        menu = EquipmentMenu(self.left_panel, e_type=e_type, equipment=equipment, origin=origin)
        menu.select_callback = self._on_equipment_selected
        menu.save_callback = self.refresh_origin
        menu.equipment_callback = self.refresh_plate
        menu.printer = self.printer
        self.equipment.append(menu)

        menu.pack(fill="x", padx=5, pady=5)
        self.refresh_plate()
        return
    def _on_equipment_selected(self, widget):
        # unhighlight old
        if self.selected_equipment:
            self.selected_equipment.set_selected(False)

        # set new
        self.selected_equipment = widget
        widget.set_selected(True)

    def update_last_preset(self):
        self.printer_configs[self.printer_var.get()]["preset"] = self.preset_var.get()
        y.write_yaml(self.printer_configs, r"configs\\printers.yaml")

    def refresh_origin(self):
        for e in self.equipment:
            e.refresh_menus()

    def delete_item(self):
        if not self.selected_equipment:
            return

        widget = self.selected_equipment

        self.equipment.remove(widget)
        widget.destroy()
        self.selected_equipment = None
        self.refresh_plate()
        return
    
    def equipment_to_dict(self):
            out = {}
            for e in self.equipment:
                name = e.equipment_var.get()
                i = 0
                while name in out.keys():
                    i += 1
                    name = e.equipment_var.get() + str(i)
                out[name] = {"type": e.type_var.get(),
                           "equipment": e.equipment_var.get(),
                           "origin": e.origin_var.get()}
            return out
    
    def save_preset(self):
   

        if self.preset_var.get() != "(new)":
            confirm = messagebox.askyesno(
                "Confirm Overwrite",
                f"Overwrite existing preset '{self.preset_var.get()}'?"
            )

            if not confirm:
                return
            self.preset_configs[self.preset_var.get()] = self.equipment_to_dict()
            y.write_yaml(self.preset_configs, r"configs\\preset.yaml")
        else:
            while True:
                name = simpledialog.askstring(
                    "Save Preset",
                    "Enter name for this preset:",
                    initialvalue=f"{self.printer_var.get()}"
                )

                if name in self.preset_configs.keys():
                    messagebox.showwarning("Warning!", f"{name} has been used")
                else:
                    break
            
            if not name:
                    return  # user cancelled or empty

            self.preset_configs[name] = self.equipment_to_dict()
            messagebox.showinfo("Saved", f"Preset '{name}' saved successfully")
            y.write_yaml(self.preset_configs, r"configs\\preset.yaml")
            EquipmentMenu.update_option_menu(self.preset_menu, self.preset_var, ["(new)"] + list(y.list_preset()), self._on_preset_select, name)
        self.update_last_preset()
        
    def configure_source(self, source, source_index):
        max_vol = source.volume
        bottle = source.bottles[source_index[0]][source_index[1]]

        root = self.winfo_toplevel()

        popup = tk.Toplevel(root)
        popup.title("Configure Source")
        popup.configure(bg=BG)
        popup.transient(root)
        popup.grab_set()

        container = tk.Frame(popup, bg=BG, padx=15, pady=15)
        container.pack(fill="both", expand=True)

        tk.Label(
            container,
            text="Volume (µL)",
            bg=BG,
            fg=TEXT
        ).pack(anchor="w")

        volume_entry = tk.Entry(
            container,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat"
        )
        volume_entry.insert(0, str(bottle.current_volume))
        volume_entry.pack(fill="x", pady=(5, 15))

        def submit():
            try:
                volume = int(volume_entry.get())

                if volume <= 0 or volume > max_vol:
                    raise ValueError

                source.set_volume(index=source_index, volume=volume)
                popup.destroy()

            except ValueError:
                messagebox.showerror(
                    "Error",
                    f"Volume must be between 1 and {max_vol} µL!"
                )
                volume_entry.delete(0, tk.END)
                volume_entry.insert(0, str(bottle.current_volume))

        tk.Button(
            container,
            text="Submit",
            command=submit,
            bg=ACCENT,
            fg=TEXT,
            activebackground=ACCENT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2"
        ).pack()

        popup.update_idletasks()

        # Center on parent
        x = root.winfo_rootx() + (root.winfo_width() - popup.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - popup.winfo_reqheight()) // 2
        popup.geometry(f"+{x}+{y}")

        return BG, None
        
    def reset_set_volume(self, event=None):
        for s in self.plate.source_uis:
            s.equipment.reset_set_volume()


# ── Example usage ────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Equipment Menu Example")
    root.state("zoomed")

    window = EquipmentWindow(root)
    window.pack()

    # menu = EquipmentMenu(root, bd=2, relief="groove", padx=10, pady=10)
    # menu.pack(padx=20, pady=20, fill="x")

    # menu1 = EquipmentMenu(root, bd=2, relief="groove", padx=10, pady=10)
    # menu1.save_callback = menu.refresh_menus
    # menu.save_callback = menu1.refresh_menus
    # menu1.pack(padx=20, pady=20, fill="x")

    root.mainloop()
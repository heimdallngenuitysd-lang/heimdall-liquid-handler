import os
from gcode_helper import GCodeHelper as g
from equipment import Equipment, TipRack, Source, Target, Assignment, YAMLHelper
from esp_comm import ZMQClient
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, scrolledtext
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import csv
from datetime import datetime
from tkinter import filedialog
import shutil
import tempfile
import ast 
from pathlib import Path


from vlm_controller import VLMController

#TODO: something is wrong with the check boxes in the first assignment

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


class AssignmentUI(tk.Frame):

    def __init__(self, parent, update_ui=None, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)

        self.vlm_controller = VLMController()
        self.dobot_controller = None
        self.printer = YAMLHelper.open_default_printer()
        self.assignments = []
        self.curr_assignment = Assignment(name="Assignment 1", colour=ASSIGNMENT_COLORS[0], volume_controller=self.vlm_controller)
        self.assignments.append(self.curr_assignment)
        self.update_ui = update_ui
        self.reset_volume = None
        self.assignment_name_var = tk.StringVar(value="") 
        self.volume_var = tk.StringVar()
        self.hold_var = tk.StringVar(value="5")
        self.accel_var = tk.StringVar(value="1000")
        self.speed_var = tk.StringVar(value="3000")
        self.shake_var = tk.BooleanVar(value=False)
        self.reverse_var = tk.BooleanVar(value=False)
        self.change_tip_var = tk.BooleanVar(value=False)
        self.prewet_var = tk.BooleanVar(value=False)
        self.heat_duration_var = tk.IntVar(value=600)
        self.dip_var = tk.BooleanVar(value=False)
        self.capture_var = tk.BooleanVar(value=False)
         # Create a temporary file for the log


        self.get_equipment = None
        self.get_tipholder = None



        self.sort_ascending = True
        
        # ── Setup base container ────────────────────────
        self._setup_container()

        # ── UI ──────────────────────────────────────────
        self._build_ui()

    # ─────────────────────────────────────────────────────────────
    # UI CONTAINER SETUP
    # ─────────────────────────────────────────────────────────────
    def _setup_container(self):
        # Anchor the entire UI component to the parent frame
        self.pack(side=tk.LEFT, fill=tk.Y)
        self.pack_propagate(False)
        
        # self.inner now acts as a direct container frame instead of a canvas child
        self.inner = tk.Frame(self, bg=CARD)
        self.inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # ─────────────────────────────────────────────────────────────
    # UI ENTRY POINT
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_assignment_section()
        self._build_current_assignment_section()

    # ─────────────────────────────────────────────────────────────
    # Assignment section
    # ─────────────────────────────────────────────────────────────
    def _build_assignment_section(self):
        assignment_row = tk.Frame(self.inner, bg=CARD)
        assignment_row.pack(fill=tk.X)
        tk.Button(
            assignment_row,
            text="Load CSV",
            command=self.load_assignments_from_csv,
            bg=TEXT_DIM,
            fg=TEXT,
            relief=tk.FLAT,
            padx=4,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(6, 0))

        tk.Button(
            assignment_row,
            text="Save CSV",
            command=self.log_assignments,
            bg=SELECTED,
            fg=TEXT,
            relief=tk.FLAT,
            padx=4,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(6, 0))

        tk.Button(
            assignment_row,
            text="Sort",
            command=self._sort_assignments,
            bg=SELECTED,
            fg=TEXT,
            relief=tk.FLAT,
            padx=4,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(6, 0))


        tk.Label(
            self.inner,
            text="Assignments",
            font=("Segoe UI", 10, "bold"),
            fg=TEXT,
            bg=CARD
        ).pack(anchor=tk.W, pady=(8, 4))

        listbox_frame = tk.Frame(self.inner, bg=CARD)
        listbox_frame.pack(fill=tk.X, pady=(0, 6))

        listbox_scrollbar = tk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.assignment_listbox = tk.Listbox(
            listbox_frame,
            height=6,
            width=35,
            bg=CARD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground=BG,
            exportselection=False,   
            font=("Segoe UI", 9),
            yscrollcommand=listbox_scrollbar.set 
        )
        self.assignment_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        listbox_scrollbar.config(command=self.assignment_listbox.yview)

        # Bind mousewheel to ONLY scroll the listbox when hovering over it
        def _on_listbox_wheel(event):
            self.assignment_listbox.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self.assignment_listbox.bind("<MouseWheel>", _on_listbox_wheel)

        self.assignment_listbox.bind(
            "<<ListboxSelect>>",
            self._select_assignment
        )
        if self.curr_assignment:
            self.assignment_listbox.insert(tk.END, self.curr_assignment)

        btn_row = tk.Frame(self.inner, bg=CARD)
        btn_row.pack(fill=tk.X)

        tk.Button(
            btn_row,
            text="Add assignment",
            command=self._add_assignment,
            bg=ACCENT,
            fg=BG,
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            btn_row,
            text="Remove",
            command=self._remove_assignment,
            bg=CARD,
            fg=TEXT,
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT)

        tk.Button(
        btn_row,
        text="▲",  # Changed from "Remove" to an upward arrow
        command=lambda: self.move_curr_assignment(False),
        bg=CARD,
        fg=TEXT,
        relief=tk.FLAT,
        padx=4,
        pady=4,
        cursor="hand2"
        ).pack(side=tk.LEFT)
        
        tk.Button(
            btn_row,
            text="▼",  # Changed to a downward arrow
            command=lambda: self.move_curr_assignment(True),  # Assuming False moves it down
            bg=CARD,
            fg=TEXT,
            relief=tk.FLAT,
            padx=4,
            pady=4,
            cursor="hand2"
        ).pack(side=tk.LEFT)


        

    # ─────────────────────────────────────────────────────────────
    # Current assignment
    # ─────────────────────────────────────────────────────────────
    def _build_current_assignment_section(self):
        # --- Name Section ---
        tk.Label(
            self.inner,
            text="Current assignment",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_DIM,
            bg=CARD
        ).pack(anchor=tk.W, pady=(12, 2))

        tk.Entry(
            self.inner,
            textvariable=self.assignment_name_var,
            width=20,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT
        ).pack(fill=tk.X, pady=2)

        tk.Button(
            self.inner,
            text="Apply Name",
            command=self._rename_assignment,
            bg=CARD,
            fg=TEXT,
            relief=tk.FLAT,
            padx=6,
            pady=4,
            cursor="hand2"
        ).pack(anchor=tk.W, pady=4)

        # --- Volume Section ---
        tk.Label(
            self.inner,
            text="Volume",
            font=("Segoe UI", 9, "bold"),
            fg=TEXT_DIM,
            bg=CARD
        ).pack(anchor=tk.W, pady=(8, 2))

        volume_entry = tk.Entry(
            self.inner,
            textvariable=self.volume_var,
            width=20,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT
        )
        volume_entry.pack(fill=tk.X, pady=2)
        volume_entry.bind("<Return>", lambda _e: self._apply_volume())
        volume_entry.bind("<FocusOut>", lambda _e: self._apply_volume())

    def _apply_volume(self):
        raw = (self.volume_var.get() or "").strip()
        if not raw:
            return
        try:
            volume = round(float(raw), self.printer["decimal_position"])
        except (TypeError, ValueError):
            return
        if self.curr_assignment and volume == self.curr_assignment.volume:
            return
        self._edit_assignment(volume=volume)

    def _add_assignment(self, name=None, tip_holder=None, 
                    tip_index=None,source=None, source_index=None,
                    target=None, target_index=None, volume_controller=None):
        if not name:
            if self.curr_assignment:
                name = f"Assignment {len(self.assignments)+1}"
            else:
                name = "Assignment 1"
        
        if not volume_controller:
            volume_controller = self.vlm_controller
        if not tip_holder and self.get_tipholder:
            tip_holder=self.get_tipholder()
        
        colour_index = (len(self.assignments) + 1)%7
        new_assignment = Assignment(name=name, tip_holder=tip_holder, tip_index=tip_index, 
                                         source=source, source_index=source_index, target=target, 
                                         target_index=target_index, volume=self.printer["max_vol"], colour=ASSIGNMENT_COLORS[colour_index],
                                         volume_controller=volume_controller)
        self.assignments.append(new_assignment)

        self.curr_assignment = new_assignment
        self.refresh_assignments()
        self.refresh_checkboxes()
        if self.update_ui:
            self.update_ui(self)
        return
    
    def _remove_assignment(self):
        to_remove = self.curr_assignment
        to_remove.remove()
        index = self.assignments.index(to_remove)
        self.assignments.remove(to_remove)
        # sort after removing assignment
        

        if not self.assignments:
            self.curr_assignment=None
            self._add_assignment()
        else:
            self.curr_assignment = self.assignments[min(len(self.assignments)-1,index)]
        if self.update_ui:
            self.update_ui(self)
        self.refresh_assignments()
        self.refresh_checkboxes()
        return
    def _edit_assignment(self, *args, **kwargs):
        volume = kwargs.get('volume')
        if volume and (volume < self.printer["min_vol"] or volume > self.printer["max_vol"]*5):
            messagebox.showerror("invalid Volume!", f"Volume must be between {self.printer["min_vol"]} and {self.printer["max_vol"]*5}")
            volume = None
        out = self.curr_assignment.edit_assignment(
        *args, **kwargs
        )

        self._refresh_curr_assignment()
        self.refresh_assignments()
        return out
    
    def toggle_option(self, option_type):
        """Keep assignment flags in sync if they are set from CSV or code."""
        mappings = {
            "shake": self.shake_var,
            "dip": self.dip_var,
            "reverse": self.reverse_var,
            "change_tip": self.change_tip_var,
            "prewet": self.prewet_var,
        }
        var = mappings[option_type]
        self._edit_assignment(**{option_type: var.get()})

    def refresh_checkboxes(self):
        if not self.curr_assignment:
            return
        self.shake_var.set(bool(self.curr_assignment.shake))
        self.dip_var.set(bool(self.curr_assignment.dip))
        self.reverse_var.set(bool(self.curr_assignment.reverse))
        self.change_tip_var.set(bool(self.curr_assignment.change_tip))
        self.prewet_var.set(bool(self.curr_assignment.prewet))

    def _select_assignment(self, event):
        listbox = event.widget
        selection = listbox.curselection()

        if selection:
            index = selection[0]
            self.curr_assignment = self.assignments[index]
            
            # --- Synchronise Checkboxes to Selected Assignment Data ---
            self.refresh_checkboxes()
            self._refresh_curr_assignment()
            
            if self.update_ui:
                self.update_ui(self)
            return
        return
    def _rename_assignment(self):
        self.curr_assignment.name = self.assignment_name_var.get()
        self._refresh_curr_assignment()
        return
    def _refresh_curr_assignment(self):
        index = self.assignments.index(self.curr_assignment)
        self.assignment_listbox.delete(index)
        self.assignment_listbox.insert(index, str(self.curr_assignment))
    
    
    def refresh_assignments(self):
        self.assignment_listbox.delete(0, tk.END)

        for assignment in self.assignments:
            self.assignment_listbox.insert(tk.END, assignment)

        #Automatically select the current assignment
        if self.curr_assignment:
            try:
                index = self.assignments.index(self.curr_assignment)
                self.assignment_listbox.selection_clear(0, tk.END)
                self.assignment_listbox.selection_set(index)
                self.assignment_listbox.see(index)
            except ValueError:
                # curr_assignment not in list (shouldn't happen)
                pass
            
        self._refresh_curr_assignment()

    def generate_gcode(self, printer_config, volume_adjust=True, esp_motor_controller=None, log_callback=None):
        if self.reset_volume:
            self.reset_volume()
        out = g.setup()
        error = []
        self.vlm_controller.first_adjust = False
        for a in self.assignments:
            if not a.is_valid():
                error.append(a.name)
        if error:
            error_msg = ""
            for e in error:
                error_msg = error_msg + f"{e} is not a valid assignment! \n"
            messagebox.showerror("Invalid Assignments", error_msg)
            return None, None
        
    
        sorted_assignments = Assignment.handle_assignments(self.assignments, printer_config)

        def compare_source(index1, index2):
            return (sorted_assignments[index1].source.name == sorted_assignments[index2].source.name and
                sorted_assignments[index1].source_index == sorted_assignments[index2].source_index)

        a = sorted_assignments[0]
        a.tip_holder.clear_reserved_index()
        tip = False

        if len(sorted_assignments)>1 and compare_source(0, 1) and (not (a.change_tip)):
            tip = True    

        out.extend(a.generate_gcode(printer=printer_config, volume_adjust=volume_adjust, 
                                        esp_motor_controller=esp_motor_controller, 
                                        log_callback=log_callback, remove_tip= (not tip), dobot=self.dobot_controller))

        if len(sorted_assignments) == 1:
            self.update_ui(self)
            self.reset_volume()
            out = g.flatten(out)
            return sorted_assignments, out

        for index in range(len(sorted_assignments)-2):
            out.extend(sorted_assignments[index+1].generate_gcode(printer=printer_config, volume_adjust=volume_adjust, 
                                        esp_motor_controller=esp_motor_controller, 
                                        log_callback=log_callback, get_tip=(not tip), remove_tip=(not compare_source(index+1, index + 2)), dobot=self.dobot_controller))
            
            tip = (compare_source(index+1, index+2) and (not (sorted_assignments[index+1].change_tip)))

        
        out.extend(sorted_assignments[-1].generate_gcode(printer=printer_config, volume_adjust=volume_adjust, 
                                        esp_motor_controller=esp_motor_controller, 
                                        log_callback=log_callback, get_tip=(not tip), remove_tip=True, dobot=self.dobot_controller))

        out = g.flatten(out)
        self.reset_volume()
        self.update_ui(self)

        return sorted_assignments, out
        
    def clear_assignments(self):
        for i in range(len(self.assignments)):
            self._remove_assignment()
        
    def printer_callback(self, printer):
        self.printer = printer
        self.vlm_controller.printer_callback(printer)
        if self.printer.get("dobot_server", None):
            self.dobot_controller = ZMQClient()


    def get_current_assignments(self):
        """Return a copy of the current assignments list."""
        if not self.assignments:
            return []
        return self.assignments.copy() # returns copy of the list
    
    def log_assignments(self, assignments=None): #takes in assignments as argument
        """Log assignments to CSV when sent to printer."""
        if assignments is None:
            assignments = self.get_current_assignments() # gets assignment from whatever is in the list
        
        if not assignments:
            print("No assignments to log")
            return False
        
        # Filter valid assignments
        valid_assignments = [a for a in assignments if a.is_valid()] # list of valid assignments
        
        if not valid_assignments:
            print("No valid assignments to log")
            return False
        
        try:
            file_path = filedialog.asksaveasfilename(title="Save Assignments to CSV",
            initialdir= Path(__file__).parent.resolve(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
            
            if file_path:
                if not file_path.endswith('.csv'):
                    file_path += '.csv'
            else:
                return
            Assignment.save_assignments_to_csv(valid_assignments, file_path)
            
        except PermissionError:
            print("Permission denied: Cannot write to log file. Is it open in Excel?")
            return False
        except FileNotFoundError:
            print(f"Directory not found: {os.path.dirname(self.log_file) or 'current directory'}")
            print(f"   Log file: {self.log_file}")
            return False
        except OSError as e:
            print(f"OS Error writing to log file: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error logging assignments: {e}")
            return False
    def load_assignments_from_csv(self):
        if not self.get_equipment:
            print("get equipment undefined")
            return None
        self.clear_assignments()
        equipment = self.get_equipment()
        new_assignments = Assignment.load_assignments_from_csv(equipment)
        if new_assignments:
            self.assignments.extend(new_assignments)
            for a in new_assignments:
                a.volume_controller = self.vlm_controller
            self.assignments.pop(0)
            self.curr_assignment = self.assignments[0]
        self.refresh_assignments()
        self.update_ui(self)
    
    def _sort_assignments(self):
        self.assignments = Assignment.sort_assignments_by_volume(self.assignments, self.printer)
        self.refresh_assignments()

    def move_curr_assignment(self, direction: bool):
        direction = 1 if direction else -1
        curr_index = self.assignments.index(self.curr_assignment)
        target_index = curr_index + direction
        if target_index < 0 or target_index > len(self.assignments) - 1:
            return
        curr_assignment = self.curr_assignment
        self.assignments[curr_index] = self.assignments[target_index]
        self.assignments[target_index] = curr_assignment
        self.refresh_assignments()
        return
        



class EquipmentUI(tk.LabelFrame):
    def __init__(self, master, equipment: Equipment, plate_size=235, command=None, row_select=False, **kwargs):
        kwargs.setdefault("bg", TEXT_DIM)
        super().__init__(master, text=equipment.name, **kwargs)
        
        self.master = master
        self.equipment = equipment
        self.plate_size = plate_size
        self.command = command
        self.row_select = row_select
        self.buttons = {}

        self._set_equipment(equipment=equipment)
        self._calculate_frame_size()

        self._build_grid()
        self._auto_size()

    def _calculate_frame_size(self):
        self.frame_width = (self.equipment.cols) * abs(self.equipment.dx) / self.plate_size
        self.frame_height = (self.equipment.rows) * abs(self.equipment.dy) / self.plate_size

    def disable_buttons(self):
        for b in self.buttons.values():
            b.config(state="disabled")
    
    def enable_buttons(self):
        for b in self.buttons.values():
            b.config(state="normal")

    def _mm_to_frame(self, mm, frame):
        return (mm / self.plate_size) * frame

    def _set_equipment(self, equipment: Equipment):
        self.rows = equipment.rows
        self.cols = equipment.cols
        self.origin = equipment.orientation
        self.button_origin = equipment.origin.t
        self.equipment = equipment

    def _build_grid(self):
        # 1. Placement logic
        x, y = self._frame_center()
        relx = x / self.plate_size
        rely = 1 - (y / self.plate_size)

        half_w = self.frame_width / 2
        half_h = self.frame_height / 2
        relx = max(half_w, min(relx, 1 - half_w))
        rely = max(half_h, min(rely, 1 - half_h))

        self.place(
            relx=relx, rely=rely,
            relheight=self.frame_height, relwidth=self.frame_width,
            anchor="center"
        )
        self.grid_propagate(False)

        # 2. Configure Grid Weights
        col_offset = 1 if self.row_select else 0

        if self.row_select:
            self.grid_columnconfigure(0, weight=0)  
            self.grid_rowconfigure(self.rows, weight=0)  

        for c in range(self.cols):
            self.grid_columnconfigure(c + col_offset, weight=1)
        for r in range(self.rows):
            self.grid_rowconfigure(r, weight=1)

        # 3. Create Main Button Grid
        for r in range(self.rows):
            for c in range(self.cols):
                # Get the mapped visual grid coordinates
                rr, cc = self._map_origin(r, c)

                btn = tk.Button(
                    self,
                    text=f"{self.equipment.get_name([c, r])}",
                    bg=CARD, fg=TEXT,
                    activebackground=ACCENT_HOVER, activeforeground=TEXT,
                    relief=tk.FLAT, bd=0,
                    highlightthickness=1, highlightbackground="#343a55",
                    cursor="hand2",
                )
                # Callbacks pass logical (r, c) to maintain correct machine logic coordinates
                btn.config(command=lambda r=r, c=c, b=btn: self._on_click(r, c, button=b))
                
                btn.grid(row=rr, column=cc + col_offset, padx=2, pady=2, sticky="nsew")
                
                # STOCKED BY VISUAL COORDINATES (rr, cc)
                self.buttons[(r, c)] = btn

# 4. Add Triggers optionally
        if self.row_select:
            # Sizing parameters for the trigger buttons
            TRIGGER_WIDTH = 1   # Character width
            TRIGGER_HEIGHT = 1  # Character height

            # Row Triggers (Left Rail: Column 0)
            for r in range(self.rows):
                rr, _ = self._map_origin(r, 0)
                tk.Button(
                    self, text="➡", bg=ACCENT, fg=TEXT, relief=tk.RAISED,
                    width=TRIGGER_WIDTH, height=TRIGGER_HEIGHT,
                    bd=1, padx=0, pady=0, # Clear inner breathing room to make it smaller
                    command=lambda r_vis=r: self._trigger_row(r_vis)
                ).grid(row=rr, column=0, padx=(1, 1), pady=1, sticky="") # Removed "nsew" so it doesn't stretch to fit the row cell height

            # Column Triggers (Bottom Rail: Row self.rows)
            for c in range(self.cols):
                _, cc = self._map_origin(0, c)
                tk.Button(
                    self, text="⬆", bg=ACCENT, fg=TEXT, relief=tk.RAISED,
                    width=TRIGGER_HEIGHT, height=TRIGGER_WIDTH,
                    bd=1, padx=0, pady=0,
                    command=lambda c_vis=c: self._trigger_col(c_vis)
                ).grid(row=self.rows, column=cc + col_offset, padx=1, pady=(1, 1), sticky="") # Removed "nsew" so it doesn't stretch to fit the column cell width

    def _trigger_row(self, visual_r):
        # Sweeps across the visual row columns
        for c in range(self.cols):
            self.buttons[(visual_r, c)].invoke()

    def _trigger_col(self, visual_c):
        # Sweeps down the visual column rows
        for r in range(self.rows):
            self.buttons[(r, visual_c)].invoke()

    def _on_click(self, r, c, button=None):
        if self.command:
            self.command(r, c)
        else:
            print(f"Clicked: ({r}, {c})")

    def _map_origin(self, r, c):
        if self.origin in ["top-left", "top_left"]:
            return r, c
        elif self.origin in ["top-right", "top_right"]:
            return r, self.cols - 1 - c
        elif self.origin in ["bottom-left", "bottom_left"]:
            return self.rows - 1 - r, c
        elif self.origin in ["bottom-right", "bottom_right"]:
            return self.rows - 1 - r, self.cols - 1 - c
        return r, c
        
    def _frame_center(self):
        half_x = self.frame_width/2 * self.plate_size
        half_y = self.frame_height/2 * self.plate_size
        if self.origin in ["top_left", "top-left"]:
            half_y = -half_y
        elif self.origin in ["top_right", "top-right"]:
            half_x = -half_x
            half_y = -half_y
        elif self.origin in ["bottom_right", "bottom-right"]:
            half_x = -half_x

        x = self.button_origin[0] + half_x
        y = self.button_origin[1] + half_y
        return x, y
        
    def set_button_colour(self, logical_row, logical_col, colour):
        # Maps coordinates to visual keys before accessing dictionary
        # rr, cc = self._map_origin(logical_row, logical_col)
        # self.buttons[(rr, cc)].config(bg=colour)
        self.buttons[(logical_row, logical_col)].config(bg=colour)

    def set_row_colour(self, row, colour, reset=False):
        if reset: self.reset_colours()
        for col in range(self.cols):
            self.set_button_colour(row, col, colour)

    def set_column_colour(self, col, colour, reset=False):
        if reset: self.reset_colours()
        for row in range(self.rows):
            self.set_button_colour(row, col, colour)

    def reset_colours(self):
        for btn in self.buttons.values():
            btn.config(bg=CARD)

    def _auto_size(self):
        self.propagate(False)
    
    def show_assignment(self, assignment):
        return

    def _draw_origin_marker(self):
        # The visual origin coordinate is always (0, 0) in grid space
        # regardless of orientation strings, because _map_origin(0,0) targets visual zero-zero.
        origin_btn = self.buttons.get((0,0))
        if origin_btn is None: return

        dot = tk.Canvas(origin_btn, width=8, height=8, highlightthickness=0, bg=origin_btn.cget("bg"))
        dot.create_oval(0, 0, 8, 8, fill="red", outline="red")
        dot.place(relx=0.15, rely=0.15, anchor="center")


class TargetUI(EquipmentUI):
    def __init__(self, master, equipment, row_select=True, **kwargs):
        if not isinstance(equipment, Target):
            raise ValueError("wrong equipment type")
        super().__init__(master, equipment, row_select=row_select, **kwargs)

    def _calculate_frame_size(self):
        self.frame_width = (self.equipment.cols) * min(max(abs(self.equipment.dx), 11), 40) / self.plate_size
        self.frame_height = (self.equipment.rows) * min(max(11, abs(self.equipment.dy)), 40) / self.plate_size

    def _on_click(self, r, c, button=None):
        if self.command and button:
            out = self.command(target=self.equipment, target_index=[c, r])
            if out:
                self.set_button_colour(r, c, out)
            else:
                button.config(bg=BG)
        else:
            print(f"Clicked: {r, c}")

    def show_assignment(self, assignment: Assignment):
        self.reset_colours()
        if assignment.target_index:
            for t in assignment.target_index:
                self.set_button_colour(t[1], t[0], assignment.colour)
class SourceUI(EquipmentUI):
    def __init__(self, master, equipment, plate_size=235, command=None, row_select=False, **kwargs):
        super().__init__(master, equipment, plate_size, command, row_select, **kwargs)
        

        self.csv_frame = tk.Frame(self)
        self.csv_frame.grid(row=self.rows, column=0, sticky="w") # sticky="w" prevents frame stretching

        small_font = ("TkDefaultFont", 5)
        self.load_button = tk.Button(
            self.csv_frame,
            text="L",
            bg=CARD, fg=TEXT,
            command=self.load_csv,
            font=small_font
        )
        self.load_button.pack(side=tk.LEFT, padx=(0,2))  # Small horizontal gap between buttons

        self.save_button = tk.Button(
            self.csv_frame,
            text="S",
            bg=CARD, fg=TEXT,
            command=self.save_csv,
            font=small_font
        )
        self.save_button.pack(side=tk.LEFT)


    def _on_click(self, r, c, button=None):
        if self.command and button:
            colour, old = self.command(source=self.equipment, source_index=[c,r])
            if colour:
                button.config(bg=colour)
            else:
                button.config(bg=CARD)
            
            if old:
                old_button = self.buttons[(old[1], old[0])]
                old_button.config(bg=CARD)
        else:
            print(f"Clicked: {r,c}")

    def load_csv(self, *args, **kwargs):
        self.equipment.load_config()

    def save_csv(self, *args, **kwargs):
            self.equipment.save_config()
    
    def show_assignment(self, assignment:Assignment):
        self.reset_colours()
        if assignment.source_index:
            self.set_button_colour(assignment.source_index[1], assignment.source_index[0], assignment.colour)
    def reset_volume(self):
        try:
            self.equipment.reset_volume()
        except:
            return

class TipHolderUI(EquipmentUI):
    def __init__(self, master, equipment, row_select=True, **kwargs):
        if not isinstance(equipment, TipRack):
            raise ValueError("wrong equipment type")
        super().__init__(master, equipment, row_select=row_select, **kwargs)

    def _on_click(self, r, c, button=None):

        state = self.equipment.add_index([c,r])

        if state:
            button.config(bg=SELECTED)
        else:
            button.config(bg=CARD)
            self.equipment.remove_index([c,r])

            # print(f"Clicked: {r,c}")
    
    def show_assignment(self, assignment):
        self.set_button_colour(assignment.tip_index[1], assignment.tip_index[0], assignment.colour)
    def show_tip_taken(self):
        for t in self.equipment.used_index:
            self.set_button_colour(t[1], t[0], ASSIGNMENT_COLORS[0])

        for t in self.equipment.reserved_index:
            self.set_button_colour(t[1], t[0], ASSIGNMENT_COLORS[1])
    
    def use_reserved_tips(self):
        self.equipment.use_reserved_index()
        self.show_tip_taken()

class PlateUI(tk.Frame):
    def __init__(self, master, parent, bg="#222222", padding_scale=0.95, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)

        self.parent = parent
        self.padding_scale = padding_scale
        self.source_uis = []
        self.target_uis = []
        self.tip_uis = []
        self.edit_callback = None

        # Prevent children from resizing container
        self.pack_propagate(False)

        self._build_ui()

        # Resize whenever parent changes size
        self.parent.bind("<Configure>", self._resize_container)

    def _build_ui(self):
        # Center the square container
        self.place(relx=0.5, rely=0.5, anchor="center")

    def _resize_container(self, event=None):
        # Keep square using smaller dimension
        size = min(
            self.parent.winfo_width(),
            self.parent.winfo_height()
        )

        # Apply padding
        size = int(size * self.padding_scale)

        self.config(width=size, height=size)
    
    # ─────────────────────────────────────────────
    # Add existing equipment ui
    # ─────────────────────────────────────────────

    def remove_equipment(self, equipment_ui):
        equipment_ui.destroy()
        for ui_list in [self.source_uis, self.target_uis, self.tip_uis]:
            if equipment_ui in ui_list:
                ui_list.remove(equipment_ui)

    def clear_plate(self):
        for e in self.source_uis + self.target_uis + self.tip_uis:
            e.destroy()
        
        self.source_uis.clear()
        self.target_uis.clear()
        self.tip_uis.clear()
    
    def add_equipment(self, equipment, command=None):

        if isinstance(equipment, Source):
            self.add_equipment_ui(SourceUI(self, equipment, command=command or self.edit_callback))
        elif isinstance(equipment, Target):
            self.add_equipment_ui(TargetUI(self, equipment, command=command or self.edit_callback))
        elif isinstance(equipment, TipRack):
            self.add_equipment_ui(TipHolderUI(self, equipment, command=command or self.edit_callback))


        return equipment

    def add_equipment_ui(self, equipment_ui):
        equipment_ui.place(in_=self)

        if isinstance(equipment_ui, SourceUI):
            self.source_uis.append(equipment_ui)
        elif isinstance(equipment_ui, TargetUI):
            self.target_uis.append(equipment_ui)
        elif isinstance(equipment_ui, TipHolderUI):
            self.tip_uis.append(equipment_ui)

        return equipment_ui
    
    def reset_volume(self):
        for s in self.source_uis:
            s.reset_volume()
    
    def show_assignment(self, assignment_ui:AssignmentUI):
        assignment = assignment_ui.curr_assignment
        assignments = assignment_ui.assignments
        if assignment.source:
            for s in self.source_uis:
                s.reset_colours()
                if s.equipment == assignment.source:
                    s.show_assignment(assignment)
        else:
            for s in self.source_uis:
                s.reset_colours()
        if assignment.target:
            for t in self.target_uis:
                t.reset_colours()
                if t.equipment == assignment.target:
                    t.show_assignment(assignment)
        else:
            for t in self.target_uis:
                t.reset_colours()
        for t in self.tip_uis:
            t.show_tip_taken()
        # for a in assignments:
        #     for t in self.tip_uis:
        #         if t.equipment == a.tip_holder:
        #             t.show_assignment(a)
    def get_equipment(self):
        ui_list = self.source_uis + self.target_uis + self.tip_uis
        equipment_list =  [ui.equipment for ui in ui_list]
        return equipment_list
    def get_tipholder(self):
        if self.tip_uis:

            return self.tip_uis[0].equipment
        else:
            return None
    
    def send_gcode(self):
        tipholder = self.tip_uis[0]
        if tipholder:
            tipholder.use_reserved_tips()

class AssignmentViewer(tk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        
        style = ttk.Style()
        style.theme_use("clam")

        # Tree body
        style.configure(
            "Treeview",
            background=CARD,
            foreground=TEXT,
            fieldbackground=CARD,
            borderwidth=0,
            rowheight=24,
            font=("Segoe UI", 9)
        )

        # Header
        style.configure(
            "Treeview.Heading",
            background=CARD,
            foreground=TEXT,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 9, "bold")
        )

        # Selection
        style.map(
            "Treeview",
            background=[
                ("selected", ACCENT)
            ],
            foreground=[
                ("selected", BG)
            ]
        )

        # Header hover
        style.map(
            "Treeview.Heading",
            background=[
                ("active", ACCENT_HOVER)
            ]
        )

        columns = (
            "volume",
            "source",
            "target"
            
        )

        self.assignment_tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings"
        )

        self.assignment_tree.heading(
            "source",
            text="Source"
        )
        self.assignment_tree.heading(
            "target",
            text="Target"
        )
        self.assignment_tree.heading(
            "volume",
            text="Volume (µL)"
        )

        self.assignment_tree.column(
            "source",
            width=150
        )
        self.assignment_tree.column(
            "target",
            width=150
        )
        self.assignment_tree.column(
            "volume",
            width=50,
            anchor="center"
        )

        scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.assignment_tree.yview
        )

        self.assignment_tree.configure(
            yscrollcommand=scrollbar.set
        )

        self.assignment_tree.pack(
            side="left",
            fill="both",
            expand=True
        )

        scrollbar.pack(
            side="right",
            fill="y"
        )
    
    def add_assignment(self, assignment):
        self.assignment_tree.insert(
                "",
                "end",
                values=(
                    assignment.volume,
                    f"{assignment.source.name}[{assignment.source.get_name(assignment.source_index)}]",
                    f"{assignment.target.name}[{', '.join(assignment.target.get_name(t) for t in assignment.target_index)}]",
                    
                )
            )

    
    def add_assignments(self, assignments):
        self.assignment_tree.delete(*self.assignment_tree.get_children())
        for assignment in assignments:
            self.add_assignment(assignment)



class GCodePanel(tk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=BG, **kwargs)
        self.user_configs = YAMLHelper.open_user()
        self.generate_func = None
        self.send_func = None
        self.send_update_ui = None
        self.gcode = None
        self.volume_adjust = True
        self.set_volume_adjust = None   
        self.assignment_ui = None

        # ── Title ──────────────────────────────────────────────
        title = tk.Label(
            self,
            text="Console",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold")
        )
        title.pack(anchor="w", padx=10, pady=(10, 6))


        self.content_frame = tk.Frame(self, bg=BG)
        self.content_notebook = ttk.Notebook(self.content_frame)
        
        self.generated_assignments_tab = AssignmentViewer(self.content_notebook)

        self.content_notebook.add(
            self.generated_assignments_tab,
            text="Generated Assignments"
        )

        
        
        self.content_notebook.pack(
            fill="both",
            expand=False,
            padx=10,
            pady=(0, 5)
        )


        # ── Console Output ──
        self.console = scrolledtext.ScrolledText(
            self.content_frame, bg=CARD, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 10), wrap="word"
        )
        # Pack this second so it fills the remaining space below
        self.console.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10)
        )
        # Read-only by default
        self.console.config(state="disabled")

        # ── Bottom Button Row ──────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.generate_btn = tk.Button(
            btn_row,
            text="Generate Gcode",
            bg=CARD,
            fg=TEXT,
            activebackground=ACCENT,
            relief="flat",
            command=self.generate_gcode
        )
        self.generate_btn.pack(side="right", padx=(6, 0))

        self.send_btn = tk.Button(
            btn_row,
            text="Send",
            bg=ACCENT,
            fg="black",
            relief="flat",
            command=self.send_gcode
        )
        self.send_btn.pack(side="right")

        self.clear_btn = tk.Button(
            btn_row,
            text="Clear console",
            bg=CARD,
            fg=TEXT,
            activebackground=ACCENT,
            relief="flat",
            command=self.clear_console
        )
        self.clear_btn.pack(side="right", padx=(6, 0))

        self.volume_btn = tk.Button(
            btn_row,
            text="Vol Adjust: ON",
            bg="#3a7a3a",
            fg=TEXT,
            activebackground=ACCENT,
            relief="flat",
            command=self.toggle_volume_adjust
        )
        self.volume_btn.pack(side="left")
        self.volume_adjust = not self.user_configs["volume-adjust"]
        self.toggle_volume_adjust()
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        

    # ── Public Methods ────────────────────────────────────────
    def clear_console(self):
        """Removes all text from the console output."""
        self.console.config(state="normal")      # Enable editing
        self.console.delete("1.0", tk.END)       # Delete from line 1, char 0 to the end
        self.console.config(state="disabled")

    def log(self, text):
        """Append text to console."""
        if not isinstance(text, str):
            text = str(text)
        self.console.config(state="normal")

        self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)

        self.console.config(state="disabled")

    def generate_gcode(self):
        if self.generate_func:
            assignments, self.gcode = self.generate_func(volume_adjust=self.volume_adjust)
            if self.gcode:
                self.log("Generated")
                for g in self.gcode:
                    self.log(g)
                self.generated_assignments_tab.add_assignments(assignments)

    def send_gcode(self):
        if self.send_func:
            self.clear_console()
            self.log("Sending G-code...")
            if self.send_update_ui:
                self.send_update_ui()
            self.send_func(self.gcode,log_callback=self.log)

    def toggle_volume_adjust(self):
        self.user_configs = YAMLHelper.open_user()
        self.volume_adjust = not self.volume_adjust
        self.user_configs["volume-adjust"] = self.volume_adjust
        YAMLHelper.write_yaml(self.user_configs, r"configs\\user.yaml")

        if self.volume_adjust:
            self.volume_btn.config(
                text="Vol Adjust: ON",
                bg="#3a7a3a"
            )
        else:
            self.volume_btn.config(
                text="Vol Adjust: OFF",
                bg="#7a3a3a"
            )
    



class AssignmentTab(tk.Frame):
    def __init__(self, master = None, example=False, printer_config=None, **kwargs):
        super().__init__(master, **kwargs)

        self.printer_config = printer_config or YAMLHelper.open_default_printer()
        # ── Left panel (1/3 width) ──────────────────────
        self.left_panel = tk.Frame(master, bg="#2b2b2b")
        self.left_panel.place(relx=0, rely=0, relwidth=0.2, relheight=1)
        self.esp_motor_controller = None

        # Initialize and tell it to fill the panel
        self.assignment = AssignmentUI(self.left_panel)
        self.assignment.pack(fill=tk.BOTH, expand=True) 

        
        # ── Right square container area (2/3 width) ─────
        self.middle_panel = tk.Frame(master, bg="#1e1e1e")
        self.middle_panel.place(relx=0.2, rely=0, relwidth=0.5, relheight=1)

        self.right_panel = tk.Frame(master, bg="#1e1e1e")
        self.right_panel.place(relx=0.7, rely=0, relwidth=.3, relheight=1)
        self.console = GCodePanel(self.right_panel)
        self.console.pack(fill="both", expand=True)
        # Keep the container square
        self.plate = PlateUI(master, self.middle_panel)
        self.plate.edit_callback = self.assignment._edit_assignment
        self.assignment.update_ui = self.plate.show_assignment
        self.assignment.get_tipholder = self.plate.get_tipholder
        self.console.send_update_ui = self.plate.send_gcode
        self.console.generate_func = (
            lambda volume_adjust: self.assignment.generate_gcode(printer_config=self.printer_config, 
            volume_adjust=volume_adjust, esp_motor_controller=self.esp_motor_controller, log_callback=self.console.log)
        )
        self.assignment.reset_volume = self.plate.reset_volume

        self.console.assignment_ui = self.assignment

        self.assignment.get_equipment = self.plate.get_equipment
        
        if example:
            tr = TipRack("tip-holder")
            s = Source("8-sample-holder")
            t = Target("96-wellplate")

            self.plate.add_equipment_ui(TipHolderUI(self.plate, tr, command=self.assignment._edit_assignment))
            self.plate.add_equipment_ui(TargetUI(self.plate, t, command=self.assignment._edit_assignment))
            self.plate.add_equipment_ui(SourceUI(self.plate, s, command=self.assignment._edit_assignment))
        
    def set_plate(self, equipment):
        diff_flag = False
        source_list = [s.equipment for s in self.plate.source_uis]
        target_list = [t.equipment for t in self.plate.target_uis]
        tip_list = [t.equipment for t in self.plate.tip_uis]
        for e in equipment:
            matched = False
            if isinstance(e, Source):
                for s in source_list:
                    if s.is_equal(e):
                        source_list.remove(s)
                        matched = True
                        break
            elif isinstance(e, Target):
                for t in target_list:
                    if t.is_equal(e):
                        target_list.remove(t)
                        matched = True
                        break
            elif isinstance(e, TipRack):
                for t in tip_list:
                    if t.is_equal(e):
                        tip_list.remove(t)
                        matched = True
                        break
            if matched == False:
                diff_flag = True
        if source_list or target_list or tip_list or diff_flag:
            print("resetting plate")
            self.plate.clear_plate()
            for e in equipment:
                self.plate.add_equipment(e)
            self.assignment.clear_assignments()

        
    def generate_gcode(self, printer_config):
        # print(self.assignment.generate_gcode(printer_config=printer_config))
        out = self.assignment.generate_gcode(printer_config=printer_config)
        self.plate.reset_volume()
        return out
    
    def camera_callback(self, camera):
        self.assignment.vlm_controller.camera = camera
    def printer_callback(self, printer):
        self.printer_config = printer
        self.assignment.printer = printer
        self.assignment.printer_callback(printer=printer)

    def on_tab_changed(self, event):
        # Check if the tab has been changed to this AssignmentTab
        if event.widget != self.master:
            return
        selected_tab = event.widget.select()
        if selected_tab != str(self):
            return
        flag = False
        if not flag:
            return





if __name__ == "__main__":


    root = tk.Tk()
    root.geometry("1000x700")

    GCodePanel(root)
    root.pack()
    # # ── Top bar ─────────────────────────────

    # printer_connector = PrinterConnector(root)
    # printer_connector.pack(
    #     fill=tk.X,
    #     padx=16,
    #     pady=(12, 8)
    # )


    # # ── Frame below connector ───────────────

    # content_frame = tk.Frame(root, bg="gray")
    # content_frame.pack(
    #     fill=tk.BOTH,
    #     expand=True
    # )


    # # ── Assignment tab inside content frame ─

    # assignment_tab = AssignmentTab(content_frame, example=True)

    # assignment_tab.place(
    #     x=0,
    #     y=0,
    #     relwidth=1,
    #     relheight=1
    # )


    root.mainloop()
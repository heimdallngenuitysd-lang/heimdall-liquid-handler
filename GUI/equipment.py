import math
import sys
from itertools import groupby
import yaml
from spatialmath import SE3
from pathlib import Path
from gcode_helper import GCodeHelper as g
from tkinter import messagebox, filedialog
import copy
import csv
import copy
import datetime
import ast
import shutil

from printer_controller import PrinterAction
import os

class Equipment:    
    """
    Represents a piece of laboratory equipment arranged as a regular grid.

    The equipment geometry (row/column spacing, dimensions, orientation)
    is loaded from an equipment YAML file, while the physical location of
    the equipment is loaded from an origin YAML file.

    Attributes:
        name (str):
            Logical name of the equipment.

        origin (SE3):
            World-frame position of the equipment origin.

        grid (list[list[SE3]]):
            2D array of positions for each grid location.

        rows (int):
            Number of rows in the equipment.

        cols (int):
            Number of columns in the equipment.

        dx (float):
            Column spacing in millimetres.

        dy (float):
            Row spacing in millimetres.

        orientation (str):
            Origin convention used by the equipment definition.
            One of: 'top-left', 'top-right', 'bottom-left',
            or 'bottom-right'.

        equipment_settings (dict):
            Raw equipment configuration loaded from YAML.

        origin_settings (dict):
            Raw origin configuration loaded from YAML.
    """


    def __init__(self, name: str, equipment_file: str = None, origin_file: str = None):
        self.name = name
        
        self.equipment_file = equipment_file
        self.origin_file = origin_file
        self.esp_motor_controller = None
        current_dir = Path(__file__).parent.resolve()

        if equipment_file is None:
            equipment_file = name
            # Load equipment
        equipment_yaml = YAMLHelper.open_equipment()[equipment_file]
        rows = equipment_yaml.get("rows", 1)
        cols = equipment_yaml.get("columns", 1)
        dx = equipment_yaml["x"]
        dy = equipment_yaml["y"]
        orientation = equipment_yaml.get("origin", "top-left")
        self.orientation = orientation
        if orientation == "top-right":
            dx = -dx
            dy = -dy
        elif orientation == "top-left":
            dy = -dy
        elif orientation == "bottom-right":
            dx = -dx
        self.dy = dy
        self.dx = dx
        self.rows = rows
        self.cols = cols
        self.equipment_settings = equipment_yaml
        if origin_file is None:
            origin_file = "default"
        origin_yaml = YAMLHelper.open_origin().get(origin_file, None)
        if origin_yaml is not None:

            self.origin = SE3(
                origin_yaml["x"],
                origin_yaml["y"],
                origin_yaml["z"]
            )
        else:
            self.origin = SE3(
                    0,
                    0,
                    0
                )

        self.grid = self.generate_grid(rows, cols, dx, dy, self.origin)
        self.origin_settings = origin_yaml
        return

    def set_origin(self, origin_file:str):
        origin_yaml = YAMLHelper.open_origin()[origin_file]

        self.origin = SE3(
            origin_yaml["x"],
            origin_yaml["y"],
            origin_yaml["z"]
        )

        self.grid = self.generate_grid(self.rows, self.cols, self.dx, self.dy, self.origin)
        self.origin_settings = origin_yaml

    def get_name(self, index):
        """
        Convert a (row, column) index into a 1-based well/location number.

        Args:
            index (tuple[int, int]):
                Grid index in the form (row, column).

        Returns:
            int: Location number.
        """
        return index[0] + 1 + (index[1] * self.cols)

    def get_coords_SE3(self, index: tuple):
        """
        Get the XYZ coordinates of a grid location in SE3.

        Args:
            index (tuple[int, int]):
                Grid index in the form (row, column).

        Returns:
            ndarray:
                Position vector [x, y, z].
        """
        return self.grid[index[0]][index[1]]
    
    def get_coords(self, index: tuple):
        """
        Get the XYZ coordinates of a grid location in SE3.

        Args:
            index (tuple[int, int]):
                Grid index in the form (row, column).

        Returns:
            ndarray:
                Position vector [x, y, z].
        """
        return self.grid[index[0]][index[1]].t
    
    def change_origin(self, origin):
        """
        Update the equipment origin and regenerate the grid.

        Args:
            origin (SE3 | list[float]):
                New origin position. May be supplied as an
                SE3 transform or [x, y, z] list.
        """
        if type(origin) == list:
            self.origin = SE3(origin[0], origin[1], origin[2])
        else:
            self.origin = origin
        self.grid = Equipment.generate_grid(self.rows, self.cols, self.dx, self.dy, self.origin)
        
    def change_equipment(self, equipment_name):
        equipment_yaml = YAMLHelper.open_equipment(equipment_name)

        dx = equipment_yaml["x"]
        dy = equipment_yaml["y"]

        orientation = equipment_yaml.get("origin", "top-left")
        self.orientation = orientation
        if orientation == "top-right":
            dx = -dx
            dy = -dy
        elif orientation == "top-left":
            dy = -dy
        elif orientation == "bottom-right":
            dx = -dx

        rows = equipment_yaml.get("rows", 1)
        cols = equipment_yaml.get("columns", 1)

        self.grid = self.generate_grid(rows, cols, dx, dy, self.origin)
        self.dy = dy
        self.dx = dx
        self.rows = rows
        self.cols = cols
        self.equipment_settings = equipment_yaml
    def save_origin(self, name=None):
        """Save origin"""
        if not name:
            name = self.name
        YAMLHelper.point_writer(name, self.origin)
        
    @staticmethod
    def generate_grid(rows: int, cols: int, spacing_x: float, spacing_y: float, origin=SE3(0, 0, 0)):
        """
        Generate a rectangular grid of SE3 positions.

        The grid is indexed as grid[column][row].

        Args:
            rows (int):
                Number of rows.

            cols (int):
                Number of columns.

            spacing_x (float):
                Column spacing in millimetres.

            spacing_y (float):
                Row spacing in millimetres.

            origin (SE3):
                Position of the first grid location.

        Returns:
            list[list[SE3]]:
                Generated grid of positions.
        """
        ox, oy, oz = origin.t
        points = []

        for c in range(cols):
            col = []
            for r in range(rows):
                x = ox + c * spacing_x
                y = oy + r * spacing_y
                col.append(SE3(x, y, oz))
            points.append(col)

        return points
    
    def is_equal(self, equipment):
        """Check if another equipment is the same as this one"""
        if (self.name == equipment.name and self.equipment_file == equipment.equipment_file 
            and self.origin_file == equipment.origin_file and self.origin == equipment.origin):
            return True
        else:
            return False
    
    def get_height(self):
        """Returns height needed to clear equipment to avoid collision"""
        return self.origin.t[2]
    
class TipRack(Equipment):
    """
    Represents a pipette tip rack used by the liquid handling system.

    A TipRack extends Equipment by tracking tip usage and providing
    helper methods for automated tip pickup and disposal. Rack geometry
    and pickup parameters are loaded from the equipment configuration.

    Attributes:
        z_drop (float):
            Distance to lower the pipette onto a tip during pickup.

        z_lift (float):
            Distance to raise the pipette after engaging a tip.

        used_index (list[tuple[int, int]]):
            List of rack positions that have already been used.

    Notes:
        The associated equipment definition must have a type containing
        "TipHolder", otherwise initialization will fail.
    """
    def __init__(self, name, equipment_file = None, origin_file = None):
        """
        Initialize a tip rack from YAML configuration files.

        Args:
            name (str):
                Name of the tip rack instance.

            equipment_file (str, optional):
                Name of the equipment definition to load from the
                equipment configuration file. If None, `name` is used.

            origin_file (str, optional):
                Name of the origin definition to load from the
                origin configuration file. If None, `name` is used.

        Raises:
            ValueError:
                If the loaded equipment definition is not of type
                "TipHolder".

        Notes:
            The equipment configuration must define:
                - type: containing "TipHolder"
                - z-drop: pickup insertion distance
                - z-lift: post-pickup lift distance

            The rack maintains an internal list of used tip positions,
            initialized as empty.
        """
        super().__init__(name, equipment_file, origin_file)
        if not "TipHolder" in self.equipment_settings.get("type"):
            raise ValueError(f"{name} is not a TipHolder equipment")
        self.z_drop = self.equipment_settings.get("z-drop")
        self.z_lift = self.equipment_settings.get("z-lift")
        self.used_index = []
        self.reserved_index = []
        self.current_index = [0,0]
        return
    
    def get_height(self):
        """ Get height needed to clear tip rack"""
        return self.origin.t[2] - self.z_drop + self.z_lift

    def check_index(self, index):
        """Check if a tip in the tip rack has been used"""
        if index in self.used_index:
            return True
        else:
            return False

    def add_index(self, index):
        """Add an index whose tip has been used"""
        if self.check_index(index):
            return False
        else:
            self.used_index.append(index)
            return True
        
    def remove_index(self,index):
        """Remove an index from list of used tips"""
        if self.check_index(index):
            self.used_index.remove(index)
            return True
        else:
            return False
    
    def add_reserved_index(self, index):
        """Add an index to the list of reserved tips"""
        if index in self.reserved_index:
            return False
        else:
            self.reserved_index.append(index)
            return True
    
    def use_reserved_index(self):
        self.used_index.extend(self.reserved_index)
        self.clear_reserved_index()
    
    def clear_reserved_index(self):
        self.reserved_index = []

    def next_tip(self):
        """Return next unused tip (Column-by-Column processing)"""
        unavailable_index = self.used_index + self.reserved_index
        unavailable_index.sort()
        for r in range(self.rows):
            for c in range(self.cols):
                current_coordinate = [c, r]
                if current_coordinate not in unavailable_index:
                    self.add_reserved_index(current_coordinate)
                    return current_coordinate
                    
        return None
        

    def get_tip(self, extruder=False, equipment_before=None):
        """Generates g code to get tip in index"""
        gcode = []
        index = self.next_tip()
        if index is None:
            messagebox.showerror("Out of tips!")
            return None
        # Move to tip position
        gcode.extend([
            g.move_absolute(self.grid[index[0]][index[1]]),
            g.move_relative([0,0, -self.z_drop], 8000),
            g.move_relative([0,0, self.z_lift]),
            g.move_absolute([self.grid[0][0].t[0],self.grid[0][0].t[1], (self.grid[0][0].t[2] + self.z_lift - self.z_drop)])
                           ])
        gcode = g.flatten(gcode)
        return gcode
    
    def remove_tip(self, printer_config, equipment_before=None):
        """
        Initialize a tip rack from YAML configuration files.

        Args:
            name (str):
                Name of the tip rack instance.

            equipment_file (str, optional):
                Name of the equipment definition to load from the
                equipment configuration file. If None, `name` is used.

            origin_file (str, optional):
                Name of the origin definition to load from the
                origin configuration file. If None, `name` is used.

        Raises:
            ValueError:
                If the loaded equipment definition is not of type
                "TipHolder".

        Notes:
            The equipment configuration must define:
                - type: containing "TipHolder"
                - z-drop: pickup insertion distance
                - z-lift: post-pickup lift distance

            The rack maintains an internal list of used tip positions,
            initialized as empty.
        """
        p_config = printer_config
        dispose_start = p_config.get("dispose_start", None)
        dispose_initial_y = p_config.get("dispose_initial_y", None)
        dispose_initial_z = p_config.get("dispose_initial_z", None)
        dispose_y = p_config.get("dispose_y", None)
        dispose_actuate_z = p_config.get("dispose_actuate_z", None)
        height = dispose_start[2]

        out = [g.wait(1)]
        start_position = dispose_start

        if equipment_before:
            if equipment_before.get_height() > self.get_height():
                out.extend(g.move_absolute([start_position[0], start_position[1], equipment_before.get_height()]))
            else:
                out.extend(g.move_absolute([None, None, start_position[2]]))

        out.extend(g.move_absolute(start_position)) 
        
        if None in [dispose_start, dispose_initial_y, dispose_initial_z, dispose_actuate_z, dispose_y]:
            raise ValueError("Printer configs incomplete for tip disposal")
        return g.flatten([
                out,
                g.move_relative([0, -dispose_initial_y,0]),
                g.move_relative([0,0,-dispose_initial_z]),
                g.move_relative([0, -dispose_y, 0]),
                g.move_relative([0,0, dispose_actuate_z]),
                g.move_relative([0,0, -dispose_actuate_z]),
                g.move_relative([0, dispose_y, 0]),
                g.move_relative([0,0,dispose_initial_z]),
                g.move_relative([0, dispose_initial_y,0]),
                g.move_absolute([self.grid[0][0].t[0], self.grid[0][0].t[1], dispose_start[2]], 4000),
                g.wait(500)])

class Source(Equipment):
    """
    Represents a rack of liquid source containers.

    The Source tracks the remaining volume and estimated liquid height
    of each container, allowing aspiration depth to be adjusted as
    liquid is consumed.
    """
    @staticmethod
    def generate_blank_csv(name, filepath=None):
        equipment_settings = YAMLHelper.open_equipment().get(name, None)
        if not equipment_settings:
            print("Invalid equipment name")
            return
        if not filepath:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                title=f"Save Blank CSV for {name}"
            )
            if not filepath:
                print("No filepath")
                return
        rows = equipment_settings["rows"]
        columns = equipment_settings["columns"]
        heading = [datetime.datetime.today(), name]
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(heading)
            for i in range(rows):
                header = [i]
                header.extend(list(range(columns)))
                writer.writerow(["Row", "Column"])
                writer.writerow(header)
                writer.writerow(["Volume"]+[equipment_settings["liquid-amount"] for i in range(columns)])
                writer.writerow(["Solvent"]+["" for i in range(columns)])
                writer.writerow(["Ingredient g/ml"]+["" for i in range(columns)])
                writer.writerow(["Ingredient g/ml"]+["" for i in range(columns)])
                writer.writerow([])
                writer.writerow([])

            writer.writerow(["END"])
    @staticmethod
    def load_csv(filepath=None):
        def safe_float(val):
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        if not filepath:
            filepath = filedialog.askopenfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                title=f"Load Source CSV"
            )
            if not filepath:
                print("No filepath")
                return
        with open(filepath, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            name = header[1]
            equipment_configs = YAMLHelper.open_equipment()
            if name not in equipment_configs.keys():
                return False, "Invalid equipment name"
            source = Source(name, name)
            next_row = []
            # Find the first row with data
            while not (len(next_row) >= 2 and next_row[0] == "Row" and next_row[1] == "Column"):
                next_row = next(reader)

            while not (next_row and next_row[0] == "END"):
                if (len(next_row) >= 2 and next_row[0] == "Row" and next_row[1] == "Column"):
                    indexes = next(reader)
                    indexes = [int(i) for i in indexes]
                    if ((len(indexes) < 2 or len(indexes) > source.cols + 1)
                        or (indexes[0] > source.rows - 1)):
                        print("Invalid number of columns")
                        return None
                    row = indexes.pop(0)
                elif not (next_row and next_row[0]):
                    next_row = next(reader)
                    continue
                else:
                    label = next_row.pop(0).lower().strip()
                    if len(next_row) < len(indexes):
                        next_row.extend([None for i in range(len(indexes) - len(next_row))])
                    if label in ["volume", "vol"]:
                        next_row = [safe_float(i) for i in next_row]
                        for i, item in enumerate(next_row):
                            status = source.bottles[indexes[i]][row].set_set_volume(item)
                            if not status:
                                source.bottles[indexes[i]][row].set_set_volume(None)
                    elif label in ["solvent", "sol"]:
                        for i, item in enumerate(next_row):
                            if not item:
                                item = None
                            source.bottles[indexes[i]][row].liquid["Solvent"] = item
                    else:
                        next_row = [safe_float(i) for i in next_row]
                        for i, item in enumerate(next_row):
                            source.bottles[indexes[i]][row].liquid[label] = item

                next_row = next(reader)
            return source
            
            

    class Bottle:
        """Represents a liquid container, used to track volume and height of liquid"""
        def __init__(self, height, volume, current_volume=None):
            self.height = height
            self.volume = volume
            self.set_volume = None # If volume was set in configuration
            self.current_volume = current_volume or self.volume
            self.liquid = {}


        @property
        def current_liquid_height(self):
            if self.current_volume < 0:
                return False
            return self.height - (self.height/self.volume*self.current_volume)
        
        def get_liquid(self, volume):
            self.current_volume -= volume
            # print(self.current_volume)
            
        def set_set_volume(self, volume):
            if not volume or volume > self.volume or volume < 0:
                return False
            self.set_volume = volume
            self.reset_volume()
            return True
            
        def reset_volume(self):
            self.current_volume = self.set_volume or self.volume
        
        def reset_set_volume(self):
            self.set_volume = self.volume
            self.reset_volume()

        def __eq__(self, value):
            return (isinstance(value, type(self)) and self.volume == value.volume and self.set_volume == value.set_volume
                and self.current_volume == value.current_volume)


    def __init__(self, name, equipment_file = None, origin_file = None):
        """
        Initialize a source container rack from YAML configuration files.

        A Source represents one or more liquid reservoirs arranged in a grid.
        Each reservoir is tracked by a Bottle object that maintains its
        remaining volume and estimated liquid height.

        Args:
            name (str):
                Name of the source instance.

            equipment_file (str, optional):
                Name of the equipment definition to load from the
                equipment configuration file. If None, `name` is used.

            origin_file (str, optional):
                Name of the origin definition to load from the
                origin configuration file. If None, `name` is used.

        Raises:
            ValueError:
                If the loaded equipment definition is not of type "Source".

        Notes:
            The equipment configuration must define:

                - type: containing "Source"
                - z-drop: aspiration depth offset from the liquid surface
                - liquid-amount: initial liquid volume per bottle
                - liquid-height: liquid height corresponding to a full bottle

            A Bottle instance is created for every grid position and is used
            to track remaining liquid volume and estimate the liquid level
            during aspiration.
        """
        super().__init__(name, equipment_file, origin_file)
        if not "Source" in self.equipment_settings.get("type"):
            raise ValueError(f"{name} is not a Source equipment")
        self.z_drop = self.equipment_settings.get("z-drop")
        self.volume = self.equipment_settings.get("liquid-amount")
        self.liquid_height = self.equipment_settings.get("liquid-height")
        self.bottles = []
        for x in range(self.cols):
            column_list = []
            for y in range(self.rows):
                bottle_instance = self.Bottle(
                    height=self.liquid_height,
                    volume=self.volume,
                )
                column_list.append(bottle_instance)
            self.bottles.append(column_list)
    
    def reset_volume(self):
        """Reset volume in all bottles to full"""
        for row in self.bottles:
            for bottle in row:
                bottle.reset_volume()
    
    def reset_set_volume(self):
        """Reset volume in all bottles to full"""
        for row in self.bottles:
            for bottle in row:
                bottle.reset_set_volume()
    
    def set_volume(self, index, volume):
        self.bottles[index[0]][index[1]].set_volume = volume
        self.bottles[index[0]][index[1]].reset_volume()
    
    def get_sample(self, index, wait_before, wait_after, dispense_wait,
                   extruder=False, esp_motor_controller=None,
                   log_callback=None, equipment_before=None, volume=100,
                   prewet=False, shake=False, reverse=False):
        """
        Generate G-code to aspirate liquid from a source container.

        The pipette is moved to the specified source position, lowered to
        the estimated liquid level, and an aspiration action is performed.
        If volume tracking is enabled, the remaining liquid volume for the
        selected bottle is updated accordingly.

        Args:
            index (tuple[int, int]):
                Source location in the form (column, row).

            wait_before (int):
                Time in milliseconds to wait before aspirating after
                reaching the aspiration position.

            wait_after (int):
                Time in milliseconds to wait after aspirating before
                retracting from the liquid.

            extruder (bool, optional):
                Whether to generate extruder-based pipette commands instead
                of using an ESP motor controller.

            esp_motor_controller (ESPMotorController, optional):
                Controller used to perform pipette priming and aspiration.
                If provided, controller commands are used instead of
                extruder G-code commands.

            log_callback (callable, optional):
                Callback function used to receive status messages from the
                motor controller.

            equipment_before (Equipment, optional):
                Previously visited equipment. If provided, safe travel moves
                are generated to avoid collisions when moving to the source.

            volume (float, optional):
                Volume to subtract from the source bottle after aspiration.
                Set to None or 0 to disable volume tracking.

        Returns:
            list:
                Flattened list of G-code commands required to perform the
                aspiration operation.

        Notes:
            The aspiration depth is adjusted based on the estimated liquid
            height of the selected bottle. If the tracked volume becomes
            invalid, a warning is displayed and the full liquid height is
            used as a fallback.
        """
        out = [g.wait(1)]
        start_position = self.grid[index[0]][index[1]].t

        # Avoid colliding into itself or equipment before it

        if equipment_before:
            if equipment_before.get_height() > self.get_height():
                out.extend(g.move_absolute([start_position[0], start_position[1], None]))
            else:
                out.extend(g.move_absolute([None, None, start_position[2]]))

        out.extend(g.move_absolute(start_position))
        if volume:
            self.bottles[index[0]][index[1]].get_liquid(volume)
        liquid_height = self.bottles[index[0]][index[1]].current_liquid_height
        if liquid_height is False:
            messagebox.showwarning("Warning!", f"{self.name} {index} might be empty!")
            liquid_height = self.liquid_height
        z_drop = self.z_drop + liquid_height

        if prewet and not reverse:
            out.extend(self.prewet(z_drop, wait_before, wait_after, dispense_wait, extruder=extruder, esp_motor_controller=esp_motor_controller, shake=shake)),
            out.extend(self.prewet(z_drop, wait_before, wait_after, dispense_wait, extruder=extruder, esp_motor_controller=esp_motor_controller, shake=shake))

        # Move to sample position
        if esp_motor_controller:
            if reverse:
                return g.flatten([
                out,
                esp_motor_controller.full_depress(log_callback=log_callback),
                g.wait(wait_before),
                g.move_relative([0,0, -z_drop]),
                esp_motor_controller.full_aspiration(log_callback=log_callback),
                g.wait(wait_after),
                g.move_relative([0,0, z_drop])
                            ])
            else:
                return g.flatten([
                out,
                esp_motor_controller.prime(log_callback=log_callback),
                g.wait(wait_before),
                g.move_relative([0,0, -z_drop]),
                esp_motor_controller.aspirate(log_callback=log_callback),
                g.wait(wait_after),
                g.move_relative([0,0, z_drop])
                            ])
        else:
            return g.flatten([
            out,
            g.trigger_pipette(extruder=extruder),
            g.wait(wait_before),
            g.move_relative([0,0, -z_drop]),
            g.trigger_pipette(extruder=extruder),
            g.wait(wait_after),
            g.move_relative([0,0, z_drop])
                           ])
    
    def prewet(self, z_drop, wait_before, wait_after, dispense_wait, extruder=False, esp_motor_controller=None, log_callback=None, shake=False):

        if esp_motor_controller:
            return g.flatten([
            esp_motor_controller.prime(log_callback=log_callback),
            g.wait(wait_before),
            g.move_relative([0,0, -z_drop]),
            esp_motor_controller.aspirate(log_callback=log_callback),
            g.wait(wait_after),
            g.move_relative([0,0, z_drop]),
            esp_motor_controller.dispense(log_callback=log_callback, shake=shake),
            g.wait(dispense_wait)
                           ])
        else:
            return g.flatten([
            g.trigger_pipette(extruder=extruder),
            g.move_relative([0,0, -z_drop]),
            g.trigger_pipette(extruder=extruder),
            g.move_relative([0,0, z_drop]),
            g.trigger_pipette(extruder=extruder),
            g.wait(wait_after)
                           ])

    def is_equal(self, equipment):
        if super().is_equal(equipment):
            diff_flag = False
            for c in range(len(self.bottles)):
                for r in range(len(self.bottles[c])):
                    if not diff_flag:
                        if self.bottles[c][r] != equipment.bottles[c][r]:
                            diff_flag = True
            return not diff_flag
        else:
            return False

    def load_config(self, filepath=None):
        source = Source.load_csv(filepath=filepath)
        if not source:
            return False, "Nothing loaded!"
        if source.equipment_settings["name"] != self.equipment_settings["name"]:
            return False, "Incompatible Equipment Type"
        for row in range(self.rows):
            for col in range(self.cols):
                self.bottles[col][row].liquid = source.bottles[col][row].liquid
                self.bottles[col][row].set_set_volume(source.bottles[col][row].set_volume)

    def save_config(self, filepath=None):
        if not filepath:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                title=f"Save CSV for {self.name}"
            )
            if not filepath:
                return False, "No filepath provided"
        rows = self.equipment_settings["rows"]
        columns = self.equipment_settings["columns"]
        heading = [datetime.datetime.today(), self.name]
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(heading)
            for i in range(rows):
                row_bottles = [self.bottles[c][i] for c in range(self.cols)]
                
                header = [i]
                header.extend(list(range(columns)))
                writer.writerow(["Row", "Column"])
                writer.writerow(header)
                # Write volume row
                volume_list = [bottle.set_volume for bottle in row_bottles]
                writer.writerow(["Volume"]+volume_list)

                # Liquid
                keyword_set = set()
                for bottle in row_bottles:
                    keyword_set.update(bottle.liquid.keys())
                for keyword in keyword_set:
                    writer.writerow([keyword]+[bottle.liquid.get(keyword, None) for bottle in row_bottles])
                writer.writerow([])

            writer.writerow(["END"])

    
    
class Target(Equipment):
    """
    Represents a destination plate or container rack for dispensing.

    A Target extends Equipment by providing helper methods for moving
    to a destination location and dispensing liquid. Typical targets
    include well plates, tube racks, and other receptacles used in
    liquid handling workflows.

    Attributes:
        z_drop (float):
            Optional dispensing depth loaded from the equipment
            configuration.

    Notes:
        Target locations are identified using alphanumeric labels
        (e.g. A1, B3, H12) via get_name().
    """
    def __init__(self, name, equipment_file = None, origin_file = None):
        """
        Initialize a target rack from YAML configuration files.

        Args:
            name (str):
                Name of the target instance.

            equipment_file (str, optional):
                Name of the equipment definition to load from the
                equipment configuration file. If None, `name` is used.

            origin_file (str, optional):
                Name of the origin definition to load from the
                origin configuration file. If None, `name` is used.

        Raises:
            ValueError:
                If the loaded equipment definition is not a valid target
                configuration.

        Notes:
            The equipment configuration should define a z-drop value if
            dispensing below the rack origin is required.
        """
        super().__init__(name, equipment_file, origin_file)
        if not "Target" in self.equipment_settings.get("type"):
            raise ValueError(f"{name} is not a Target equipment")
        self.z_drop = self.equipment_settings.get("z-drop")
    
    def get_name(self, index):
        label = "ABCDEFGHI"
        return f"{label[index[0]]}{index[1]}"
    
    def to_target(self, index, wait, extruder=False,
                   esp_motor_controller=None, log_callback=None, equipment_before=None,
                   shake=False, reverse=False, dip=False):
        """
        Generate G-code to move to a target location and dispense liquid.

        The pipette is moved to the specified target position and a
        dispensing action is performed using either an ESP motor controller
        or extruder-based G-code commands.

        Args:
            index (tuple[int, int]):
                Target location in the form (column, row).

            wait (int):
                Time in milliseconds to wait after dispensing.

            extruder (bool, optional):
                Whether to generate extruder-based dispense commands.

            esp_motor_controller (ESPMotorController, optional):
                Controller used to perform dispensing. If provided,
                controller commands are used instead of extruder G-code.

            log_callback (callable, optional):
                Callback function used to receive status messages from the
                motor controller.

            equipment_before (Equipment, optional):
                Previously visited equipment. If provided, safe travel moves
                are generated to avoid collisions when moving to the target.

        Returns:
            list:
                Flattened list of G-code commands required to move to the
                target and dispense liquid.
        """
        out = [g.wait(1)]
        start_position = self.grid[index[0]][index[1]].t

        if equipment_before:
            if equipment_before.get_height() > self.get_height():
                out.extend(g.move_absolute([start_position[0], start_position[1], None]))
            else:
                out.extend(g.move_absolute([None, None, start_position[2]]))

        out.extend(g.move_absolute(start_position))
        out.extend(g.move_relative([0,0, -self.z_drop], 4000))
        liquid_height = self.equipment_settings.get("liquid-height", 0)
        # Move to sample position
        if esp_motor_controller:
            if reverse:
                out.extend([esp_motor_controller.prime(log_callback=log_callback)])

            else:
                out.extend([esp_motor_controller.full_depress(log_callback=log_callback)])
            
           
            
            if shake:
                out.extend(g.shake())
            else:
                out.extend([g.wait(1000)])

            if dip:
                out.extend([g.move_relative([0,0,-liquid_height]),
                            g.move_relative([0,0,liquid_height])])
            out.extend([g.move_relative([0,0, self.z_drop], 4000)])
            if reverse:
                out.extend([esp_motor_controller.aspirate(log_callback=log_callback)])
            else:
                out.extend([esp_motor_controller.full_aspiration(log_callback=log_callback)])

            
            return g.flatten(out)                   
        else:
            return g.flatten([
            out,
            g.finish_move(),
            g.trigger_pipette(extruder=extruder),
            g.wait(wait),
            g.move_relative([0,0, self.z_drop], 4000)
                           ])
        

class Assignment:
    """
    Represents a liquid handling task that transfers a specified volume
    from a source location to one or more target locations using a
    designated pipette tip.

    An Assignment contains all information required to execute a
    transfer, including the source well, destination wells, tip
    location, transfer volume, and pipette volume controller settings.
    It can generate the corresponding G-code sequence required to
    perform the operation on the liquid handling platform.

    Attributes:
        name (str):
            Human-readable name of the assignment.

        tip_holder (TipRack):
            Tip rack containing the tip to be used.

        tip_index (tuple[int, int]):
            Position of the tip within the tip rack.

        source (Source):
            Source container or plate from which liquid is aspirated.

        source_index (tuple[int, int]):
            Position of the source well or container.

        target (Target):
            Destination container or plate.

        target_index (list[tuple[int, int]]):
            One or more destination locations for dispensing.

        volume (float):
            Transfer volume in microlitres.

        volume_controller:
            Controller responsible for adjusting the pipette volume.

        colour (str):
            Display colour used by the GUI to identify the assignment.

    Notes:
        A single Assignment may dispense to multiple target locations.
        In this case, liquid is re-aspirated from the source before
        each dispense operation while reusing the same pipette tip.

        Assignments are considered valid only when all required source,
        target, tip, and volume information has been specified.
    """
    colours = [
        "#9ece6a",  # Green
        "#7aa2f7",  # Blue
        "#bb9af7",  # Purple
        "#f7768e",  # Red
        "#e0af68",  # Yellow/Orange
        "#73daca",  # Cyan
        "#ff9e64",  # Orange
        "#2ac3de",  # Light Blue
        ]
    def __init__(self, name=None, tip_holder=None, 
                tip_index=None,source=None, source_index=None,
                target=None, target_index=None, volume=None, volume_controller=None, colour=colours[0] ):
        """
        Parameters:
            name: str
            tip_holder: container for tips
            tip_index: int
            source: source container (e.g. sample well plate)
            source_index: int or identifier
            target: target container (e.g. 96-well plate)
            target_index: list of (x, y) tuples
                e.g. [(x, y), (x, y), ...]
        """
        self.name = name
        self.tip_holder = tip_holder
        self.tip_index = tip_index
        self.source = source
        self.source_index = source_index
        self.target = target
        self.target_index = target_index
        self.volume = volume or 500
        self.volume_controller = volume_controller
        self.colour=colour
        self.speed = 3000
        self.acceleration = 1000
        self.hold_time = 5
        self.heat_duration = 600
        self.dip = False
        self.shake = False
        self.reverse = False
        self.change_tip = False
        self.prewet = False
        self.capture = False

    def __str__(self):
        source_name = " " if self.source is None else "".join([word[0] for word in self.source.name.split('-') if word])
        source_index = " " if self.source_index is None else self.source.get_name(self.source_index)
        target_index = " " if self.target_index is None else (', '.join(self.target.get_name(t) for t in self.target_index))
        return f"{self.name}: {self.volume}µL, {source_name}{source_index}, {target_index}"
    # Validation
    def is_valid(self):
        """Checks if assignment has a tip, source and target"""
        return all([
            self.name is not None,
            self.tip_holder is not None,
            self.source is not None,
            self.source_index is not None,
            self.target is not None,
            self.target_index is not None,
            self.volume is not None and (self.volume >= 100 or self.volume <=1000)
        ])
        
    def remove(self):
        """Used if tip is reassigned, remove tip from used list in TipRack"""
        if self.tip_holder:
            self.tip_holder.remove_index(self.tip_index)


    def generate_gcode(self, printer, volume_adjust=True, esp_motor_controller=None, log_callback=None, get_tip=True, remove_tip=True, dobot=None):
        """
        Generate the command sequence required to execute this assignment.

        The generated sequence performs the following operations:

            1. Adjust the pipette volume (optional).
            2. Pick up the assigned tip.
            3. Aspirate liquid from the source location.
            4. Dispense liquid into one or more target locations.
            5. Dispose of the used tip.

        If multiple target locations are specified, the same tip is reused
        and liquid is re-aspirated from the source before each subsequent
        dispense.

        Args:
            printer (dict):
                Printer configuration containing movement, timing, volume
                adjustment, and tip disposal parameters.

            volume_adjust (bool, optional):
                If True, adjust the pipette to the assignment volume before
                execution.

            esp_motor_controller (ESPMotorController, optional):
                Controller used for pipette aspiration and dispensing. If
                omitted, extruder-based G-code commands are generated.

            log_callback (callable, optional):
                Callback function used to receive status updates from the
                motor controller.

        Returns:
            list:
                List of G-code commands and printer actions required to
                perform the assignment.

        Raises:
            ValueError:
                If the assignment is incomplete or invalid.
        """
        if not self.is_valid:
            raise ValueError("invalid assignment")
        extruder = printer.get("extruder")
        prime_dwell_before = printer.get("prime_dwell_time_before")
        prime_dwell_after = printer.get("prime_dwell_time_after")
        dispense_dwell_time = printer.get("dispense_dwell_time")
        tip_dispose_z = printer.get("dispose_start")[2]
        start_position = printer.get("vol_adjust_position")


        out = []


        out.extend(g.move_absolute(start_position))
            
        if self.volume and volume_adjust:
            # Move decimal points for volume adjuster
            vol_no_dec = int(self.volume * 10**int(printer["decimal_position"]))
            pipette_interval = int(printer.get("pipette-interval", 1))
            out.extend([PrinterAction(lambda printer_controller, log_callback:self.volume_controller.adjust(vol_no_dec, printer_controller,log_callback, interval=pipette_interval), name=f"Adjust pipette to {vol_no_dec}")])
        
        prewet_int = False
        if get_tip:
            out.extend(self.tip_holder.get_tip())
            if self.prewet:
                prewet_int = True

        
        if not self.volume:
            
            out.extend(self.source.get_sample(self.source_index, prime_dwell_before, prime_dwell_after, dispense_dwell_time, extruder, esp_motor_controller, log_callback, equipment_before=self.tip_holder, prewet=prewet_int, shake=self.shake, reverse=self.reverse))
        else:
            volume = self.volume
            if self.reverse:
                volume = self.volume + printer["max_vol"]*.2
            out.extend(self.source.get_sample(self.source_index, prime_dwell_before, prime_dwell_after, dispense_dwell_time, extruder, esp_motor_controller, log_callback, equipment_before=self.tip_holder, volume=volume, prewet=prewet_int, shake=self.shake, reverse=self.reverse))

        out.extend(self.target.to_target(self.target_index[0], dispense_dwell_time, extruder, esp_motor_controller, log_callback, equipment_before=self.source, shake=self.shake, dip=self.dip, reverse=self.reverse))

        if len(self.target_index) == 1:
            if not self.remove or remove_tip: 
                out.extend(self.tip_holder.remove_tip(printer, equipment_before=self.target))  
            return out
        
        if self.change_tip:
            out.extend(self.tip_holder.remove_tip(printer, equipment_before=self.target))
            
        get_tip = self.change_tip
        prewet_int = False
        for target in self.target_index[1:]:
            equipment_before = self.target
            if get_tip:
                out.extend(self.tip_holder.get_tip())
                equipment_before = self.tip_holder
                prewet_int = True
            volume = self.volume
            if self.reverse:
                volume = self.volume + printer["max_vol"]*.2
            out.extend(self.source.get_sample(self.source_index, prime_dwell_before, prime_dwell_after, dispense_dwell_time, extruder, esp_motor_controller, log_callback, equipment_before=equipment_before, volume=volume, prewet=prewet_int, shake=self.shake, reverse=self.reverse))
            out.extend(self.target.to_target(target, dispense_dwell_time, extruder, esp_motor_controller, log_callback, equipment_before=self.source, shake=self.shake, dip=self.dip, reverse=self.reverse))
            if self.change_tip:
                out.extend(self.tip_holder.remove_tip(printer, equipment_before=self.target))
            
        if not self.change_tip and remove_tip:
            out.extend(self.tip_holder.remove_tip(printer, equipment_before=self.target))
        return out
    

    def edit_assignment(self, name=None, tip_holder=None, tip_index=None, 
                        source=None, source_index=None, target=None, target_index=None, 
                        colour=None, volume=None, speed=None, acceleration=None, heat_duration=None,
                        hold_time=None, shake=None, dip=None, reverse=None, change_tip=None, prewet=None, capture=None, *args, **kwargs):
        """
        Modify assignment parameters after creation.

        Depending on the argument provided, this method updates assignment
        properties such as source, target, tip, transfer volume, or display
        colour.

        Target locations are treated as a toggle: selecting an existing
        target removes it, while selecting a new target adds it.

        Args:
            name (str, optional):
                New assignment name.

            tip_holder (TipRack, optional):
                Tip rack associated with the assignment.

            tip_index (tuple[int, int], optional):
                Position of the assigned tip.

            source (Source, optional):
                Source container or plate.

            source_index (tuple[int, int], optional):
                Position of the source well or container.

            target (Target, optional):
                Destination container or plate.

            target_index (tuple[int, int] | list[tuple[int, int]], optional):
                Target location(s) to add or remove.

            colour (str, optional):
                Display colour for the assignment.

            volume (float, optional):
                Transfer volume in microlitres.

        Returns:
            str:
                Current assignment colour.

            tuple:
                For tip or source updates, returns
                (current_colour, previous_index).

            bool:
                For target updates, indicates whether a target was added
                or removed.

        Notes:
            Only one field should typically be modified per call, as the
            method returns immediately after handling tip, source, or target
            index updates.
        """
        
        def update_list(item, list):
            if item in list:
                list.pop(list.index(item))
                if not list:
                    list = None
                return False
            else:
                list.append(item)
                return self.colour

        if name is not None:
            self.name = name

        if volume is not None and volume >= 0:
            self.volume = volume

        if tip_holder is not None:
            self.tip_holder = tip_holder

        if tip_index is not None:
            old = None
            if self.tip_index is not None and self.tip_index != tip_index:
                old = self.tip_index
            self.tip_index = tip_index
            return self.colour, old

        if source is not None:
            self.source = source

        if source_index is not None:
            old = None
            if self.source_index is not None and self.source_index != source_index:
                old = self.source_index
            self.source_index = source_index
            return self.colour, old

        if target is not None:
            self.target = target

        if target_index is not None:
            if not self.target_index:
                self.target_index = []
            if isinstance(target_index[0], list):
                for t in target_index:
                    out = update_list(t, self.target_index)
                return out
            else:
                return update_list(target_index, self.target_index)
        if speed:
            self.speed = speed
        if acceleration:
            self.acceleration = acceleration
        if hold_time:
            self.hold_time = hold_time

        if heat_duration:
            self.heat_duration = heat_duration
            
        if colour:
            self.colour = colour
        if dip is not None:
            self.dip = dip
            return self.dip
        if shake is not None:
            self.shake = shake
            return shake
        if reverse is not None:
            self.reverse = reverse
            return self.reverse
        if prewet is not None:
            self.prewet = prewet
            return self.prewet
        if change_tip is not None:
            self.change_tip = change_tip
            return self.change_tip
        if capture is not None:
            self.capture = capture
            return self.capture
        return self.colour
    
       
    
    def get_target_index(self):
        return self.target_index
    
    def get_tip_holder(self):
        return self.tip_holder

    def get_tip_index(self):
        return self.tip_index

    def get_source(self):
        return self.source

    def get_source_index(self):
        return self.source_index

    def get_target(self):
        return self.target

    def get_target_index(self):
        return self.target_index
    
    def _init_csv_log(path):
        """Initialize CSV file with headers if it doesn't exist."""


        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
            "Batch_ID", "Position", "Date", "Time",
            "Assignment_Name", "Source", "Source_Index", "Target", "Target_Indices",
            "Tip_Holder", "Tip_Index",
            "Volume_uL", "Shake", "Reverse", "Dip","Change_tip"
        ])


    def save_assignments_to_csv(assignments, filepath):
        """Log assignments to CSV when sent to printer."""
        assignments = copy.deepcopy(assignments)
        if not assignments:
            print("No assignments to log")
            return False
        
        # Filter valid assignments
        valid_assignments = [a for a in assignments if a.is_valid()] # list of valid assignments
        
        if not valid_assignments:
            print("No valid assignments to log")
            return False
        
        # Generate batch information (one timestamp per batch)
        now = datetime.datetime.now()
        batch_id = now.strftime("%Y%m%d_%H%M%S")
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        Assignment._init_csv_log(filepath)
        current_dir = Path(__file__).parent.resolve()
        current_dir = current_dir / filepath
        
        try:
            with open(current_dir, 'a', newline='') as f:
                writer = csv.writer(f)
                
                for index, assignment in enumerate(valid_assignments, 1):
                    # Extract source indices they have [c,r] format
                    

                    # Format target indices as string
                    target_indices = str(assignment.target_index) 
                    
                    writer.writerow([
                        batch_id,
                        index,
                        date,
                        time,
                        assignment.name,
                        assignment.source.name,
                        assignment.source_index,
                        assignment.target.name,
                        target_indices,
                        assignment.tip_holder.name,
                        assignment.tip_index,
                        assignment.volume,
                        assignment.shake,
                        assignment.reverse,
                        assignment.dip,
                        assignment.change_tip,
                    ])
            
            return True
            
        except PermissionError:
            print("Permission denied: Cannot write to log file. Is it open in Excel?")
            return False
        except FileNotFoundError:
            print(f"Directory not found: {os.path.dirname(filepath) or 'current directory'}")
            return False
        except OSError as e:
            print(f"OS Error writing to log file: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error logging assignments: {e}")
            return False
    

    def _apply_loaded_assignment(self, data):
        """Populate self.curr_assignment from one parsed CSV row, mirroring UI clicks."""
        for key, value in data.items():
            self.edit_assignment(**{key: value})


    def _parse_pair(raw):
            """'[c, r]' -> [c, r]"""
            val = (raw or "").strip()
            return list(ast.literal_eval(val)) if val and val != "None" else None

    def sort_assignments_by_volume(assignments):
        # Sort assignments by volume
        return sorted(assignments, key=lambda x: x.volume)

    def sort_assignments_by_source(assignments):
        return sorted(
            assignments,
            key=lambda x: (x.source.name, x.source_index)
        )

    def handle_assignments(assignments, printer_config):
        processed = []
        # assignments = Assignment.sort_assignments_by_volume(assignments, printer_config)
        for assignment in assignments:
            if assignment.volume > printer_config["max_vol"]:
                processed.extend(
                    Assignment.split_assignment(
                        assignment,
                        printer_config
                    )
                )
            else:
                processed.append(assignment)

        return processed
            

    def load_assignments_from_csv(equipment):
        """Load assignments from a CSV previously written by log_sent_assignments()."""
        
        file_path = filedialog.askopenfilename(
            title="Load Assignments from CSV",
            initialdir=Path(__file__).parent.resolve(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not file_path:
            return # for exiting loading file

        # name -> equipment, by type (SpinCoater is a Target subclass)
        sources = {e.name: e for e in equipment if isinstance(e, Source)}
        tips    = {e.name: e for e in equipment if isinstance(e, TipRack)}
        targets = {e.name: e for e in equipment if isinstance(e, Target)}

        parsed, errors = [], []
        try:
            with open(file_path, newline='') as f:
                for line_no, row in enumerate(csv.DictReader(f), start=2):  # row 1 = header
                    try:
                        name       = row["Assignment_Name"].strip()
                        source     = sources.get(row["Source"].strip())
                        target     = targets.get(row["Target"].strip())
                        tip_holder = tips.get(row["Tip_Holder"].strip())

                        missing = [label for label, obj in
                                (("source", source), ("target", target), ("tip holder", tip_holder))
                                if obj is None]
                        if missing:
                            errors.append(f"Row {line_no} ({name}): {', '.join(missing)} not on plate")
                            continue

                        source_index = Assignment._parse_pair(row["Source_Index"])

                        raw_targets   = (row.get("Target_Indices") or "").strip()
                        target_index  = ast.literal_eval(raw_targets) if raw_targets and raw_targets != "None" else []
                        target_index  = [list(p) for p in target_index]

                        volume = float(row["Volume_uL"])

                        def _int_or_none(key):
                            v = (row.get(key) or "").strip()
                            return int(float(v)) if v else None

                        # --- FIXED: Use clean helper functions to safely default to False if keys don't exist ---
                        def _bool_or_false(key):
                            val = row.get(key)
                            return val.strip() == "True" if val is not None else False

                        parsed.append({
                            "name": name,
                            "source": source, "source_index": source_index,
                            "tip_holder": tip_holder,
                            "target": target, "target_index": target_index,
                            "volume": volume,
                            "shake":   _bool_or_false("Shake"),
                            "reverse": _bool_or_false("Reverse"),
                            "dip":     _bool_or_false("Dip"),
                            "change_tip": _bool_or_false("Change_tip"),
                        })
                    except (KeyError, ValueError, SyntaxError) as e:
                        errors.append(f"Row {line_no}: {e}")
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not read the CSV:\n{e}")
            return None

        if not parsed:
            messagebox.showerror("Nothing loaded", "\n".join(errors) or "No valid rows in file.")
            return None
        
        output = []
        # Replace current assignments; clear_assignments() leaves one empty assignment we reuse for row 0
        for i, data in enumerate(parsed):
            assignment = Assignment()
            assignment._apply_loaded_assignment(data)
            output.append(assignment)
    
        output = Assignment.sort_assignments_by_volume(output)

        msg = f"Loaded {len(parsed)} assignment(s)."
        if errors:
            msg += "\n\nSkipped rows:\n" + "\n".join(errors)
        
        # --- FIXED: Corrected your broken 'm sessagebox' typo ---
        messagebox.showinfo("Load complete", msg)
        return output


    def split_assignment(assignment, printer_config):
        max_vol = printer_config["max_vol"]

        if assignment.volume <= max_vol:
            return [assignment]

        assignment_volumes = Assignment.split_assignment_volumes(assignment.volume, printer_config)

        assignment_volumes_same = [list(group) for key, group in groupby(assignment_volumes)]

        split_assignments = []        
        for i in assignment_volumes_same:
            new_assignment = copy.deepcopy(assignment)

            old_targets = new_assignment.target_index
            new_assignment.volume = i[0]
            new_assignment.target_index = [item for item in old_targets for _ in range(len(i))]

            new_assignment.source = assignment.source
            new_assignment.target = assignment.target
            new_assignment.tip_holder = assignment.tip_holder
            new_assignment.volume_controller = assignment.volume_controller

            split_assignments.append(new_assignment)

        return split_assignments
    
    def split_assignment_volumes(volume, printer_config):
        max_vol = printer_config["max_vol"]
        # Get configuration constraints (with defaults if missing)
        interval = printer_config.get("pipette-interval", 1.0)
        decimal_position = printer_config.get("decimal_position", 0)
        if volume <= max_vol:
            return [volume]

        # Calculate how many parts are required
        n_parts = math.ceil(volume / max_vol)

        vol_int = volume * (10 ** decimal_position)

        # 1. Convert total volume into absolute physical "steps" or intervals
        total_intervals = round(vol_int / interval)
        
        # 2. Divide intervals as evenly as possible using integer math
        base_intervals = total_intervals // n_parts
        remainder_intervals = total_intervals % n_parts

        volumes = []
        for i in range(n_parts):
            # Distribute the remainder intervals one by one
            allocated_intervals = base_intervals + (1 if i < remainder_intervals else 0)
            
            # 3. Convert back to raw volume
            raw_vol = allocated_intervals * interval
            
            # 4. Enforce strict decimal position rounding
            final_vol = raw_vol / (10 ** decimal_position)
            volumes.append(final_vol)

        return volumes

    def sort_assignments_by_volume(assignments, printer_config=None):
        # Sort assignments by volume
        if printer_config is None:
            return sorted(assignments, key=lambda x: x.volume)
        else:
            max_vol = printer_config["max_vol"]
            def sort_key(assignment):
                if assignment.volume <= max_vol:
                    return assignment.volume
                else:
                    n_parts = math.ceil(assignment.volume/max_vol)
                    return round(assignment.volume//n_parts)
            
            return sorted(assignments, key=sort_key)

    def sort_assignments_by_source(assignments):
        return sorted(
            assignments,
            key=lambda x: (x.source.name, x.source_index)
        )

    
            

class Plate:
    def __init__(self, equipment:list):
        self.printer_config = y.open_default_printer()
        self.assignments = [Assignment("Assignment 1")]
        self.source = []
        self.tip_rack = []
        self.target = []
        self.add_equipment(equipment)

    def add_equipment(self, equipment:list):
        def add_one(equipment):
            if isinstance(equipment, Source):
                    self.source.append(equipment)

            elif isinstance(equipment, TipRack):
                self.tip_rack.append(equipment)

            elif isinstance(equipment, Target):
                self.target.append(equipment)


        if isinstance(equipment, Equipment):
            for e in equipment:
                add_one(e)
            
    def delete_equipment(self, equipment:Equipment):
        if isinstance(equipment, Source):
            self.source.remove(equipment)
        elif isinstance(equipment, TipRack):
            self.tip_rack.remove(equipment)
        elif isinstance(equipment, Target):
            self.target.remove(equipment)
    
    @property
    def get_equipment(self):
        return self.source + self.target + self.tip_rack
    
        




class YAMLHelper:
    """
    Utility class for reading and writing YAML configuration files.

    This class provides helper methods for accessing application
    configuration files, including equipment definitions, printer
    settings, presets, user settings, and coordinate points. It also
    provides convenience methods for filtering equipment by type and
    updating configuration entries.

    Configuration files are expected to be stored in the project's
    `configs` directory.

    Supported configuration types:
        - equipment: Equipment definitions and geometry
        - points: Equipment origin coordinates
        - printers: Printer and pipette settings
        - preset: Saved workflow presets
        - user: User-specific settings

    Notes:
        Most methods return dictionaries loaded directly from YAML
        files. Configuration updates are written back to disk
        immediately.
    """

    @staticmethod
    def _gui_dir() -> Path:
        """Directory that holds `configs/` for source and packaged runs."""
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            dest = exe_dir
            if sys.platform == "darwin":
                for parent in exe_dir.parents:
                    if parent.suffix == ".app":
                        dest = Path.home() / "Library" / "Application Support" / "LiquidHandler"
                        break
            dest.mkdir(parents=True, exist_ok=True)
            YAMLHelper._seed_configs(dest)
            return dest
        return Path(__file__).parent.resolve()

    @staticmethod
    def _seed_configs(dest_root: Path):
        dest = dest_root / "configs"
        if dest.exists():
            return
        src = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "configs"
        if src.exists():
            shutil.copytree(src, dest)

    @staticmethod
    def _config_path(relative_path: str) -> Path:
        rel = str(relative_path).replace("\\", "/").lstrip("/")
        if not rel.endswith(".yaml"):
            rel = f"{rel}.yaml"
        return YAMLHelper._gui_dir() / rel

    @staticmethod
    def open_file(file_name):
        """
        Open and parse a YAML file.

        Args:
            file_name (str):
                Relative path to the YAML file without the `.yaml`
                extension.

        Returns:
            dict:
                Parsed YAML contents.
        """
        path = YAMLHelper._config_path(file_name)
        with path.open() as f:
            out = yaml.safe_load(f)
        return out

    def open_config(type, name):
        """
        Retrieve a named configuration entry.

        Args:
            type (str):
                Configuration category.

            name (str):
                Configuration name.

        Returns:
            dict:
                Requested configuration entry.

        Raises:
            ValueError:
                If the requested configuration does not exist.
        """
        types = YAMLHelper.open_file(f"configs\\{type}")
        if name not in types.keys():
            raise ValueError(f"{type} {name} not found!")
        else:
            return types[name]
        
    def write_config(config_type, name, data):
        """
        Create or update a configuration entry.

        Args:
            config_type (str):
                Configuration category.

            name (str):
                Name of the configuration entry.

            data (dict):
                Configuration data to store.

        Returns:
            dict:
                Saved configuration entry.
        """
        file_path = f"configs/{config_type}.yaml"

        # load existing configs (or create empty dict if file doesn't exist)
        try:
            types = YAMLHelper.open_file(file_path)
            if types is None:
                types = {}
        except FileNotFoundError:
            types = {}

        # update / insert entry
        types[name] = data

        YAMLHelper.write_yaml(types, file_path)
        return types[name]
    
    @staticmethod
    def write_yaml(data: dict, relative_path: str):
        """
        Write a dictionary directly to a YAML file.

        Args:
            data (dict):
                Data to save.

            relative_path (str):
                Output file path relative to the current module.

        Returns:
            dict:
                Saved data.
        """
        path = YAMLHelper._config_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        return data

    @staticmethod
    def open_equipment():
        """
        Load all equipment definitions.

        Returns:
            dict:
                Equipment configuration data.
        """
        return YAMLHelper.open_file(r"configs\\equipment")
    
    @staticmethod
    def open_equipment_by_type(eq_type_filter):
        """
        Retrieve equipment definitions matching a specific type.

        Args:
            eq_type_filter (str):
                Equipment type to filter by.

        Returns:
            dict:
                Equipment definitions containing the specified type.
        """
        equipment = YAMLHelper.open_file(r"configs\\equipment")

        result = {}

        for key, item in equipment.items():
            eq_type = item.get("type", [])

            # normalize to list
            if isinstance(eq_type, str):
                eq_type = [eq_type]

            if eq_type_filter in eq_type:
                result[key] = item

        return result
    
    def get_tipholders():
        """
        Retrieve all equipment configured as tip holders.

        Returns:
            dict:
                Tip holder definitions.
        """
        return YAMLHelper.open_equipment_by_type("TipHolder")
    
    

    def get_sources():
        """
        Retrieve all equipment configured as sources.

        Returns:
            dict:
                Source definitions.
        """
        return YAMLHelper.open_equipment_by_type("Source")
    def get_targets():
        """
        Retrieve all equipment configured as targets.

        Returns:
            dict:
                Target definitions.
        """
        return YAMLHelper.open_equipment_by_type("Target")
    
        

    @staticmethod
    def open_origin():
        """
        Load all saved coordinate points.

        Returns:
            dict:
                Point configuration data.
        """
        out = YAMLHelper.open_file(r"configs\\points")
        if out is None:
            out = {}
        return out
    @staticmethod
    def open_printer():
        """
        Load printer configurations.

        Returns:
            dict:
                Printer configuration data.
        """
        return YAMLHelper.open_file(r"configs\\printers")
    
    @staticmethod
    def open_preset():
        """
        Load saved workflow presets.

        Returns:
            dict:
                Preset configuration data.
        """
        out = YAMLHelper.open_file(r"configs\\preset")
        if out is None:
            out = {}
        return out

    @staticmethod
    def open_user():
        """
        Load user configuration settings.

        If user.yaml does not exist, a new user.yaml is created from
        user_default.yaml.

        Returns:
            dict:
                User configuration data.
        """
        current_dir = YAMLHelper._gui_dir()

        user_file = current_dir / "configs" / "user.yaml"
        default_file = current_dir / "configs" / "user_default.yaml"

        if not user_file.exists():
            if not default_file.exists():
                raise FileNotFoundError(
                    "Neither user.yaml nor user_default.yaml exists."
                )
            shutil.copy(default_file, user_file)

        data = YAMLHelper.open_file(r"configs\\user")
        if data.get("printer") == "bosco":
            data["printer"] = "heimdall"
            YAMLHelper.write_yaml(data, r"configs\\user.yaml")
        return data
    


    @staticmethod
    def list_content(name):
        """
        List all entries within a configuration file.

        Args:
            name (str):
                Configuration category.

        Returns:
            dict_keys | None:
                Names of all entries, or None if the file is empty.
        """
        file = YAMLHelper.open_file(f"configs\\{name}")
        if not file:
            return None
        return file.keys()
    
    VISIBLE_PRINTERS = ("heimdall",)

    @staticmethod
    def list_printers():
        """
        Printer names shown in the UI dropdown.

        Only Heimdall is selectable. Other machine configs stay in
        printers.yaml for later use.
        """
        names = list(YAMLHelper.list_content("printers") or [])
        visible = [name for name in YAMLHelper.VISIBLE_PRINTERS if name in names]
        return visible or names

    @staticmethod
    def default_printer_name():
        printers = list(YAMLHelper.list_printers())
        return printers[0] if printers else "heimdall"

    @staticmethod
    def open_default_printer():
        return YAMLHelper.open_printer()[YAMLHelper.default_printer_name()]
    
    @staticmethod
    def list_preset():
        """
        List all available presets.

        Returns:
            dict_keys:
                Preset names.
        """
        out = YAMLHelper.list_content("preset")
        if out is None:
            out=[]
        return out
    
    @staticmethod
    def list_equipment():
        """
        List all available equipment definitions.

        Returns:
            dict_keys:
                Equipment names.
        """
        return YAMLHelper.list_content("equipment")
    
    @staticmethod
    def list_points():
        """
        List all saved coordinate points.

        Returns:
            dict_keys:
                Point names.
        """
        return YAMLHelper.list_content("points")


    @staticmethod
    def point_writer(name, data):
        """
        Save a coordinate point to the points configuration file.

        Args:
            name (str):
                Point name.

            data (SE3 | list[float]):
                Point coordinates as either an SE3 transform or
                [x, y, z] list.

        Notes:
            Existing points with the same name are overwritten.
        """
        if isinstance(data, SE3):
            data = [data.t[0], data.t[1], data.t[2]]
        data = {"x": data[0],
                "y": data[1],
                "z": data[2]}
        YAMLHelper.write_config("points", name, data=data)

        
    def save_dict_to_yaml(data: dict, filepath: str):
        """
        Save a dictionary to a YAML file.

        Args:
            data: Dictionary to save
            filepath: Path to output .yaml file
        """

        with open(filepath, "w") as file:
            yaml.dump(data, file, default_flow_style=False)

if __name__ == "__main__":    
    e_name = "tip-holder"
    e = Equipment(e_name, origin_file="8-sample-holder.yaml")
    print(e.grid[0][0].t)
    print(e.grid[1][0].t)
    print(e.grid[0][1].t)
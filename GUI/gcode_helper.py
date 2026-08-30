from spatialmath import SE3
class GCodeHelper():
    def home(axes):
        axes = axes.upper()
        if axes in ("X", "Y", "Z"):
            if axes == "X":
                return [f"G28 X", "G1 Z-30 F600"]

            return f"G28 {axes}"
        else:
            raise ValueError("Axes invalid")
        
    def move_absolute(point, speed=8000):
        if type(point) == SE3:
            point = point.t
        out = f"G0"

        if point[0]:
            out += f" X{point[0]}"
        if point [1]:
            out += f" Y{point[1]}"
        if point [2]:
            out += f" Z{point[2]}"
        if speed:
            out += f" F{speed}"
        return [GCodeHelper.set_absolute(), out, GCodeHelper.finish_move()]
    
    def move_relative(point, speed=8000):
        if type(point) == SE3:
            point = point.t
        
        out = f"G0"

        if point[0]:
            out += f" X{point[0]}"
        if point [1]:
            out += f" Y{point[1]}"
        if point [2]:
            out += f" Z{point[2]}"
        if speed:
            out += f" F{speed}"
            return [GCodeHelper.set_relative(), out, GCodeHelper.finish_move()]
    
    def wait(time):
        return f"G4 P{time}"
    
    def finish_move():
        return "M400"
    
    def fan_on(amount=255):
        return f"M106 S{amount}"
    
    def fan_stop():
        return f"M107"
    
    def set_extruder_temp(temp):
        return f"M104 S{temp}"

    def trigger_pipette(extruder=False, wait_time=2000):
        if extruder:
            return GCodeHelper.flatten([GCodeHelper.wait(500), 
                    GCodeHelper.set_extruder_temp(200), 
                    GCodeHelper.wait(1000), 
                    GCodeHelper.set_extruder_temp(0)])
        else:
            return GCodeHelper.flatten([
                GCodeHelper.fan_on(),
                GCodeHelper.wait(wait_time),
                GCodeHelper.fan_stop()
            ])
        
    def set_absolute():
        return "G90"
    def set_relative():
        return "G91"
    
    def setup_motors():
        return ["G91",
                "G21",
                "M203 X200 Y200 Z30 E50",
                "M201 X3000 Y3000 Z200 E500",
                "M204 T2000",
                "M205 X10 Y10"]

    def setup():
        return ["G91",
                "G21",
                "M203 X200 Y200 Z30 E50",
                "M201 X3000 Y3000 Z200 E500",
                "M204 T2000",
                "M205 X10 Y10",

                "G28 X",
                "G28 Z",
                "G1 Z-30 F600",
                "G28 Y",
                "G90"]
    @staticmethod
    def flatten(list_in):
        if not isinstance(list_in, list):
            return list_in
        flat_list = []
        for item in list_in:
            if isinstance(item, list):
                flat_list.extend(item)
            else:
                flat_list.append(item)
        return flat_list
    
    @staticmethod
    def turn_extruder(distance, speed=100):
        return ["G21", "M302 S0", "M92 E1600", "G91", f"G1 E{distance} F{speed}"]
    
    @staticmethod
    def motors_on():
        return f"M17"
    @staticmethod
    def motors_off(axes):
        if axes in ("x", "y", "z"):

            return f"M18 {axes}"
        elif not axes:
            return "M18"
        else:
            raise ValueError("Axes invalid")
        
    def emergency_stop():
        return "M112"

    def shake(degree=1):
        return GCodeHelper.flatten([
            GCodeHelper.move_relative([degree, 0, 0]),
            GCodeHelper.move_relative([-degree, 0, 0]),
            GCodeHelper.move_relative([degree, 0, 0]),
            GCodeHelper.move_relative([-degree, 0, 0]),
            GCodeHelper.move_relative([degree, 0, 0]),
            GCodeHelper.move_relative([-degree, 0, 0])
        ])
    
    

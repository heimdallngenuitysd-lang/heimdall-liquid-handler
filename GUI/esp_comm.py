import serial, json, time, threading, socket, re, zmq
from printer_controller import PrinterAction
from gcode_helper import GCodeHelper as g
from pymodbus.client import ModbusTcpClient
from typing import Optional, Callable

class PrinterController:
    """
    Handles serial communication with the 3D printer.
    """
    def __init__(self):
        self.serial_connection = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self.on_message_received = None  # Callback for UI log updates
        self._send_lock = threading.RLock()

    # ── Connection ────────────────────────────────────────────────────────────

    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial port names."""
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Open serial connection to printer.
        timeout is used only for readline() blocking — not for move completion.
        """
        try:
            self.serial_connection = serial.Serial(port, baudrate, timeout=timeout)
            time.sleep(2)                          # Wait for printer reboot
            self.serial_connection.flushInput()    # Clear stale buffer data
            self.is_connected = True
            self.stop_event.clear()
            return True, "Connected successfully"
        except Exception as e:
            return False, str(e)

    def disconnect(self):
        self.stop_event.set()
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.is_connected = False

    # ── Core send ─────────────────────────────────────────────────────────────

    def send_gcode(self, gcode: str, max_wait: float = 120.0, log_callback=None):
        """
        Send a single G-code line and wait for the printer to acknowledge.

        Uses wall-clock timeout so long moves (G0 Z50 F300) don't trigger a
        false timeout — only commands that truly hang will fail.

        The 'ok' check is intentionally loose: Marlin sometimes piggybacks
        temperature data onto the ok line, e.g. "ok T:20.1 /0.0 B:19.9".
        """
        if not self.is_connected or not self.serial_connection:
            return False, "Not connected"

        gcode = gcode.strip()
        if not gcode or gcode.startswith(";"):
            return True, "Skipped (empty or comment)"

        with self._send_lock:
            try:
                self.serial_connection.write((gcode + "\n").encode("utf-8"))
                log_callback(f">> {gcode}")

                deadline = time.time() + max_wait

                while True:
                    # Bail out if we've waited too long (real timeout)
                    if time.time() > deadline:
                        return False, f"Timeout ({max_wait}s) waiting for: {gcode}"

                    line = self.serial_connection.readline().decode("utf-8", errors="ignore").strip()

                    if not line:
                        # readline() returned empty — serial timeout, not move done
                        # Just keep looping until wall-clock deadline
                        continue

                    log_callback(f"<< {line}")

                    # ── Less strict ok check ──────────────────────────────
                    # Matches: "ok", "ok T:20.1 /0.0", "OK", etc.
                    if line.lower().startswith("ok"):
                        return True, "Success"

                    # Detect printer errors
                    if "error" in line.lower():
                        return False, f"Printer error: {line}"

            except Exception as e:
                return False, str(e)

    def send_sequence(self, gcode_list: list[str], log_callback=None, progress_callback=None, max_wait: float = 120.0):
        """
        Send a list of G-code commands sequentially, waiting for ok after each.
        progress_callback(current, total) is called after each successful command.
        """
        def log(out):
            if log_callback:
                log_callback(out)
        if not gcode_list:
            return False, f"No gcode sent"
        gcode_list = g.flatten(gcode_list)
        total = len(gcode_list)
        for i, gcode in enumerate(gcode_list):
            if self.stop_event.is_set():
                log("Sequence aborted")
                return False, "Sequence aborted"
            if type(gcode) == PrinterAction:
                if gcode.name:
                    log(gcode.name)
                success,msg = gcode.do_action(self, log_callback=log)
            else:
                log(gcode)
                success, msg = self.send_gcode(gcode, max_wait=max_wait, log_callback=log)
            if not success:
                log(f"Failed on line {i + 1} ({gcode!r}): {msg}")
                return False, f"Failed on line {i + 1} ({gcode!r}): {msg}"
            if progress_callback:
                progress_callback(i + 1, total)
        return True, "Sequence completed"

    # ── Movement helpers ──────────────────────────────────────────────────────

    def move(self, axis: str, distance_mm: float, feedrate: int = 3000):
        """
        Move a single axis by a relative distance (mm).
        Automatically wraps in G91/G90 so absolute position is preserved.
        axis: 'X', 'Y', or 'Z'
        """
        cmds = [
            "G91",                                        # Relative mode
            f"G0 {axis.upper()}{distance_mm} F{feedrate}",
            "G90",                                        # Back to absolute
        ]
        for cmd in cmds:
            ok, msg = self.send_gcode(cmd)
            if not ok:
                return False, msg
        return True, "Move complete"

    def home(self, axes: str = ""):
        """
        Home axes. Pass axes='X Y' or axes='' to home all.
        """
        cmd = f"G28 {axes}".strip()
        return self.send_gcode(cmd, max_wait=120.0)

    def motors_on(self):
        return self.send_gcode("M17")

    def motors_off(self, axes: str = ""):
        """Disable motors. axes='' disables all, axes='Z' disables only Z."""
        cmd = f"M18 {axes}".strip()
        return self.send_gcode(cmd)

    def emergency_stop(self):
        """Immediately halt all motion (M112). Requires reconnect after."""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.write(b"M112\n")
            self._log(">> M112 (EMERGENCY STOP)")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        if self.on_message_received:
            self.on_message_received(msg)



class SerialCommunicator():
    def __init__(self, baudrate=115200, timeout=2):
        self.default_timeout = timeout
        self.baudrate = baudrate
        self.serial_connection = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self._send_lock = threading.RLock()
    
    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial port names."""
        return [p.device for p in serial.tools.list_ports.comports()]
    
    def connect(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Open serial connection to printer.
        timeout is used only for readline() blocking — not for move completion.
        """
        if self.serial_connection:
            self.disconnect()
        try:
            self.serial_connection = serial.Serial(port, baudrate, timeout=timeout)
            time.sleep(.5)                          # Wait for printer reboot
            self.serial_connection.flushInput()    # Clear stale buffer data
            self.is_connected = True
            self.stop_event.clear()
            return True, "Connected successfully"
        except Exception as e:
            return False, str(e)
    
    def disconnect(self):
        """Safely release COM port"""
        self.stop_event.set()
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            self.serial_connection = None
        self.is_connected = False

    def send(self, payload, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        if not isinstance (payload, str):
            payload = str(payload)
        with self._send_lock:
            try:
                self.serial_connection.write((payload + "\n").encode("utf-8"))
                return True, None
            except Exception as e:
                log(e)
                self.disconnect()
                return False, str(e)
    
    def read(self, max_wait:float = 2.0, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        with self._send_lock:
            try:
                deadline = time.time() + max_wait
                while True:
                    # Bail out if we've waited too long (real timeout)
                    if time.time() > deadline:
                        return False, f"Timeout ({max_wait}s) waiting for response"

                    line = self.serial_connection.readline().decode("utf-8", errors="ignore").strip()

                    if not line:
                        # readline() returned empty — serial timeout, not move done
                        # Just keep looping until wall-clock deadline
                        continue
                    if line:
                        return True, line
            except Exception as e:
                log(e)
                self.disconnect()
                return False, str(e)
                    




class ESPCommunicator(SerialCommunicator):

    @staticmethod
    def calculate_checksum(data: str) -> str:
        checksum = 0

        for b in data.encode():
            checksum ^= b

        return checksum
    
    @staticmethod
    def verify_checksum(data: str) -> bool:
        """
        Verifies an embedded "checksum" inside the raw JSON string 
        without risking key-reordering bugs from parsing.
        """
        # Clean up whitespace/newlines
        raw_str = data.strip()
        
        # Use regex to find the value of the "checksum" key
        # It looks for "checksum": followed by any digits
        match = re.search(r'"checksum"\s*:\s*(\d+)', raw_str)
        
        if not match:
            return False
            
        received_checksum = int(match.group(1))
        
        # Replace the actual digits with '0' to match the sender's pre-calculation state
        # This preserves the exact spacing and layout of the original payload
        modified_string = re.sub(r'("checksum"\s*:\s*)(\d+)', r'\g<1>0', raw_str)
        
        # Calculate checksum on the modified layout
        calculated_checksum = ESPCommunicator.calculate_checksum(modified_string)
        
        # Verify match
        return calculated_checksum == received_checksum
    
    def __init__(self, baudrate=115200, timeout=2):
        super().__init__(baudrate=baudrate, timeout=timeout)
        self.command_id = 0
        self.received_id = 0
    
        

    def send_json(self, payload: dict, acknowledge=False, 
                  retries=3, log_callback=None, timeout = 2):
        def log(payload):
            if log_callback:
                log_callback(payload)
        payload_copy = payload.copy()
        payload_copy["checksum"] = "0"
        json_string = json.dumps(
            payload_copy,
            separators=(",", ":")
        )

        payload_copy["checksum"] = ESPCommunicator.calculate_checksum(json_string)
        
        message = json.dumps(
            payload_copy,
            separators=(",", ":")
        )
        print(message)
        if acknowledge:
            for attempt in range(retries):
                log(f"Sending {message}")
                self.send(message)

                response = self.wait_for_ack(
                    payload["id"],
                    timeout=timeout
                )

                if response is None:
                    continue

                if response.get("ok"):
                    log(f"Received ack for {message}")
                    return True, f"Received ack for {message}"

                log(
                    f"ESP reported corruption attempt {attempt + 1} {payload_copy}"
                )
            log(f"No response from ESP for {message}")
            return False,  f"No response from ESP for {message}"
        else:
            self.send(message, log_callback=log_callback)
            log(f"Sent {message}")
            return True, f"Sent {message}"


    def read_json(self, acknowledge=False, log_callback=None, max_wait=3):
        def log(payload):
            if log_callback:
                log_callback(payload)
        status, line = self.read(max_wait=max_wait)
        if not status:
            return status, line

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            log(f"Invalid JSON: {line}")
            return False, line
        


        if acknowledge:
            if ESPCommunicator.verify_checksum(line):
                if "id" in data :
                    self.send_json(
                        {
                            "ack": data["id"],
                            "ok": True
                        },
                        acknowledge=False
                    )
                if data["id"] <= self.received_id:
                    return False, data
                return True, data
        else:
            if ESPCommunicator.verify_checksum(line):
                return True, data
            else:
                return False, data


    
    def wait_for_ack(self, msg_id, timeout):
        deadline = time.time() + timeout

        while time.time() < deadline:
            status, msg = self.read_json(max_wait=timeout)

            if not status:
                continue

            if msg.get("ack") == msg_id:
                return msg

        return None

    
    def connect(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Blocks until ESP sends {"status":"ready"}.
        Filters boot noise + corrupted lines.
        Always releases port on failure.
        """
        # 1. Run the parent class connect method
        success, message = super().connect(port, baudrate, timeout)
        print(success, message)
        # 2. If parent connection failed, exit early and pass up the error
        if not success:
            return False, message
        
        with self._send_lock:
            try:
                # self.serial_connection.setDTR(False)
                # self.serial_connection.setRTS(False)

                time.sleep(2)

                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()

                start = time.time()

                while time.time() < start+timeout:

                    status, msg = self.read_json(max_wait=timeout)

                    if not status:
                        continue

                    if msg.get("status") == "ready":
                        self.is_connected = True
                        return True, f"Connected to {port}"
                probe = {
                    "id": -1
                }
                print(probe)
                status, msg = self.send_json(probe, acknowledge=True)
                if status:
                    return True, f"Connected to {port}"

                else:
                    self.disconnect()
                    print(status, msg)
                    return False, f"Failed to connect to {port}"
            except serial.SerialException as e:
                self.disconnect()
                return False, f"Failed to connect to {port}, {e}"
    def _next_id(self):
        self.command_id += 1
        return self.command_id
    
    def send_command(self, command, log_callback=None):
        def log(input):
            if log_callback:
                log_callback(input)
        if not self.serial_connection or not self.is_connected:
            print(f"{self.serial_connection}, {self.is_connected}")
            return False, "ESP not connected"

        cmd_id = self._next_id()
        command["id"] = cmd_id


        try:
            return self.send_json(command, acknowledge=True, log_callback=log_callback)
        except Exception as e:
            log(e)
            return False, e



class ESPMotorController(ESPCommunicator):
    def __init__(self, baudrate=115200, timeout=1):
        super().__init__(baudrate=baudrate, timeout=timeout)
        self.printer_config = None
        self.is_armed = False
        self.data_callback = None

    def init_ser(self, port):
        """
        Blocks until ESP sends {"status":"ready"}.
        Filters boot noise + corrupted lines.
        Always releases port on failure.
        """

        self.connect(port)


    def close_ser(self):
        """Safely release COM port"""
        self.disconnect()

    def printer_callback(self, printer):
        self.printer_config = printer
    
    def set_port(self, port, baudrate=115200):
        if self.serial_connection and self.serial_connection.port == port:
            return
        self.init_ser(port)

    def send_command(self, direction: bool, run_time: int, speed: int = 100, log_callback=None):
        def log(input):
            if log_callback:
                log_callback(input)
        if not self.serial_connection or not self.is_connected:
            log("ESP not connected")
            return False, "ESP not connected"

        cmd_id = self._next_id()

        payload = {
            "id": cmd_id,
            "cmd": "motor",
            "direction": direction,
            "time": run_time,
            "speed": speed
        }

        dynamic_timeout = max(
            self.default_timeout,
            (run_time / 1000.0) + 1.0
        )

        # old_timeout = self.serial_connection.timeout
        # self.serial_connection.timeout = 0.2   # short poll reads
        with self._send_lock:
            try:
                status, msg = self.send_json(payload, acknowledge=True, log_callback=log_callback)
                if not status:
                    return status, msg
                
                status, msg =  self.read_json(log_callback=log_callback, max_wait=dynamic_timeout)
                if not status:
                    return status, msg
                elif (msg.get("status") == "ok" and
                    msg.get("id") == self.command_id):
                    print("Received end msg")
                    return True, f"Moved {direction} for {run_time} "

        
            except Exception as e:
                log(e)
                return False, e
           

    def extend(self, ms):
        return self.send_command(True, ms)

    def retract(self, ms):
        return self.send_command(False, ms)

    def close(self):
        if self.serial_connection.is_open:
            self.serial_connection.close()

    def send_command_printer_action(self, direction: bool, runtime: int, speed: int = 100, log_callback=None):
        return PrinterAction(
            action=lambda *args, **kwargs: self.send_command(direction, runtime, speed, log_callback=log_callback),
            name=f"Direction {direction} for {runtime} at speed {speed}"
        )
    
    def pause_printer_action(self, runtime):
        def pause(runtime):
            time.sleep(runtime)
            return True, f"Paused for {runtime}"
        return PrinterAction(
            action=lambda *_, **__: pause(runtime),
            name=f"Pausing for {runtime}"
        )

    def prime(self, log_callback=None):
        runtime = self.printer_config["aspiration_actuation_time"]
        return self.send_command_printer_action(True, runtime, log_callback=log_callback)
    
    def aspirate(self, log_callback=None):
        runtime = self.printer_config["aspiration_actuation_time"]
        return self.send_command_printer_action(False, runtime, log_callback=log_callback)
    
    def dispense(self, log_callback=None, shake=False):
        
        pause = self.printer_config["blowout_pause_time"]/1000
        
        out = [self.prime(), 
               self.pause_printer_action(pause), 
               self.send_command_printer_action(True, self.printer_config["blowout_actuation_time"], log_callback=log_callback)]
        if shake:
               out.extend(g.shake())
        else:
            out.extend([
               self.pause_printer_action(1)])
        out.extend([
               self.send_command_printer_action(False, 0)])
        return out
    
    def full_depress(self, log_callback=None):
        pause = self.printer_config["blowout_pause_time"]/1000
        return [self.prime(), 
               self.pause_printer_action(pause), 
               self.send_command_printer_action(True, self.printer_config["blowout_actuation_time"], log_callback=log_callback)]
    
    def full_aspiration(self, log_callback=None):
        runtime = self.printer_config["aspiration_actuation_time"] + self.printer_config["blowout_actuation_time"]
        return [self.send_command_printer_action(False, runtime, log_callback=log_callback)]
        

    
    def spin(self, speed: float, acceleration: float, spin_time: float, motor=0, log_callback=None, data_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        speed = float(speed)
        acceleration = float(acceleration)
        spin_time = float(spin_time)
        if not self.is_armed:
            self.arm(log_callback=log_callback)
        command = { "cmd" : "r",
                    "motor" : motor,
                    "speed": speed,
                   "acceleration": acceleration,
                   "time": spin_time}
        status, msg = super().send_command(command, log_callback=log_callback)
        if not status:
            return status, msg
        start = time.time()
        while time.time() < start + (speed/acceleration) + spin_time + 2:
            status, msg = self.read_json(max_wait=((speed/acceleration) + spin_time))
            if not status:
                continue
            if (msg.get("state", None) == "STOP"):
                log(f"Finished spinning at {speed}RPM, accel {acceleration} for {spin_time}")
                return True, f"Finished spinning at {speed}RPM, accel {acceleration} for {spin_time}"
            
            elif data_callback:
                data_callback(msg)
            
        return False, "Unsure if spinning finished"
    
    def arm(self, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        command = { "cmd" : "a"}
        status, msg = super().send_command(command, log_callback=log_callback)
        if not status:
            print(msg)
            return status, msg
        start = time.time()
        while time.time() < start + 6:
            status, msg = self.read_json(max_wait=6)
            if not status:
                continue
            if (msg.get("state", None) == "READY"):
                log(f"Armed spincoaters")
                self.is_armed = True
                return True, f"Armed spincoaters"
        
            
        return False, "Unsure if spincoaters are armed"
    
    def arm_printer_action(self, log_callback=None):
        return PrinterAction(action=lambda *args, **kwargs: self.arm(log_callback=log_callback),
            name=f"Arming spincoater")

    def stop(self, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        command = { "cmd" : "x"}
        status, msg = super().send_command(command, log_callback=log_callback)
        if not status:
            print(msg)
        return status, msg
    
    def stop_printer_action(self, log_callback=None):
        return PrinterAction(action=lambda *args, **kwargs: self.stop(log_callback=log_callback),
            name=f"Stopping spincoater")

        
    def spin_printer_action(self, speed: float, acceleration: float, time: float, motor: int=0, log_callback=None):
        return PrinterAction(action=lambda *args, **kwargs: self.spin(speed, acceleration, time, motor=motor, log_callback=log_callback, data_callback=self.data_callback),
            name=f"Spin motor {motor} at {speed} RPM for {time} at accel {acceleration}")
    


class SpinCoaterController(ESPCommunicator):
    def __init__(self, baudrate=115200, timeout=1):
        super().__init__(baudrate, timeout)
        self.is_armed = False
        self.rpm = None
        self.acceleration = None
        self.time = None
    def spin(self, speed: float, acceleration: float, spin_time: float, log_callback=None, data_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        speed = float(speed)
        acceleration = float(acceleration)
        spin_time = float(spin_time)
        if not self.is_armed:
            self.arm(log_callback=log_callback)
        command = { "cmd" : "r",
                    "speed": speed,
                   "acceleration": acceleration,
                   "time": spin_time}
        status, msg = self.send_command(command, log_callback=log_callback)
        if not status:
            return status, msg
        start = time.time()
        while time.time() < start + (speed/acceleration) + spin_time + 2:
            status, msg = self.read_json(max_wait=((speed/acceleration) + spin_time))
            if not status:
                continue
            if (msg.get("state", None) == "STOP"):
                log(f"Finished spinning at {speed}RPM, accel {acceleration} for {spin_time}")
                return True, f"Finished spinning at {speed}RPM, accel {acceleration} for {spin_time}"
            
            elif data_callback:
                data_callback(msg)
            
        return False, "Unsure if spinning finished"
    
    def arm(self, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        command = { "cmd" : "a"}
        status, msg = self.send_command(command, log_callback=log_callback)
        if not status:
            print(msg)
            return status, msg
        start = time.time()
        while time.time() < start + 6:
            status, msg = self.read_json(max_wait=6)
            if not status:
                continue
            if (msg.get("state", None) == "READY"):
                log(f"Armed spincoaters")
                self.is_armed = True
                return True, f"Armed spincoaters"
        
            
        return False, "Unsure if spincoaters are armed"

    def stop(self, log_callback=None):
        def log(payload):
            if log_callback:
                log_callback(payload)
        command = { "cmd" : "x"}
        status, msg = self.send_command(command, log_callback=log_callback)
        if not status:
            print(msg)
        return status, msg

        
    def spin_printer_action(self, speed: float, acceleration: float, time: float, motor: int=0, log_callback=None, data_callback=None):
        return PrinterAction(action=lambda *args, **kwargs: self.spin(speed, acceleration, time, motor=motor, log_callback=log_callback, data_callback=data_callback),
            name=f"Spin motor {motor} at {speed} RPM for {time} at accel {acceleration}")
        

class ModbusCommunicator:
    def __init__(self, host: str, port: int = 502, log_callback: Optional[Callable[[str], None]] = None):
        """
        :param host: IP address of the Modbus server/robot.
        :param port: Port number (default 502).
        :param log_callback: A function that takes a string argument for custom logging (e.g., print).
        """
        self.host = host
        self.port = port
        self.log_callback = log_callback
        self.client = ModbusTcpClient(self.host, port=self.port)
        self._lock = threading.RLock()

    def _log(self, message: str):
        """Internal helper to trigger the callback if it exists."""
        if self.log_callback:
            self.log_callback(f"[IPCommunicator] {message}")

    def connect(self, port=None) -> bool:
        """Establishes connection to the Modbus server/robot."""
        with self._lock:
            if port is not None:
                self.port = port
                if self.client and self.client.is_socket_open():
                    self.client.close()
                # Re-initialize or update the client port
                self.client = ModbusTcpClient(self.host, port=self.port)

            if not self.client.is_socket_open():
                self._log(f"Connecting to {self.host}:{self.port}...")
                return self.client.connect()
            return True, "Connected"

    def disconnect(self):
        """Closes the connection safely."""
        with self._lock:
            if self.client:
                self.client.close()
                self._log("Disconnected from Modbus server.")
                return True, "Disconnected"

    def write_coil(self, address: int, value: bool) -> bool:
        """Writes a boolean value to a specific coil address."""
        with self._lock:
            if not self.connect():
                self._log("Connection failed. Cannot write coil.")
                return False
            
            try:
                result = self.client.write_coil(address, value)
                if result.isError():
                    self._log(f"Failed to write {value} to Coil {address}: {result}")
                    return False
                self._log(f"Successfully wrote {value} to Coil {address}")
                return True
            except Exception as e:
                self._log(f"Exception during coil write: {e}")
                return False

    def read_coil(self, address: int) -> Optional[bool]:
        """Reads a boolean value from a specific coil address."""
        with self._lock:
            # if not self.connect():
            #     self._log("Connection failed. Cannot read coil.")
            # return None

            try:
                result = self.client.read_coils(address, count=1)
                # print("result", result)
                if result.isError():
                    self._log(f"Failed to read Coil {address}: {result}")
                    return None
                return result.bits[0]
            except Exception as e:
                self._log(f"Exception during coil read: {e}")
                return None

    def send_pulse(self, address: int, state: bool = True, duration: float = 0.2):
        """
        Sends a temporary pulse to a specific coil.
        If state=True:  Turns ON -> Waits -> Turns OFF
        If state=False: Turns OFF -> Waits -> Turns ON
        """
        self._log(f"Initiating pulse on Coil {address} (Primary State: {state})")
        
        # Step 1: Set to primary state
        with self._lock:
            if self.write_coil(address, state):
                # Step 2: Hold
                time.sleep(duration)
            # Step 3: Revert state
            self.write_coil(address, not state)
        return True, f"Pulse sent to Coil {address} (Duration: {duration}s)"

    def wait_for_chirp(self, address: int, target_state: bool = True, timeout: float = 30.0, poll_interval: float = 0.05) -> bool:
        """
        Blocks execution until the Dobot changes the state of a specific address.
        
        :param address: The Modbus coil address to monitor.
        :param target_state: The state you are waiting for (True for ON chirp, False for OFF).
        :param timeout: Maximum seconds to wait before failing.
        :param poll_interval: How long to sleep between consecutive reads (saves CPU/Network).
        :return: True if the chirp was detected, False if timed out.
        """
        self._log(f"Waiting for chirp ({target_state}) on Coil {address} (Timeout: {timeout}s)...")
        with self._lock:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                current_state = self.read_coil(address)
                # print(current_state)
                if current_state == target_state:
                    self._log(f"Chirp detected on Coil {address}!")
                    return True, "chirp detected"
                    
                time.sleep(poll_interval)
                
            self._log(f"Timed out waiting for chirp on Coil {address}.")
            return False, "no chirp detected"

    def write_register(self, address: int, value: int) -> bool:
        """Writes a 16-bit integer to a holding register address."""
        if not self.connect():
            self._log("Connection failed. Cannot write register.")
            return False
        with self._lock:
            try:
                result = self.client.write_register(address, value)
                if result.isError():
                    self._log(f"Failed to write register {address}: {result}")
                    return False
                return True
            except Exception as e:
                self._log(f"Exception during register write: {e}")
                return False

    def read_register(self, address: int) -> Optional[int]:
        """Reads a 16-bit integer from a holding register address."""
        if not self.connect():
            self._log("Connection failed. Cannot read register.")
            return None
        with self._lock:
            try:
                result = self.client.read_holding_registers(address, count=1)
                if result.isError():
                    self._log(f"Failed to read register {address}: {result}")
                    return None
                return result.registers[0]
            except Exception as e:
                self._log(f"Exception during register read: {e}")
                return None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect_action(self):
        """
        Returns a PrinterAction that connects to the Modbus server.
        Useful for integrating into G-code sequences.
        """
        return PrinterAction(
            action=lambda *args, **kwargs: self.connect(),
            name=f"Connect to {self.host}:{self.port}"
        )
    
    def disconnect_action(self):
        """
        Returns a PrinterAction that disconnects from the Modbus server.
        Useful for integrating into G-code sequences.
        """
        return PrinterAction(
            action=lambda *args, **kwargs: self.disconnect(),
            name=f"Disconnect from {self.host}:{self.port}"
        )

    def wait_for_chirp_action(self, address: int, target_state: bool = True, timeout: float = 30.0, poll_interval: float = 0.05):
        """
        Returns a PrinterAction that waits for a chirp on the specified coil.
        Useful for integrating into G-code sequences.
        """
        return PrinterAction(
            action=lambda *args, **kwargs: self.wait_for_chirp(address, target_state, timeout, poll_interval),
            name=f"Wait for chirp on Coil {address} (State: {target_state})"
        )

    def send_pulse_action(self, address: int, state: bool = True, duration: float = 0.2):
        """
        Returns a PrinterAction that sends a pulse to the specified coil.
        Useful for integrating into G-code sequences.
        """
        return PrinterAction(
            action=lambda *args, **kwargs: self.send_pulse(address, state, duration),
            name=f"Send pulse on Coil {address} (State: {state}, Duration: {duration}s)"
        )
    def write_coil_action(self, address: int, value: bool):
        """
        Returns a PrinterAction that writes a value to a specific coil.
        Useful for integrating into G-code sequences.
        """
        def write_coil_feedback(address, value):
            status = self.write_coil(address, value)
            print("writing coil")
            if status:
                return status, f"Wrote {value} to coil {address}"
            else:
                return status, f"Failed to write {value} to coil {value}"
        return PrinterAction(action=lambda *args, **kwargs: write_coil_feedback(address=address, value=value),
                             name= f"Set Coil {address} to {value}")


class TCPServerCommunicator:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, log_callback: Optional[Callable[[str], None]] = None):
        """
        Synchronous TCP Server to interface with Hikrobot VisionMaster or Dobot.
        """
        self.host = host
        self.port = port
        self.log_callback = log_callback
        
        self.client_socket: Optional[socket.socket] = None
        self.client_address = None
        self.lock = threading.RLock()

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self._log(f"Server initialized on {self.host}:{self.port}")
        except Exception as e:
            self._log(f"Fatal error initializing server socket: {e}")
            raise e

    @property
    def is_connected(self):
        return self.client_socket is not None


    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(f"[VM-TCPServer] {message}")

    def connect(self) -> bool:
        """BLOCKING CALL: Pauses script execution entirely until a client connects."""
        with self.lock:
            try:
                self._log("Waiting for client to connect...")
                client_sock, client_addr = self.server_socket.accept()
                self.client_socket = client_sock
                self.client_socket.settimeout(5.0) 
                self.client_address = client_addr
                self._log(f"Connected successfully from {client_addr[0]}:{client_addr[1]}")
                return True
            except Exception as e:
                self._log(f"Connection acceptance failed: {e}")
                return False

    def write(self, data: str) -> bool:
        """Sends a string payload."""
        with self.lock:
            if not self.client_socket:
                return False
            try:
                if not data.endswith('\n'):
                    data += '\n'
                self.client_socket.sendall(data.encode('utf-8'))
                return True
            except Exception as e:
                self._log(f"[ERROR] Write failed: {e}")
                self.disconnect()
            return False

    def read(self, length: Optional[int] = None, start_limiter: Optional[str] = None, end_limiter: Optional[str] = None) -> Optional[str]:
        """
        Reads data from the socket with dynamic parsing strategies.
        
        :param length: If provided, reads exactly this number of bytes.
        :param start_limiter: Optional starting character/string required to validate data frame.
        :param end_limiter: Optional terminating character/string (e.g., ';' or ']'). Loops until found.
        :returns: Processed clean string, or None if reading failed.
        """
        if not self.client_socket:
            self._log("[WARNING] Read failed: No client connected.")
            return None
        with self.lock:
            try:
                # STRATEGY 1: Fixed Byte Length
                if length is not None:
                    chunks = []
                    bytes_recvd = 0
                    while bytes_recvd < length:
                        chunk = self.client_socket.recv(min(length - bytes_recvd, 512))
                        if not chunk:
                            self._log("[INFO] Connection closed mid-read.")
                            self.disconnect()
                            return None
                        chunks.append(chunk)
                        bytes_recvd += len(chunk)
                    return b"".join(chunks).decode('utf-8')

                # STRATEGY 2: Bounded Delimiters (or End Limiter Only)
                buffer = ""
                target_end = end_limiter if end_limiter else "\n"  # Fallback to newline if no limiters given
                
                while target_end not in buffer:
                    chunk = self.client_socket.recv(512).decode('utf-8')
                    if not chunk:
                        self._log("[INFO] Connection closed mid-read.")
                        self.disconnect()
                        return None
                    buffer += chunk

                # Splicing up to the end limiter
                clean_msg = buffer.split(target_end)[0] + target_end

                # If a specific starting token was requested, validate or strip up to it
                if start_limiter:
                    if start_limiter in clean_msg:
                        # Keep everything from the start limiter forward
                        clean_msg = clean_msg[clean_msg.find(start_limiter):]
                    else:
                        self._log(f"[WARNING] Start limiter '{start_limiter}' not found in message.")
                        return None

                return clean_msg

            except socket.timeout:
                self._log("[TIMEOUT] Reading timed out.")
                return None
            except Exception as e:
                self._log(f"[ERROR] Read error: {e}")
                self.disconnect()
                return None

    def disconnect(self):
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.client_address = None

    def close(self):
        self.disconnect()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

class DobotCommunicator(ModbusCommunicator):
    """
    Specialized communicator for Dobot devices.
    Provides convenience methods for Dobot-specific commands.
    """
    def __init__(self, host: str = "192.168.1.6", port: int = 502, log_callback: Optional[Callable[[str], None]] = None):
        super().__init__(host=host, port=port, log_callback=log_callback)
        self.dobot_address = "192.168.1.6"
        self.dobot_port = 502
        self.remove_coil = 3096  # Example coil address for Dobot-specific commands
        self.place_coil = 3098  # Example coil address for Dobot-specific commands
    
    def send_remove_pulse_action(self, duration: float = 0.2):
        return self.write_coil_action(self.remove_coil, True)

    def wait_place_chirp_action(self, timeout: float = 30.0, poll_interval: float = 0.05):
        return self.wait_for_chirp_action(self.place_coil, target_state=True, timeout=timeout, poll_interval=poll_interval)
    
    def wait_for_dobot_actions(self, timeout:float = 60.0, poll_interval: float = 0.05):
        return [
            self.write_coil_action(self.remove_coil, True),
            self.wait_for_chirp_action(self.place_coil, target_state=True, timeout= timeout, poll_interval=poll_interval),
            self.write_coil_action(self.remove_coil, False),
            self.wait_for_chirp_action(self.place_coil, target_state=False, timeout= timeout, poll_interval=poll_interval)
        ]

class ZMQClient:

    def __init__(
        self, host="localhost", port=5555, timeout_ms=5000, name=None):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.name = name or "Client"
        self.socket.setsockopt_string(zmq.IDENTITY, self.name)

        self.endpoint = f"tcp://{host}:{port}"
        self.socket.connect(self.endpoint)
        print(f"Connected to server at {self.endpoint}")

    def send_command(self, command: str, **kwargs) -> tuple[bool, str]:
        """Sends a command with kwargs to the server and waits for ACK."""
        json_payload = json.dumps(kwargs) if kwargs else "{}"
        request_str = f"{command}, {json_payload}"

        try:
            print(f"Sending: {request_str}")
            self.socket.send(request_str.encode("utf-8"))

            response_bytes = self.socket.recv()
            response_str = response_bytes.decode("utf-8")

            if ":" not in response_str:
                return False, f"Malformed response: {response_str}"

            response_type, content = response_str.split(":", 1)
            parts = [p.strip() for p in content.split(",", 2)]

            if len(parts) < 3:
                return False, f"Invalid ACK format: {content}"

            resp_cmd, resp_status_str, resp_content = parts
            resp_status = resp_status_str.lower() == "true"

            if response_type == "ACK" and resp_cmd == command:
                return resp_status, resp_content
            else:
                return False, f"Unexpected response: {response_str}"

        except zmq.Again:
            print("Error: Request timed out waiting for server.")
            return False, "ERROR: TIMEOUT"
        except Exception as e:
            print(f"Error communicating with server: {e}")
            return False, f"ERROR: {e}"

    def send_blocking_command(self, command: str, timeout=300, **kwargs) -> tuple[bool, str]:
        """Sends a command, waits for ACK, and blocks until execution completes or times out."""
        kwargs = kwargs or {}
        kwargs["response"] = True

        # Send command and parse initial ACK using send_command logic
        json_payload = json.dumps(kwargs)
        request_str = f"{command}, {json_payload}"

        try:
            print(f"Sending: {request_str}")
            self.socket.send(request_str.encode("utf-8"))

            response_bytes = self.socket.recv()
            response_str = response_bytes.decode("utf-8")

            if ":" not in response_str:
                return False, f"Malformed response: {response_str}"

            response_type, content = response_str.split(":", 1)
            parts = [p.strip() for p in content.split(",", 2)]

            if len(parts) < 3:
                return False, f"Invalid ACK format: {content}"

            resp_cmd, resp_status_str, resp_content = parts
            if response_type != "ACK" or resp_cmd != command:
                return False, f"Unexpected response: {response_str}"

            if resp_status_str.lower() != "true":
                return (
                    False,
                    f"Server rejected task '{command}': {resp_content}",
                )

            print(f"ACK received for '{command}'. Waiting for completion...")

            # Polling for completion with ZMQ Poller
            poller = zmq.Poller()
            poller.register(self.socket, zmq.POLLIN)

            start_time = time.time()
            while time.time() - start_time < timeout:
                remaining_time = max(
                    0, int((timeout - (time.time() - start_time)) * 1000)
                )
                socks = dict(poller.poll(100))  # Poll in 100ms chunks

                if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                    result_bytes = self.socket.recv()
                    result_str = result_bytes.decode("utf-8")

                    if ":" in result_str:
                        res_type, res_body = result_str.split(":", 1)
                        res_parts = [p.strip() for p in res_body.split(",", 2)]

                        if len(res_parts) == 3:
                            res_cmd, res_status, res_msg = res_parts
                            if res_type == "DONE" and res_cmd == command:
                                return res_status.lower() == "true", res_msg

                    return False, f"Malformed execution response: {result_str}"

            return False, f"ERROR: Task '{command}' timed out after {timeout}s"

        except zmq.Again:
            print("Error: Request timed out waiting for server ACK.")
            return False, "ERROR: TIMEOUT"
        except Exception as e:
            print(f"Error communicating with server: {e}")
            return False, f"ERROR: {e}"

    def close(self):
        """Clean up sockets and context."""
        self.socket.close()
        self.context.term()
        print("Client disconnected.")

    def send_command_action(self, command: str, **kwargs):
        """Returns a wrapped action function with merged keyword arguments."""
        return PrinterAction(
            action=lambda *args, **extra_kwargs: self.send_command(name=f"Send action {command}",
                command=command, **{**kwargs, **extra_kwargs}))

    def send_blocking_command_action(self, command: str, **kwargs):
        """Returns a wrapped action function with merged keyword arguments."""
        return PrinterAction(name=f"Send blocking action {command}",
            action=lambda *args, **extra_kwargs: self.send_blocking_command(
                command=command, **kwargs))
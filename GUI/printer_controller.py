import serial
import serial.tools.list_ports
import time
import threading
from gcode_helper import GCodeHelper as g
from tkinter import messagebox

class PrinterAction:
    def __init__(self, action, name=None):
        self.action = action
        self.name = name
    def __str__(self):
        if self.name:
            return self.name
        else:
            return str(self.action)
    def do_action(self, printer_controller, log_callback=None):
        return self.action(printer_controller=printer_controller,log_callback=log_callback)
class PrinterController:
    """
    Handles serial communication with the 3D printer.
    """
    def __init__(self):
        self.serial_connection = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self.on_message_received = None  # Callback for UI log updates
        self._send_lock = threading.Lock()

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

    def _send_gcode(self, gcode: str, max_wait: float = 120.0, log_callback=None):
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
        # print(gcode_list)
        gcode_list = g.flatten(gcode_list)
        total = len(gcode_list)
        for i, gcode in enumerate(gcode_list):
            if self.stop_event.is_set():
                log("Sequence aborted")
                return False, "Sequence aborted"
            if type(gcode) == PrinterAction:
                if gcode.name:
                    log(gcode.name)
                try:
                    success,msg = gcode.do_action(self, log_callback=log)
                except:
                    pass
            else:
                log(gcode)
                success, msg = self._send_gcode(gcode, max_wait=max_wait, log_callback=log)
            if not success:
                log(f"Failed on line {i + 1} ({gcode!r}): {msg}")
                return False, f"Failed on line {i + 1} ({gcode!r}): {msg}"
            if progress_callback:
                progress_callback(i + 1, total)
        return True, "Sequence completed"

    # ── Movement helpers ──────────────────────────────────────────────────────

    # def move(self, axis: str, distance_mm: float, feedrate: int = 3000):
    #     """
    #     Move a single axis by a relative distance (mm).
    #     Automatically wraps in G91/G90 so absolute position is preserved.
    #     axis: 'X', 'Y', or 'Z'
    #     """
    #     cmds = [
    #         "G91",                                        # Relative mode
    #         f"G0 {axis.upper()}{distance_mm} F{feedrate}",
    #         "G90",                                        # Back to absolute
    #     ]
    #     for cmd in cmds:
    #         ok, msg = self.send_gcode(cmd)
    #         if not ok:
    #             return False, msg
    #     return True, "Move complete"

    # def home(self, axes: str = ""):
    #     """
    #     Home axes. Pass axes='X Y' or axes='' to home all.
    #     """
    #     cmd = f"G28 {axes}".strip()
    #     return self.send_gcode(cmd, max_wait=120.0)

    # def motors_on(self):
    #     return self.send_gcode("M17")

    # def motors_off(self, axes: str = ""):
    #     """Disable motors. axes='' disables all, axes='Z' disables only Z."""
    #     cmd = f"M18 {axes}".strip()
    #     return self.send_gcode(cmd)

    # def emergency_stop(self):
    #     """Immediately halt all motion (M112). Requires reconnect after."""
    #     if self.serial_connection and self.serial_connection.is_open:
    #         self.serial_connection.write(b"M112\n")
    #         self._log(">> M112 (EMERGENCY STOP)")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        if self.on_message_received:
            self.on_message_received(msg)


if __name__ == "__main__":
    print("PrinterController module loaded.")
    print("Available ports:", PrinterController.list_ports())

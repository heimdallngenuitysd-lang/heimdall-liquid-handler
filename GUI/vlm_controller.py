import os
import time
import cv2
import ast
import re
from dotenv import load_dotenv
from google import genai
from gcode_helper import GCodeHelper as g
from printer_controller import PrinterController, PrinterAction
from equipment import YAMLHelper as y

class VLMController:
    def __init__(self, volume=None,camera=1):
        self.volume = volume
        self.camera = camera
        self.last_valid = None
        self.iteration = 0 
        self.max_iterations = 20
        self.printer_config = y.open_default_printer()
        self.first_adjust = False
    def adjust(self, volume, printer_controller, log_callback=None, delay=5, interval=1):
        def log(text):
            if log_callback:
                log_callback(str(text))

        def camera():
                self.iteration += 1
                if self.iteration > self.max_iterations:
                    log(f"TIMEOUT: Failed to reach target {target} after {self.max_iterations} attempts")
                    return False, None
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                cap = cv2.VideoCapture(self.camera, backend)

                if not cap.isOpened():
                    # print("Camera did not open")
                    log(f"Camera {self.camera} did not open")
                    raise Exception("Camera did not open")
                    return False, None
                time.sleep(2)

                frame = None
                ret = False

                for _ in range(30):
                    ret, frame = cap.read()
                    if ret:
                        break
                    time.sleep(0.1)

                if not ret:
                    log("Image not captured")
                    cap.release()
                    return False, None
                
                image_path = str(y._gui_dir() / "image.jpg")

                # Save it securely to that exact location
                cv2.imwrite(image_path, frame)

                # print("Image saved as image.jpg")
                log("Image Captured")

                cap.release()
                time.sleep(2)

                digits = extract_digit(image_path,log) # returns parsed JSON dict
                log(f"Detected digit: {digits}")

                if digits is None:
                    log("Digits is None")
                    return False, None

                result = ""
                for pos in ["1", "2", "3", "4"]:
                    d = digits.get(pos)
                    if d is None:
                        log(f"Position {pos} missing")
                        return True, None
                    result += str(d)
                return True, int(result)


        def send_digit_corrections(current_reading, target):
            time.sleep(0.2)

            commands = [
                "G21",
                "M302 S0",
                "M92 E1600",
                "M302 S170",
                "G90"
            ]

            printer_controller.send_sequence(commands)
            
            # Dead zone recovery
            if current_reading is None:
                if self.last_valid is None:
                    # No previous info – creep forward slowly
                    step = 0.05
                else:
                    # Move toward the target from last known position
                    step = 0.05 if target > self.last_valid else -0.05

                printer_controller.send_sequence(g.turn_extruder(step))
                log(f"Dead zone recovery: G1 E{step} F100")
                time.sleep(2)
                return  # Don't update last_valid

            # Valid reading – update last known position
            self.last_valid = current_reading


            if current_reading != target:
                e_value = 0.2 * (target - int(current_reading))/interval
                printer_controller.send_sequence(g.turn_extruder(e_value))
                log(f"Sending correction: G1 E{e_value} F100")
                time.sleep(2 + abs(e_value) * 0.6)

            time.sleep(1)
        

        if self.volume and self.volume == volume:
            return True, "adjustment complete"

        target = volume

        # Reset state for this adjustment
        self.last_valid = None
        self.iteration = 0
        

        while True:
            
            print(self.volume)
            if self.first_adjust:
                send_digit_corrections(self.volume, target) 
            self.first_adjust = True

            status, reading = camera()

            if not status:
                continue

            log(f"Read: {reading} | Target: {target}")

            self.volume = reading

            if reading == target:
                log(f"Target {target} reached!")
                break

            
            time.sleep(2)

        return True, "adjustment complete"
    


                # more adjustments
    def printer_callback(self, printer):
        self.printer_config = printer





def extract_digit(image_path, log):
    load_dotenv(y._gui_dir() / ".env")
    # Set API key directly
    # Replace the empty string below with your actual API key"
    api_key=os.getenv("GEMINI_API_KEY")
    

        
    try:
        # Initialize the GenAI client with the key directly
        client = genai.Client(api_key=api_key)
        
        log("Uploading image to Gemini...")
        # Upload the file
        sample_file = client.files.upload(file=image_path)
        
        log("Analyzing image...")
        
        dict_format = (
            "{'digits': {"
            "'1': <fully visible uncut digit 0-9, or None>, "
            "'2': <fully visible uncut digit 0-9, or None>, "
            "'3': <fully visible uncut digit 0-9, or None>, "
            "'4': <fully visible uncut digit 0-9, or None>}}"
        )

        prompt = (
        f"Look at the vertical black display in this image. Inside this display, there are four "
        f"digits aligned vertically. These digits together form a 4-digit volume reading (top to bottom)."
        f'''Positions: 
        Position 1 = TOP-most digit
        Position 2 = second from top
        Position 3 = third from top
        Position 4 = BOTTOM-most digit)'''

        f"The digits rotate horizontally. Because of this, each position may sometimes show partial digits, "
        f"overlapping digits, or a digit cut off on the left or right.\n\n"

        f"CRITICAL RULES (apply these STRICTLY to EACH of the 4 digit independently):\n"
        f"1. A digit is valid ONLY if exactly ONE complete, fully visible digit is present in that position, and no other digit is bleeding into that slot.\n"
        f"2. If ANY part of a neighbouring digit is visible in the same slot, the digit is INVALID.\n"
        f"3. If the digit is cut off on the left or right, it is INVALID.\n"
        f"4. If you are unsure about ANY digit, mark it INVALID.\n"
        f"5. If digit is not perfectly centered in its position, it is INVALID.\n\n"

        f"Return ONLY a Python dictionary, no explanation, no extra text:{dict_format}"
        )   

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[sample_file, prompt]
        )
        
        # Clean up the file from Gemini storage
        client.files.delete(name=sample_file.name)

        if not response.text:
            return None

        result_text = response.text.strip()

        # Parse the JSON/Dict response
        try:
            match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if not match:
                print(f"Could not find dictionary in response: {result_text}")
                return None
            
            parsed = ast.literal_eval(match.group())
            return parsed.get("digits")
            
        except (ValueError, SyntaxError, KeyError) as e:
            print(f"Failed to parse response: {e}")
            print(f"Raw text: {result_text}")
            return None

    except Exception as e:
        log(f"Error calling Gemini API: {e}")
        return None


# Allows running this file directly for testing
# if __name__ == "__main__":
#     import sys
#     if len(sys.argv) < 2:
#         print("Usage: python ocr_module.py <image_path>")
#         sys.exit(1)

#     result = extract_digit(sys.argv[1])
#     if result is not None:
#         print(f"Extracted digits: {result}")

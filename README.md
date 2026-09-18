Heimdall is a low-cost, open-source automated liquid-handling platform developed by repurposing a Creality Ender-series FDM 3D printer. The system retains the printer's Cartesian motion architecture while integrating a modular 3D-printed pipetting mechanism, an ESP32-based actuator controller, and host-side software for automated liquid-handling workflows.

A key feature of Heimdall is its vision-language model (VLM)-based closed-loop pipette-volume verification system. A camera captures the pipette volume display, and the VLM interprets the displayed setting. If the measured state differs from the requested target, the system automatically applies corrective actuation and repeats the verification process until the target setting is reached.

The platform supports:

Automated Cartesian positioning using G-code and the existing printer controller.
Programmable pipette-volume adjustment using the repurposed extruder stepper motor.
Automated aspiration, dispensing, blowout, and plunger control using an ESP32 and TB6612FNG motor driver.
Closed-loop visual verification and correction of pipette volume settings using Gemini 2.5 Flash.
Interchangeable fixtures for pipettes, labware, pipette tips, and camera positioning.
Host-side control through a Python-based graphical user interface.

The repository contains the software, firmware, control scripts, hardware-related files, and supporting documentation required to reproduce and operate the Heimdall liquid-handling platform.

Heimdall was developed as an accessible automation platform for laboratory workflows and as a foundation for integration into modular and self-driving laboratory systems.

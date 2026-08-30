#include <ESP32Servo.h>
#include <math.h>
#include <ArduinoJson.h>

/*
  Multi Scale Spin Coater - ESP32 + ESC
  IMPORTANT: This code keeps the original motor-running logic and only adds
  real-time DATA lines for the Python GUI graph.

  GUI / Serial commands:
    r RPM ACC HOLD       Example: r 3000 2000 5
    m THROTTLE SECONDS   Example: m 1330 3
    a                    Arm ESC again at 1000 us
    x                    Emergency stop

  Telemetry sent to GUI:
    DATA,time_seconds,commanded_rpm,throttle,state
*/

Servo esc;

// ===== CHANGE THIS ONLY IF YOUR ESC SIGNAL WIRE IS ON ANOTHER ESP32 PIN =====
#define ESC_PIN 13


int last_id = -1;
// ESC throttle values in microseconds
const int STOP_THROTTLE  = 1000;
//const int START_THROTTLE = 1154;   // motor start/kick throttle
const int START_THROTTLE = 1060;   // motor start/kick throttle
const int MAX_THROTTLE   = 2000;

// ESC update interval
const unsigned long UPDATE_INTERVAL_MS = 20;     // 50 Hz ESC pulse update
const unsigned long TELEMETRY_INTERVAL_MS = 100; // GUI graph update every 100 ms

// RPM vs throttle calibration table from your experiment
const int NUM_POINTS = 4;
float rpmTable[NUM_POINTS] = {3000, 4000, 5000, 6000};
//int throttleTable[NUM_POINTS] = {1330, 1400, 1500, 1600};
int throttleTable[NUM_POINTS] = {1274, 1360, 1430, 1530};

int currentThrottle = STOP_THROTTLE;
float currentRPM = 0.0;

unsigned long profileStartMs = 0;
unsigned long lastTelemetryMs = 0;

bool verifyChecksum(const String& rawJson) {
    String json = rawJson;
    json.trim();

    // Find "checksum":
    int keyPos = json.indexOf("\"checksum\"");
    if (keyPos < 0) {
        Serial.println("Missing checksum key");
        return false;
    }

    int colonPos = json.indexOf(':', keyPos);
    if (colonPos < 0) {
        Serial.println("Malformed checksum field");
        return false;
    }

    // Skip whitespace
    int valueStart = colonPos + 1;
    while (valueStart < json.length() && isspace(json[valueStart])) {
        valueStart++;
    }

    // Read numeric checksum
    int valueEnd = valueStart;
    while (valueEnd < json.length() && isdigit(json[valueEnd])) {
        valueEnd++;
    }

    if (valueStart == valueEnd) {
        Serial.println("Invalid checksum value");
        return false;
    }

    int receivedChecksum = json.substring(valueStart, valueEnd).toInt();

    // Replace checksum digits with 0
    String modified =
        json.substring(0, valueStart) +
        "0" +
        json.substring(valueEnd);

    String calculatedHex = calculateChecksum(modified);

    char receivedHex[3];
    sprintf(receivedHex, "%02X", receivedChecksum);

    return calculatedHex.equalsIgnoreCase(receivedHex);
}

String calculateChecksum(const String& data) {
    uint8_t checksum = 0;

    for (size_t i = 0; i < data.length(); i++) {
        checksum ^= (uint8_t)data[i];
    }

    char buf[3];
    sprintf(buf, "%02X", checksum);

    return String(buf);
}

void sendJsonWithChecksum(JsonDocument& doc) {
    doc["checksum"] = 0;

    String payload;
    serializeJson(doc, payload);

    String checksumHex = calculateChecksum(payload);

    // If your protocol uses decimal checksum:
    doc["checksum"] = strtol(checksumHex.c_str(), nullptr, 16);

    payload = "";
    serializeJson(doc, payload);

    Serial.println(payload);
}

// ---------------- LOW LEVEL ESC WRITE ----------------
void writeThrottle(int throttle) {
  currentThrottle = constrain(throttle, STOP_THROTTLE, MAX_THROTTLE);
  esc.writeMicroseconds(currentThrottle);
}

// ---------------- GUI TELEMETRY ----------------
void sendTelemetry(const char *state) {
  float t = 0.0;
  if (profileStartMs > 0) {
    t = (millis() - profileStartMs) / 1000.0;
  }

  StaticJsonDocument<64> msg;
  msg["time"] = t;
  msg["rpm"] = currentRPM;
  msg["throttle"] = currentThrottle;
  msg["state"] = state;

  sendJsonWithChecksum(msg);
  
}

void sendTelemetryTimed(const char *state) {
  unsigned long now = millis();
  if (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    sendTelemetry(state);
    lastTelemetryMs = now;
  }
}

// ---------------- ARM ESC ----------------
void armESC() {
  profileStartMs = millis();
  currentRPM = 0;

  unsigned long startMs = millis();
  while (millis() - startMs < 5000) {
    writeThrottle(STOP_THROTTLE);
    sendTelemetryTimed("ARMING");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(STOP_THROTTLE);
  currentRPM = 0;
  sendTelemetry("READY");
}

// ---------------- RPM TO THROTTLE ----------------
int rpmToThrottle(float targetRPM) {
  if (targetRPM <= 0) {
    return STOP_THROTTLE;
  }

  if (targetRPM < rpmTable[0] || targetRPM > rpmTable[NUM_POINTS - 1]) {
    return -1;
  }

  for (int i = 0; i < NUM_POINTS; i++) {
    if (fabs(targetRPM - rpmTable[i]) < 0.01) {
      return throttleTable[i];
    }
  }

  for (int i = 0; i < NUM_POINTS - 1; i++) {
    if (targetRPM > rpmTable[i] && targetRPM < rpmTable[i + 1]) {
      float rpm1 = rpmTable[i];
      float rpm2 = rpmTable[i + 1];
      int throttle1 = throttleTable[i];
      int throttle2 = throttleTable[i + 1];
      float ratio = (targetRPM - rpm1) / (rpm2 - rpm1);
      float throttle = throttle1 + ratio * (throttle2 - throttle1);
      return (int)round(throttle);
    }
  }

  return -1;
}

// ---------------- EMERGENCY STOP CHECK ----------------
bool checkEmergencyStop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');

    StaticJsonDocument<128> doc;
    DeserializationError err = deserializeJson(doc, msg);

    if (err) {
        return false;  // Can't even determine the id
    }

    int id = doc["id"] | 0;

    if (!verifyChecksum(msg)) {
    StaticJsonDocument<64> ack;
    ack["ack"] = id;
    ack["status"] = "ok";
    ack["ok"] = false;

    sendJsonWithChecksum(ack);
    return false;
    }

    StaticJsonDocument<64> ack;
    ack["ack"] = id;
    ack["status"] = "ok";
    ack["ok"] = true;

    sendJsonWithChecksum(ack);

    if (id == -1){
      last_id = -1;
    }

    if (id <= last_id){
      return false;
    }

    
    String cmd = doc["cmd"];
    if (cmd == "x" || cmd == "X") {
      writeThrottle(STOP_THROTTLE);
      currentRPM = 0;
      return true;
    }
    return false;
} else {return false;}
}

// ---------------- RAW MOTOR TEST ----------------
void rawMotorTest(int throttle, float seconds) {
  throttle = constrain(throttle, STOP_THROTTLE, MAX_THROTTLE);
  if (seconds <= 0) seconds = 2;

  profileStartMs = millis();
  lastTelemetryMs = 0;
  currentRPM = 0; // raw throttle test, RPM unknown without tachometer

  // Serial.println("================================");
  // Serial.println("RAW MOTOR TEST");
  // Serial.print("Throttle command: "); Serial.print(throttle); Serial.println(" us");
  // Serial.print("Run time: "); Serial.print(seconds, 2); Serial.println(" s");
  // Serial.println("If this also does not spin, check ESC signal pin, common GND, battery, and arming.");
  // Serial.println("================================");

  unsigned long testTimeMs = (unsigned long)(seconds * 1000.0);
  unsigned long startMs = millis();

  while (millis() - startMs < testTimeMs) {
    if (checkEmergencyStop()) return;
    writeThrottle(throttle);
    sendTelemetryTimed("TEST");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(STOP_THROTTLE);
  currentRPM = 0;
  sendTelemetry("STOP");
  // Serial.println("=== RAW MOTOR TEST COMPLETE: MOTOR BAND ===");
}

// ---------------- RAMP + HOLD + AUTO STOP ----------------
void rampHoldStop(float targetRPM, float accelerationRPMps, float holdTimeSec) {
  if (targetRPM <= 0) {
    writeThrottle(STOP_THROTTLE);
    currentRPM = 0;
    sendTelemetry("STOP");
    // Serial.println("Target RPM is zero. Motor band.");
    return;
  }

  if (accelerationRPMps <= 0) {
    sendTelemetry("FAILED");
    // Serial.println("Acceleration is wrong. Give positive value.");
    return;
  }

  if (holdTimeSec < 0) {
    sendTelemetry("FAILED");
    // Serial.println("Hold time cannot be negative.");
    return;
  }

  int targetThrottle = rpmToThrottle(targetRPM);
  if (targetThrottle == -1) {
    // Serial.println("ERROR: For this RPM throttle calibration is not available.");
    // Serial.println("Allowed RPM range: 3000 to 6000 RPM");
    // Serial.println("3000 RPM -> 1330 throttle");
    // Serial.println("4000 RPM -> 1400 throttle");
    // Serial.println("5000 RPM -> 1500 throttle");
    // Serial.println("6000 RPM -> 1600 throttle");
    sendTelemetry("RPM ERROR");
    return;
  }

  unsigned long rampTimeMs = (unsigned long)((targetRPM / accelerationRPMps) * 1000.0);
  unsigned long holdTimeMs = (unsigned long)(holdTimeSec * 1000.0);

  if (rampTimeMs < UPDATE_INTERVAL_MS) {
    rampTimeMs = UPDATE_INTERVAL_MS;
  }

  int startThrottle = START_THROTTLE;

  profileStartMs = millis();
  lastTelemetryMs = 0;

  // Serial.println("================================");
  // Serial.println("Ramp + Hold + Auto Stop Command");
  // Serial.print("Target RPM: "); Serial.println(targetRPM);
  // Serial.print("Acceleration: "); Serial.print(accelerationRPMps); Serial.println(" RPM/s");
  // Serial.print("Calculated Ramp Time: "); Serial.print(rampTimeMs / 1000.0, 3); Serial.println(" seconds");
  // Serial.print("Hold Time: "); Serial.print(holdTimeSec, 3); Serial.println(" seconds");
  // Serial.print("Start Throttle: "); Serial.println(startThrottle);
  // Serial.print("Target Throttle: "); Serial.println(targetThrottle);
  // Serial.print("Total Expected Time: "); Serial.print((rampTimeMs + holdTimeMs) / 1000.0, 3); Serial.println(" seconds");
  // Serial.println("================================");

  // This is kept from original working logic: give starting throttle first
  currentRPM = 0;
  writeThrottle(startThrottle);
  sendTelemetry("START");
  delay(50);

  // Serial.println("Ramping started...");

  unsigned long rampStartTime = millis();
  unsigned long elapsedTime = 0;

  while (elapsedTime < rampTimeMs) {
    if (checkEmergencyStop()) {
      return;
    }

    elapsedTime = millis() - rampStartTime;
    float ratio = (float)elapsedTime / (float)rampTimeMs;
    if (ratio > 1.0) {
      ratio = 1.0;
    }

    int throttle = startThrottle + ratio * (targetThrottle - startThrottle);
    currentRPM = ratio * targetRPM;
    writeThrottle(throttle);
    sendTelemetryTimed("RAMP");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(targetThrottle);
  currentRPM = targetRPM;
  sendTelemetry("HOLD");

  // Serial.println("=== Target RPM command reached ===");
  // Serial.print("Final Ramp Throttle: "); Serial.println(currentThrottle);
  // Serial.println("================================");
  // Serial.println("Constant speed hold started...");

  unsigned long holdStartTime = millis();

  while ((millis() - holdStartTime) < holdTimeMs) {
    if (checkEmergencyStop()) {
      return;
    }
    writeThrottle(targetThrottle);
    currentRPM = targetRPM;
    sendTelemetryTimed("HOLD");
    delay(UPDATE_INTERVAL_MS);
  }

  // Serial.println("=== Hold complete ===");
  // Serial.println("Motor stopping automatically...");

  writeThrottle(STOP_THROTTLE);
  currentRPM = 0;
  sendTelemetry("STOP");

  // Serial.println("=== MOTOR BAND ===");
  // Serial.print("Final Throttle: "); Serial.println(currentThrottle);
  // Serial.println("================================");
}

void setup() {
  Serial.begin(115200);
  delay(300);

  ESP32PWM::allocateTimer(0);
  esc.setPeriodHertz(50);
  esc.attach(ESC_PIN, STOP_THROTTLE, MAX_THROTTLE);

  writeThrottle(STOP_THROTTLE);

  // Serial.println("================================");
  // Serial.println("Multi Scale Spin Coater ESP32");
  // Serial.print("ESC signal pin: GPIO"); Serial.println(ESC_PIN);
  // Serial.println("Commands:");
  // Serial.println("r RPM ACC HOLD       Example: r 3000 2000 5");
  // Serial.println("m THROTTLE SECONDS   Example: m 1330 3");
  // Serial.println("a                    Arm ESC again");
  // Serial.println("x                    Emergency stop");
  // Serial.println("================================");

  armESC();
}

void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');

    StaticJsonDocument<128> doc;
    DeserializationError err = deserializeJson(doc, msg);

    if (err) {
        return;  // Can't even determine the id
    }

    int id = doc["id"] | 0;

    if (!verifyChecksum(msg)) {
    StaticJsonDocument<64> ack;
    ack["ack"] = id;
    ack["status"] = "ok";
    ack["ok"] = false;

    sendJsonWithChecksum(ack);
    return;
    }

    StaticJsonDocument<64> ack;
    ack["ack"] = id;
    ack["status"] = "ok";
    ack["ok"] = true;

    sendJsonWithChecksum(ack);

    if (id == -1){
          last_id = -1;
        }

    if (id <= last_id){
      return;
    }

  
    String cmd = doc["cmd"];
    last_id = id;
    if (cmd == "x" || cmd == "X") {
      writeThrottle(STOP_THROTTLE);
      currentRPM = 0;
    }
    else if (cmd == "a" || cmd == "A") {
      armESC();
    }
    else if (cmd == "m" || cmd == "M") {
      int throttle = doc["throttle"];
      float seconds = doc["time"];
      rawMotorTest(throttle, seconds);
    }
    else if (cmd == "r" || cmd == "R") {
      float targetRPM = doc["speed"];
      float acceleration = doc["acceleration"];
      float holdTime = doc["time"];
      rampHoldStop(targetRPM, acceleration, holdTime);
    }
  }
}
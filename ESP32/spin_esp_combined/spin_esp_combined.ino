#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <math.h>
#define ESC_PIN 13
#define ESC_PIN1 12
const int ENA  = 23;
const int AIN1 = 14;
const int AIN2 = 22;

Servo esc;
Servo esc1;

// ESP32 PWM
const int pwmChannel = 0;
const int pwmFreq = 5000;
const int pwmResolution = 8;   // 0-255
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


// Watchdog timer
unsigned long lastCommandTime = 0;
const unsigned long TIMEOUT_MS = 7000;

// Global speed
int currentPwmSpeed = 255;

void coastStop() {
  ledcWrite(ENA, 0);
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, LOW);
}

void extendStart() {
  digitalWrite(AIN1, HIGH);
  digitalWrite(AIN2, LOW);
  ledcWrite(ENA, currentPwmSpeed);
}

void retractStart() {
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, HIGH);
  ledcWrite(ENA, currentPwmSpeed);
}

void extendFor(uint32_t ms) {
  extendStart();
  delay(ms);
  coastStop();
}

void retractFor(uint32_t ms) {
  retractStart();
  delay(ms);
  coastStop();
}

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
void writeThrottle(int throttle, int motor=0) {
  currentThrottle = constrain(throttle, STOP_THROTTLE, MAX_THROTTLE);
  switch(motor) {
    case 0:
      esc.writeMicroseconds(currentThrottle);
      break;
    case 1:
      esc1.writeMicroseconds(currentThrottle);
      break;    
  }
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
    writeThrottle(STOP_THROTTLE, 0);
    writeThrottle(STOP_THROTTLE, 1);
    sendTelemetryTimed("ARMING");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(STOP_THROTTLE, 0);
  writeThrottle(STOP_THROTTLE, 1);
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
      writeThrottle(STOP_THROTTLE, 0);
      writeThrottle(STOP_THROTTLE, 1);
      currentRPM = 0;
      return true;
    }
    return false;
} else {return false;}
}

// ---------------- RAW MOTOR TEST ----------------
void rawMotorTest(int throttle, float seconds, int motor=0) {
  throttle = constrain(throttle, STOP_THROTTLE, MAX_THROTTLE);
  if (seconds <= 0) seconds = 2;

  profileStartMs = millis();
  lastTelemetryMs = 0;
  currentRPM = 0;

  unsigned long testTimeMs = (unsigned long)(seconds * 1000.0);
  unsigned long startMs = millis();

  while (millis() - startMs < testTimeMs) {
    if (checkEmergencyStop()) return;
    writeThrottle(throttle, motor);
    sendTelemetryTimed("TEST");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(STOP_THROTTLE, motor);
  currentRPM = 0;
  sendTelemetry("STOP");
}

// ---------------- RAMP + HOLD + AUTO STOP ----------------
void rampHoldStop(float targetRPM, float accelerationRPMps, float holdTimeSec, int motor=0) {
  if (targetRPM <= 0) {
    writeThrottle(STOP_THROTTLE, motor);
    currentRPM = 0;
    sendTelemetry("STOP");
    return;
  }

  if (accelerationRPMps <= 0) {
    sendTelemetry("FAILED");
    return;
  }

  if (holdTimeSec < 0) {
    sendTelemetry("FAILED");
    return;
  }

  int targetThrottle = rpmToThrottle(targetRPM);
  if (targetThrottle == -1) {
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

  currentRPM = 0;
  writeThrottle(startThrottle, motor);
  sendTelemetry("START");
  delay(50);

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
    writeThrottle(throttle, motor);
    sendTelemetryTimed("RAMP");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(targetThrottle, motor);
  currentRPM = targetRPM;
  sendTelemetry("HOLD");

  unsigned long holdStartTime = millis();

  while ((millis() - holdStartTime) < holdTimeMs) {
    if (checkEmergencyStop()) {
      return;
    }
    writeThrottle(targetThrottle, motor);
    currentRPM = targetRPM;
    sendTelemetryTimed("HOLD");
    delay(UPDATE_INTERVAL_MS);
  }

  writeThrottle(STOP_THROTTLE, motor);
  currentRPM = 0;
  sendTelemetry("STOP");
}

void runPipette(StaticJsonDocument<128> doc){
  lastCommandTime = millis();

  bool direction = doc["direction"];   // true = extend
  uint32_t runTime = doc["time"];
  int speedPct = doc["speed"];

  speedPct = constrain(speedPct, 0, 100);
  currentPwmSpeed = map(speedPct, 0, 100, 0, 255);

  if (direction && runTime) {
    extendFor(runTime);
  } else {
    if (runTime) {
      retractFor(runTime);
    } else {
      retractStart();
    }
  }
  int id = doc["id"] | 0;

  StaticJsonDocument<128> reply;
  reply["status"] = "ok";
  reply["direction"] = direction;
  reply["runtime"] = runTime;
  reply["id"] = id;

  sendJsonWithChecksum(reply);
  Serial.println();
  lastCommandTime = millis();
}


void setup() {
  Serial.begin(115200);
  // ESC setup
  ESP32PWM::allocateTimer(0);
  esc.setPeriodHertz(50);
  esc.attach(ESC_PIN, STOP_THROTTLE, MAX_THROTTLE);

  esc1.setPeriodHertz(50);
  esc1.attach(ESC_PIN1, STOP_THROTTLE, MAX_THROTTLE);

  writeThrottle(STOP_THROTTLE, 0);
  writeThrottle(STOP_THROTTLE, 1);

  // motor input setup
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);

  // ESP32 PWM setup
  ledcAttach(ENA, pwmFreq, pwmResolution);

  retractStart();
  lastCommandTime = millis();

  armESC();

  // clear any leftover junk (optional but helpful)
  while (Serial.available()) {
    Serial.read();
  }

  // READY handshake (MUST be JSON only)
  Serial.println("{\"status\":\"ready\"}");

}


void loop() {
  if (Serial.available()) {
    String msg = Serial.readStringUntil('\n');

    StaticJsonDocument<128> doc;
    DeserializationError err = deserializeJson(doc, msg);

    if (err) {
        return;  // Can't even determine the id
    }

    int id = doc["id"] | -1;

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
    } else if (id <= last_id){
      return;
    }

    String cmd = doc["cmd"];
    last_id = id;
    if (cmd == "x" || cmd == "X") {
      writeThrottle(STOP_THROTTLE, 0); 
      writeThrottle(STOP_THROTTLE, 1); 
      currentRPM = 0;
    }
    else if (cmd == "a" || cmd == "A") {
      armESC();
    }
    else if (cmd == "m" || cmd == "M") {
      int throttle = doc["throttle"];
      float seconds = doc["time"];
      int motor = doc["motor"];
      rawMotorTest(throttle, seconds, motor);
    }
    else if (cmd == "r" || cmd == "R") {
      float targetRPM = doc["speed"];
      float acceleration = doc["acceleration"];
      float holdTime = doc["time"];
      int motor = doc["motor"];
      rampHoldStop(targetRPM, acceleration, holdTime, motor);
    } else if (cmd == "motor") {
      runPipette(doc);
    }
    

  // watchdog: auto retract after no messages
  if (millis() - lastCommandTime >= TIMEOUT_MS) {
    currentPwmSpeed = 255;
    retractStart();
    }
  }
}
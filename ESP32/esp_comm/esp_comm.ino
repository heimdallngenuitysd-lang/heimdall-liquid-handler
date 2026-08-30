#include <ArduinoJson.h>

const int ENA  = 23;
const int AIN1 = 14;
const int AIN2 = 22;

// ESP32 PWM
const int pwmChannel = 0;
const int pwmFreq = 5000;
const int pwmResolution = 8;   // 0-255
int last_id = -1;

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

void setup() {
  Serial.begin(115200);

  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);

  // ESP32 PWM setup
  ledcAttach(ENA, pwmFreq, pwmResolution);

  retractStart();
  lastCommandTime = millis();

  // let boot messages finish
  delay(500);

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

    if (id == -1 | id <= last_id){
      return;
    }


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

    StaticJsonDocument<128> reply;
    reply["status"] = "ok";
    reply["direction"] = direction;
    reply["runtime"] = runTime;
    reply["id"] = id;

    sendJsonWithChecksum(reply);
    Serial.println();
    lastCommandTime = millis();
  }

  // watchdog: auto retract after no messages
  if (millis() - lastCommandTime >= TIMEOUT_MS) {
    currentPwmSpeed = 255;
    retractStart();
  }
}
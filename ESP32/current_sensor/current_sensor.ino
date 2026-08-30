#include <Wire.h>
#include <Adafruit_INA219.h>

Adafruit_INA219 ina219;

// TB6612FNG pins
const int ENA  = 23;
const int AIN1 = 14;
const int AIN2 = 19;

// PWM
const int pwmChannel = 0;
const int pwmFreq = 1000;
const int pwmResolution = 8;
const int motorSpeed = 180;

// timing
const unsigned long runTime = 2000;
const unsigned long stopTime = 3000;
const unsigned long ignoreTime = 300;   // ignore startup spike

// current threshold
const float currentThreshold = 80.0;   // mA

void motorStop() {
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, LOW);
  ledcWrite(pwmChannel, 0);
}

void extendMotor() {
  digitalWrite(AIN1, HIGH);
  digitalWrite(AIN2, LOW);
  ledcWrite(pwmChannel, motorSpeed);
}

void retractMotor() {
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, HIGH);
  ledcWrite(pwmChannel, motorSpeed);
}

float readCurrent() {
  return abs(ina219.getCurrent_mA());   // handle reverse polarity
}

void runMotorWithLogging(bool extend) {
  unsigned long start = millis();

  if (extend)
    extendMotor();
  else
    retractMotor();

  while (millis() - start < runTime) {
    float current = readCurrent();

    // Serial Plotter
    Serial.print("Current:");
    Serial.println(current);

    // // ignore initial inrush current
    if (millis() - start > ignoreTime) {
      if (current > currentThreshold) {
        Serial.println("STALL DETECTED");
        motorStop();
        delay(5000);
        return;
      }
    }

    delay(10);
  }

  motorStop();
}

void setup() {
  Serial.begin(115200);
  Wire.begin();

  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);

  ledcSetup(pwmChannel, pwmFreq, pwmResolution);
  ledcAttachPin(ENA, pwmChannel);

  motorStop();

  if (!ina219.begin()) {
    Serial.println("INA219 not found");
    while (1);
  }

  Serial.println("Start loop");
}

void loop() {
  Serial.println("EXTEND");
  runMotorWithLogging(true);

  delay(stopTime);

  Serial.println("RETRACT");
  runMotorWithLogging(false);

  delay(stopTime);
}
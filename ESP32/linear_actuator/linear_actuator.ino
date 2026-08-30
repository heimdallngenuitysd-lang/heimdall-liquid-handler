// Automatic solution Despenser Machine. 
// ESP32 DevKit V1 -> TB6612FNG
// NOTE: GPIO32 is now INPUT trigger. Move TB6612FNG PWMA (enable) to GPIO33.
// AIN1 -> GPIO22, AIN2 -> GPIO14, STBY tied HIGH on PCB.

const int ENA       = 23; // TB6612FNG PWMA (enable)
const int AIN1      = 14; // TB6612FNG AIN1 (direction for motor 1 out)
const int AIN2      = 22; // TB6612FNG AIN2 (direction for motor 2nd out)
const int TRIG_PIN  = 32; // external logic trigger (3.3V-3.7 HIGH, must required)from 3d printer. )

/* Timings (tune as needed) */
const uint32_t MOVE3   = 1110;  // 1.10 seconds seconds move
const uint32_t MOVE4   = 600; //.6 seconds retracting dispensor.
const uint32_t PAUSE1  = 2000;  // 2 seconds pause
const uint32_t HOME_MS = 8000;  // startup/final retract time -> adjust to your actuator stroke---- also 8 seconds

int pulseCount = 0;   // how many HIGH triggers seen in this cycle
int lastTrig   = LOW;

void coastStop() {
  digitalWrite(ENA, LOW);   // outputs off (coast)
}

void extendStart() {         // function call for forward direction
  digitalWrite(AIN1, HIGH);
  digitalWrite(AIN2, LOW);
  digitalWrite(ENA, HIGH);
}
void retractStart() {        // function call for reverse direction (retract)
  digitalWrite(AIN1, LOW);
  digitalWrite(AIN2, HIGH);
  digitalWrite(ENA, HIGH); 
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

/* Sequences */
void doSequence1() {              // 1st HIGH: forward 1.1 seconds
  extendFor(MOVE3);
}

void doSequence2() {              // 2nd HIGH: reverse 1.1 seconds
  retractFor(MOVE3);
}

void doSequence3() {              // 3rd HIGH: F3s, off1s, F3s, B3s, F3s, B3s
  extendFor(MOVE3);
  delay(PAUSE1);
  extendFor(MOVE4);
  retractFor(MOVE4);
  //extendFor(MOVE4); not required now; but can use to desspense the solution further okay
  //retractFor(MOVE4);not required now; but can use to desspense the solution further okay 
}

void setup() {
  pinMode(ENA, OUTPUT);
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);
  pinMode(TRIG_PIN, INPUT_PULLDOWN);   // ensure external signal is 3.3V, not 5V
  Serial.begin(115200);
  delay(200);
  // Power-on homing: fully retract to default position in 3D printer. 
  retractFor(HOME_MS);
  coastStop();

  lastTrig = digitalRead(TRIG_PIN);
}

void loop() {
  int now = digitalRead(TRIG_PIN);
  Serial.print("now = ");
    Serial.println(now);
    delay(100);

  // Rising edge: count HIGH pulses and run the mapped sequence
  if (now == HIGH && lastTrig == LOW) {
    pulseCount++;
    Serial.print("[TRIGGER] Rising edge. pulseCount = ");
    Serial.println(pulseCount);
    if      (pulseCount == 1) doSequence1();
    else if (pulseCount == 2) doSequence2();
    else if (pulseCount == 3) doSequence3();
    // extra HIGHs beyond 3 are ignored until the “final LOW → home” step
    delay(50); // simple debounce
  }

  // After 3rd sequence, on falling edge (LOW), return to home and rest 3s, then reset cycle
  if (now == LOW && lastTrig == HIGH && pulseCount >= 3) {
    retractFor(2000);
    // delay(3000);
    //delay(300);
    pulseCount = 0;  // ready for the next cycle
  }

  lastTrig = now;
  Serial.print("lasttrig = ");
    Serial.println(lastTrig);
    //delay(100); //only this much is required okay.
}

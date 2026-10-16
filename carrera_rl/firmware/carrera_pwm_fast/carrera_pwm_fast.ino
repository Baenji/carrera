/*
 * Carrera GO PWM-Steuerung, schnelle Variante für carrera_rl
 *
 * Gleiche Verdrahtung wie scaled_pwm_controller.ino (PWM an Pin 11, LEDs an 2 und 4).
 * Unterschiede zur alten Firmware:
 *  - 115200 statt 9600 Baud
 *  - KEINE Textausgabe pro Befehl. Die alte Firmware schickt pro Befehl ~120 Zeichen
 *    zurück; bei 9600 Baud blockiert das den Arduino ~125 ms pro Befehl.
 *  - Watchdog: kommt 500 ms lang kein Befehl, wird das Gas auf 0 gesetzt
 *    (Auto bleibt stehen, wenn der PC-Prozess abstürzt). carrera_rl.record sendet
 *    deshalb alle 100 ms den aktuellen Wert erneut.
 *
 * Protokoll: Zahl 0-100 gefolgt von '\n'. "STATUS\n" liefert eine Statuszeile.
 */

const int CARRERA_PIN = 11;
const int RED_PIN = 2;
const int BLUE_PIN = 4;
const unsigned long WATCHDOG_MS = 500;

char buf[16];
int len = 0;
int currentSpeed = 0;
unsigned long lastCommand = 0;

void setup() {
  Serial.begin(115200);
  pinMode(CARRERA_PIN, OUTPUT);
  pinMode(RED_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  setSpeed(0);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buf[len] = '\0';
      if (len > 0) handleLine();
      len = 0;
    } else if (len < (int)sizeof(buf) - 1) {
      buf[len++] = c;
    }
  }
  if (currentSpeed != 0 && millis() - lastCommand > WATCHDOG_MS) {
    setSpeed(0);
  }
}

void handleLine() {
  if (strcmp(buf, "STATUS") == 0) {
    Serial.print("STATUS:speed=");
    Serial.print(currentSpeed);
    Serial.print(",errors=0,uptime=");
    Serial.print(millis());
    Serial.print(",pin=");
    Serial.println(CARRERA_PIN);
    return;
  }
  int value = atoi(buf);
  if (value < 0) value = 0;
  if (value > 100) value = 100;
  lastCommand = millis();
  if (value != currentSpeed) setSpeed(value);
}

void setSpeed(int speed) {
  currentSpeed = speed;
  analogWrite(CARRERA_PIN, map(speed, 0, 100, 0, 255));
  // LEDs wie in der alten Firmware
  digitalWrite(RED_PIN, speed >= 35 ? HIGH : LOW);
  digitalWrite(BLUE_PIN, (speed >= 20 && speed < 48) ? HIGH : LOW);
}

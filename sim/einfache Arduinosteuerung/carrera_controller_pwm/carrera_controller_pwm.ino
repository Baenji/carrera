const int CARRERA_PIN = 11; // PWM Pin
int previousValue = 0;     // Speichert den letzten eingestellten Wert

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50); // 50 ms

  // PWM-PIN (11) und 2 bis 6 auf OUTPUT setzen
  pinMode(CARRERA_PIN, OUTPUT);
  for(int x=2; x < 7; x++ ) {
    pinMode(x, OUTPUT);
  }
  
  // Anfangsgeschwindigkeit: 0
  set_LEDs(previousValue);
  set_PWM(previousValue); 
}

void loop() {
  if (Serial.available() > 0) {
    
    // signal should be in range 0 - 100
    String s = Serial.readStringUntil('\n');
    int value = s.toInt();
    
    value = constrain(value, 0, 100);

    if (value != previousValue) {
      set_LEDs(value);
      set_PWM(value);
      
      previousValue = value;
    } 
  }
}

void set_LEDs(int value) {
  digitalWrite(2, value >= 10);
  digitalWrite(3, value >= 30);
  digitalWrite(4, value >= 50);
  digitalWrite(5, value >= 70);
  digitalWrite(6, value >= 90);
}

void set_PWM(int value) {
  int pwm = map(value, 0, 100, 0, 255);
  analogWrite(CARRERA_PIN, pwm);
}


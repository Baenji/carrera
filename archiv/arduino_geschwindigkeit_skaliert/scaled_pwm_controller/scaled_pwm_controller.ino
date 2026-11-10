const int CARRERA_PIN = 11; // PWM Pin
const int RED_PIN = 2;
const int BLUE_PIN = 4;
int previousValue = -1;     // Speichert den letzten eingestellten Wert
int errorCount = 0;         // Zählt aufgetretene Fehler

void setup() {
  Serial.begin(9600);
  pinMode(CARRERA_PIN, OUTPUT);
  pinMode(RED_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  
  Serial.println("=== Carrera GO Controller gestartet ===");
  Serial.println("Pin 11 als Output konfiguriert");
  Serial.println("Gib eine Zahl zwischen 0 und 100 ein und drücke ENTER.");
  
  analogWrite(CARRERA_PIN, 0); // Anfangsgeschwindigkeit: 0
}

void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim(); // Entferne Whitespace
    
    // Prüfe auf STATUS-Kommando
    if (input.equalsIgnoreCase("STATUS")) {
      sendStatus();
    } else if (input.length() == 0) {
      // Leere Eingabe - ignoriere, zähle aber als Fehler
      errorCount++;
      Serial.println("ERROR: Leere Eingabe empfangen");
    } else {
      // Normale Geschwindigkeitssteuerung
      // Prüfe ob Eingabe numerisch ist
      bool isNumeric = true;
      for (unsigned int i = 0; i < input.length(); i++) {
        if (!isDigit(input.charAt(i)) && input.charAt(i) != '-') {
          isNumeric = false;
          break;
        }
      }
      
      if (!isNumeric) {
        errorCount++;
        Serial.print("ERROR: Ungültige Eingabe (nicht numerisch): ");
        Serial.println(input);
      } else {
        int rawValue = validateInput(input.toInt());
        set_speed(rawValue);
        sendFeedbackToRL(rawValue);
      }
    }

    // Input-Puffer leeren
    while (Serial.available() > 0) {
      Serial.read();
    }
  }
}

// Funktion zur Validierung der Eingabe (0 bis 100)
int validateInput(int value) {
  if (value < 0) {
    errorCount++;
    Serial.println("ERROR: Wert unter 0, korrigiert auf 0");
    return 0;
  }
  if (value > 100) {
    errorCount++;
    Serial.println("ERROR: Wert über 100, korrigiert auf 100");
    return 100;
  }
  return value;
}

void set_speed(int speed) {
  set_lights(speed);
  if (speed >= 0 && speed <= 100) {
    // Umrechnen von 0–100 auf 0–255 (PWM)
    int pwmWert = map(speed, 0, 100, 0, 255);
    analogWrite(CARRERA_PIN, pwmWert);
    previousValue = speed; // Speichere aktuellen Wert
    
    Serial.print("Geschwindigkeit gesetzt auf: ");
    Serial.print(speed);
    Serial.print("% (PWM ");
    Serial.print(pwmWert);
    Serial.println(")");
  } else {
    Serial.println("Ungültiger Wert! Bitte Zahl zwischen 0 und 100 eingeben.");
  }
}

// Sendet strukturierten Status für Python-Abfrage
void sendStatus() {
  Serial.print("STATUS:");
  Serial.print("speed=");
  Serial.print(previousValue >= 0 ? previousValue : 0);
  Serial.print(",errors=");
  Serial.print(errorCount);
  Serial.print(",uptime=");
  Serial.print(millis());
  Serial.print(",pin=");
  Serial.println(CARRERA_PIN);
}

void set_lights(int speed) {
  Serial.println("SPEED");
  if (speed >= 48) {
    digitalWrite(RED_PIN, HIGH);
    digitalWrite(BLUE_PIN, LOW);
  } else if (speed >= 35) {
    digitalWrite(RED_PIN, HIGH);
    digitalWrite(BLUE_PIN, HIGH);
  } else if (speed >= 20) {
    digitalWrite(RED_PIN, LOW);
    digitalWrite(BLUE_PIN, HIGH);
  } else {
    digitalWrite(RED_PIN, LOW);
    digitalWrite(BLUE_PIN, LOW);
  }
}

// Funktion zur Rückmeldung für das RL-Modell
void sendFeedbackToRL(int currentSpeed) {
  Serial.print("Aktuelle Geschwindigkeit: ");
  Serial.print(currentSpeed);
  Serial.print(" | Zielgeschwindigkeit (0-100): ");
  Serial.println(currentSpeed);
}


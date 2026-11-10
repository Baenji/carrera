/*
 * MCP4151-103 Digitales Potentiometer Ansteuerung
 *
 * Chip: MCP4151-103
 * - 10kΩ Gesamtwiderstand (103 = 10k)
 * - 257 Steps (0-256)
 * - SPI Interface (Mode 0,0 oder 1,1)
 * - Max 10 MHz SPI Clock
 *
 * Verdrahtung:
 * Arduino Pin 10 (SS)   -> MCP4151 Pin 1 (CS/SHDN)
 * Arduino Pin 11 (MOSI) -> MCP4151 Pin 3 (SDI/SDO)
 * Arduino Pin 13 (SCK)  -> MCP4151 Pin 2 (SCK)
 * Arduino 5V            -> MCP4151 Pin 8 (VDD)
 * Arduino GND           -> MCP4151 Pin 4 (VSS)
 *
 * Carrera GO Verbindung (nur 2 Kabel!):
 * MCP4151 Pin 6 (P0A) - Terminal A -> Carrera GO Kabel 1
 * MCP4151 Pin 5 (P0W) - Wiper      -> Carrera GO Kabel 2
 * MCP4151 Pin 7 (P0B) - Terminal B -> NICHT VERBUNDEN (offen lassen)
 *
 * Funktion: Variabler Widerstand zwischen P0A und P0W steuert Geschwindigkeit
 * - 2.34 kΩ (Wert 60)  = langsam
 * - 9.96 kΩ (Wert 255) = schnell
 */

#include <SPI.h>

const int CS_PIN = 10;   // Chip-Select-Pin für den MCP4151
int previousValue = -1;  // Speichert den letzten eingestellten Wert

void setup() {
  Serial.begin(9600);       // Startet die serielle Kommunikation
  SPI.begin();              // Initialisiert SPI
  pinMode(CS_PIN, OUTPUT);
  digitalWrite(CS_PIN, HIGH);  // CS auf HIGH, wenn nicht aktiv
  Serial.println("MCP4151-103 Geschwindigkeitssteuerung bereit.");
  Serial.println("Widerstandsbereich: 0-10 kOhm");
}

void loop() {
  if (Serial.available() > 0) {                  
    String input = Serial.readStringUntil('\n');  
    int rawValue = validateInput(input.toInt());

    // Skalierung von 0-100 auf 60-255
    int scaledValue = map(rawValue, 0, 100, 60, 255);
    if (scaledValue != previousValue) {      // Prüft, ob der neue Wert sich vom alten unterscheidet
      setPotentiometer(scaledValue);         // Setzt direkt ohne Verzögerung
      previousValue = scaledValue;           // Aktualisiert den letzten Wert
      sendFeedbackToRL(previousValue, rawValue);
    }
  }
}

// Funktion zur Validierung der Eingabe (0 bis 100)
int validateInput(int value) {
  if (value < 0) return 0;
  if (value > 100) return 100;
  return value;
}

// Funktion zum Einstellen des Potentiometerwerts über SPI
void setPotentiometer(byte value) {
  // MCP4151 benötigt 16-Bit Kommando:
  // Bits 15-12: Adresse (0x0 = Wiper 0)
  // Bits 11-10: Command (00 = Write)
  // Bits 9-8: Don't care
  // Bits 7-0: Wiper value (0-256, aber wir limitieren auf 0-255)

  uint16_t command = 0x0000 | (value & 0xFF);  // Write command für Wiper 0

  SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));  // MCP4151 unterstützt bis 10 MHz
  digitalWrite(CS_PIN, LOW);             // CS aktivieren

  // 16-Bit Kommando senden
  SPI.transfer16(command);               // Sendet beide Bytes korrekt als 16-Bit Wert

  digitalWrite(CS_PIN, HIGH);            // CS deaktivieren
  SPI.endTransaction();
  
  // Ausgabe zur Kontrolle
  // Widerstand berechnen: R = (value / 256) * 10kΩ
  float resistance = (value / 256.0) * 10.0;
  Serial.print("Potentiometerwert: ");
  Serial.print(value);
  Serial.print(" | Widerstand: ~");
  Serial.print(resistance, 2);
  Serial.println(" kΩ");
}

// Funktion zur Rückmeldung für das RL-Modell
void sendFeedbackToRL(int currentSpeed, int targetSpeed) {
  Serial.print("Aktuelle Geschwindigkeit (Potentiometer): ");
  Serial.print(currentSpeed);
  Serial.print(" | Zielgeschwindigkeit (0-100): ");
  Serial.println(targetSpeed);
}
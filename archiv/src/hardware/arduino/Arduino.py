import serial
import serial.tools.list_ports
import time

class ArduinoInterface:
    @staticmethod
    def find_arduino_port():
        """Findet automatisch den Arduino-Port"""
        ports = serial.tools.list_ports.comports()

        # Suche nach Arduino
        for port in ports:
            # Check Arduino vendor ID (2341) or USB serial device
            if ('2341' in port.hwid or  # Arduino VID
                'usbmodem' in port.device.lower() or  # macOS Arduino ports
                'usbserial' in port.device.lower() or  # CH340/CH341 chips on macOS
                any(keyword in port.description.lower() for keyword in ['arduino', 'ch340', 'ch341', 'usb-serial'])):
                try:
                    # Skip Bluetooth and debug ports
                    if 'bluetooth' in port.device.lower() or 'debug-console' in port.device.lower():
                        continue
                    
                    # Teste ob Port zugänglich ist
                    test = serial.Serial(port.device, 9600, timeout=0.1)
                    test.close()
                    print(f"Arduino gefunden auf: {port.device}")
                    return port.device
                except:
                    continue

        # Fallback: Nimm ersten verfügbaren USB-Port (keine Bluetooth-Ports)
        for port in ports:
            if 'bluetooth' not in port.device.lower() and 'debug' not in port.device.lower():
                try:
                    test = serial.Serial(port.device, 9600, timeout=0.1)
                    test.close()
                    print(f"Fallback Port verwendet: {port.device}")
                    return port.device
                except:
                    continue

        raise serial.SerialException("Kein Arduino gefunden!")

    def __init__(self, port=None, baudrate=9600, initial_speed=0):
        """Initialisiert die Verbindung zum Arduino"""
        if port is None:
            port = self.find_arduino_port()

        self.serial_connection = serial.Serial(port, baudrate, timeout=0.1, write_timeout=0)
        time.sleep(2)  # Arduino-Reset abwarten

        # Buffer leeren
        self.serial_connection.reset_input_buffer()
        self.serial_connection.reset_output_buffer()
        
        if initial_speed > 0:
            self.set_signal_rate(initial_speed)

    def set_signal_rate(self, speed) -> None | int:
        """Setzt die Geschwindigkeit (0-100) - BLOCKIERT NICHT

        Der Arduino wandelt 0-100 automatisch in PWM-Signale um:
        - Skalierung: 0-100 -> 0-255 (map Funktion)
        - PWM: analogWrite auf Pin 11
        - Direkte Steuerung der Carrera GO Bahn
        - Falls ein Wert zurückgegeben wird, sind es die tatsächlich gesendeten Bytes
        """
        if not 0 <= speed <= 100:
            raise ValueError("Geschwindigkeit muss zwischen 0 und 100 liegen")

        try:
            # Sende sauberen Wert 0-100 zum Arduino
            command = f"{int(speed)}\n"
            bytes = self.serial_connection.write(command.encode())
            #print(f"➡️ Sende an Arduino: {command.strip()} mit ({bytes} Bytes)")
            return bytes
            # KEIN WARTEN, KEIN LESEN - sofort zurückkehren
        except Exception as e:
            # Ignoriere Fehler beim Senden um Blocking zu verhindern
            print(f"⚠️ Fehler beim Senden an Arduino: {e}")

    def get_status(self, timeout=1.0) -> dict:
        """Ruft Status vom Arduino ab
        
        Returns:
            dict mit:
            - speed: Aktuelle Geschwindigkeit (0-100)
            - errors: Fehleranzahl (0 = keine Fehler)
            - uptime: Arduino Laufzeit in Millisekunden
            - pin: PWM Pin Nummer
            - raw_response: Original-Antwort vom Arduino
            - communication_ok: Boolean ob Kommunikation erfolgreich
            - serial_messages: Liste aller Serial-Ausgaben (inkl. Fehlermeldungen)
        """
        try:
            # Lese zuerst alle angesammelten Serial-Nachrichten (ohne Buffer zu leeren)
            serial_messages = []
            while self.serial_connection.in_waiting > 0:
                try:
                    line = self.serial_connection.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        serial_messages.append(line)
                except:
                    break
            
            # Sende STATUS-Kommando
            self.serial_connection.write(b"STATUS\n")
            time.sleep(0.1)  # Kurze Wartezeit für Arduino-Antwort
            
            # Lese Antwort mit Timeout
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < timeout:
                if self.serial_connection.in_waiting > 0:
                    line = self.serial_connection.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("STATUS:"):
                        response = line
                        break
                    elif line:
                        serial_messages.append(line)
            
            if not response:
                return {
                    "speed": None,
                    "errors": None,
                    "uptime": None,
                    "pin": None,
                    "raw_response": "",
                    "communication_ok": False,
                    "error_message": "Keine Antwort vom Arduino erhalten",
                    "serial_messages": serial_messages
                }
            
            # Parse STATUS:speed=50,errors=0,uptime=12345,pin=11
            status = {
                "raw_response": response,
                "communication_ok": True,
                "serial_messages": serial_messages
            }
            
            # Extrahiere Key-Value Paare
            data_part = response.split("STATUS:")[1]
            pairs = data_part.split(",")
            
            for pair in pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    try:
                        status[key.strip()] = int(value.strip())
                    except ValueError:
                        status[key.strip()] = value.strip()
            
            return status
            
        except Exception as e:
            return {
                "speed": None,
                "errors": None,
                "uptime": None,
                "pin": None,
                "raw_response": "",
                "communication_ok": False,
                "error_message": str(e),
                "serial_messages": []
            }


    def close(self):
        """Schließt die Verbindung"""
        if self.serial_connection and self.serial_connection.is_open:
            self.set_signal_rate(0)
            self.serial_connection.close()

# Verwendung
if __name__ == "__main__":
    try:
        arduino = ArduinoInterface()
        print(f"✅ Verbunden auf {arduino.serial_connection.port}")

        # Setze Geschwindigkeit
        arduino.set_signal_rate(50)
        time.sleep(0.5)
        
        # Hole Status
        status = arduino.get_status()
        #print(f"\n📊 Arduino Status:")
        #print(f"   Geschwindigkeit: {status.get('speed')}%")
        #print(f"   Fehler: {status.get('errors')}")
        #print(f"   Laufzeit: {status.get('uptime')}ms")
        #print(f"   PWM Pin: {status.get('pin')}")
        #print(f"   Kommunikation OK: {status.get('communication_ok')}")
        
        # Zeige Serial Messages
        serial_msgs = status.get('serial_messages', [])
        if serial_msgs:
            #print(f"\n📝 Arduino Nachrichten:")
            for msg in serial_msgs:
                print(f"   {msg}")
        
        arduino.set_signal_rate(0)
        arduino.close()
        print("\n✅ Beendet")

    except Exception as e:
        print(f"❌ Fehler: {e}")

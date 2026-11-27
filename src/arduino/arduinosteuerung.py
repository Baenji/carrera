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
    
    def close(self):
        """Schließt die Verbindung"""
        if self.serial_connection and self.serial_connection.is_open:
            self.set_signal_rate(0)
            self.serial_connection.close()

    def set_signal_rate(self, speed) -> None | int:
        """Setzt die Geschwindigkeit (0-100)

        Der Arduino wandelt 0-100 automatisch in PWM-Signale um:
        - Skalierung: 0-100 -> 0-255 (map Funktion)
        """
        if not 0 <= speed <= 100:
            raise ValueError("Geschwindigkeit muss zwischen 0 und 100 liegen")

        try:
            # Sende sauberen Wert 0-100 zum Arduino
            command = f"{int(speed)}\n"
            bytes = self.serial_connection.write(command.encode())
            return bytes
        except Exception as e:
            # Ignoriere Fehler beim Senden um Blocking zu verhindern
            print(f"Fehler beim Senden an Arduino: {e}")


if __name__ == "__main__":
    try:
        arduino = ArduinoInterface()
        print(f"✅ Verbunden auf {arduino.serial_connection.port}")

        for speed in range(0, 80, 10):
            print(speed)
            arduino.set_signal_rate(speed)
            time.sleep(2)

        arduino.close()
        
    except Exception as e:
        print(f"Fehler: {e}")
#!/usr/bin/env python3
"""
Test-Skript um pyserial zu überprüfen und das Arduino Interface zu testen
"""

import sys
import time

def test_pyserial_installation():
    """Teste ob pyserial korrekt installiert ist"""
    print("=== PySerial Installation Test ===")
    
    # Entferne das falsche serial Modul aus dem Cache
    if 'serial' in sys.modules:
        del sys.modules['serial']
    
    try:
        # Forciere Import von pyserial
        import serial
        
        # Prüfe ob Serial Klasse verfügbar ist
        if hasattr(serial, 'Serial'):
            print("✓ pyserial ist korrekt installiert")
            print(f"  Version: {getattr(serial, '__version__', 'Unbekannt')}")
            print(f"  Pfad: {serial.__file__}")
            
            # Teste COM-Port listing
            try:
                import serial.tools.list_ports
                ports = list(serial.tools.list_ports.comports())
                if ports:
                    print(f"✓ Verfügbare COM-Ports:")
                    for port in ports:
                        print(f"  - {port.device}: {port.description}")
                else:
                    print("! Keine COM-Ports gefunden")
                return True
            except ImportError:
                print("! serial.tools.list_ports nicht verfügbar")
                return True
                
        else:
            print("✗ Falsches serial Modul gefunden")
            print(f"  Gefunden: {serial.__file__}")
            print(f"  Attribute: {dir(serial)}")
            return False
            
    except ImportError as e:
        print(f"✗ pyserial Import fehlgeschlagen: {e}")
        return False

def run_arduino_test():
    """Teste Arduino Interface"""
    print("\n=== Arduino Interface Test ===")
    
    # Entferne serial aus dem Modul-Cache
    if 'serial' in sys.modules:
        del sys.modules['serial']
    
    try:
        import serial
        
        class ArduinoInterface:
            def __init__(self, port="COM5", baudrate=9600, timeout=1):
                self.serial_connection = serial.Serial(port, baudrate, timeout=timeout)
                time.sleep(1)
                print(f"✓ Verbunden mit Arduino auf {port}")
                
            def set_speed(self, speed):
                if 0 <= speed <= 255:
                    command = f"{speed}\n"
                    self.serial_connection.write(command.encode())
                    print(f"→ Geschwindigkeit gesendet: {speed}")
                else:
                    raise ValueError("Geschwindigkeit muss zwischen 0 und 255 liegen.")
                    
            def close(self):
                self.serial_connection.close()
                print("✓ Arduino-Verbindung geschlossen")
        
        # Teste Arduino-Verbindung
        arduino = ArduinoInterface()
        arduino.set_speed(105)
        time.sleep(0.5)
        arduino.set_speed(150)
        time.sleep(0.5)
        arduino.close()
        
    except Exception as e:
        print(f"✗ Arduino-Test fehlgeschlagen: {e}")
        print("Das ist normal wenn kein Arduino angeschlossen ist.")

if __name__ == "__main__":
    # Teste pyserial Installation
    if test_pyserial_installation():
        # Wenn pyserial funktioniert, teste Arduino Interface
        run_arduino_test()
    else:
        print("\n! Bitte installieren Sie pyserial:")
        print("  pip install --user pyserial")
        print("  oder")
        print("  conda install pyserial")
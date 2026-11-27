"""Hardware: Bahnspannung über den Arduino einstellen.

Benutzung, aus dem Ordner src/:
  from arduino import connect, set_throttle
  connect()          # einmal beim Start, sucht den Arduino und wartet seinen Neustart ab
  set_throttle(50)   # 0 = Stillstand, 100 = Vollgas

Beim Beenden des Programms wird die Bahn auf 0 gesetzt und die Verbindung geschlossen, damit das
Auto nicht weiterfährt.

Gegenstück ist die Firmware carrera_pwm_controller.ino: Sie liest Zeilen "<0-100>\\n" und rechnet
sie in ein PWM-Signal 0-255 auf Pin 11 um.
"""

from __future__ import annotations

import atexit
import time

import serial
import serial.tools.list_ports

BAUDRATE = 9600
ARDUINO_RESET_SECONDS = 2  # Der Arduino startet beim Öffnen des Ports neu.
# USB-Hersteller-IDs. Die stehen auf Linux, Windows und macOS gleich in port.vid, anders als
# Portnamen (/dev/ttyACM0, COM3, /dev/cu.usbmodem1101).
ARDUINO_VENDOR_IDS = {
    0x2341,  # Arduino
    0x2A03,  # Arduino (arduino.org)
    0x1A86,  # CH340/CH341, USB-Chip vieler Nachbauten
}

serial_connection: serial.Serial | None = None


def find_arduino_port() -> str:
    """Sucht den Port des Arduino, sonst den einzigen angeschlossenen USB-Seriell-Port."""
    # Ports ohne Hersteller-ID sind keine USB-Geräte, z. B. /dev/ttyS0 oder Bluetooth auf macOS.
    usb_ports = [port for port in serial.tools.list_ports.comports() if port.vid is not None]

    for port in usb_ports:
        if port.vid in ARDUINO_VENDOR_IDS:
            print(f"Arduino gefunden auf: {port.device}")
            return port.device

    if len(usb_ports) == 1:
        print(f"Kein Arduino erkannt, nehme einzigen USB-Port: {usb_ports[0].device}")
        return usb_ports[0].device

    found_ports = ", ".join(port.device for port in usb_ports) or "keine"
    raise serial.SerialException(
        f"Kein Arduino gefunden (USB-Ports: {found_ports}). Port von Hand angeben: connect(\"COM3\")"
    )


def connect(port_name: str | None = None) -> None:
    """Öffnet die Verbindung. Ohne port_name wird der Arduino automatisch gesucht."""
    global serial_connection
    if port_name is None:
        port_name = find_arduino_port()

    try:
        serial_connection = serial.Serial(port_name, BAUDRATE, timeout=0.1, write_timeout=0)
    except serial.SerialException as error:
        raise serial.SerialException(
            f"{port_name} lässt sich nicht öffnen: {error}\n"
            "Ist der Port schon offen, z. B. im Serial Monitor der Arduino IDE?\n"
            "Linux: Der Benutzer muss in der Gruppe dialout sein:\n"
            "  sudo usermod -aG dialout $USER   (danach neu anmelden)"
        ) from error
    time.sleep(ARDUINO_RESET_SECONDS)
    serial_connection.reset_input_buffer()
    serial_connection.reset_output_buffer()


def set_throttle(throttle: int) -> None:
    """Setzt die Bahnspannung, 0 = Stillstand, 100 = Vollgas."""
    if not 0 <= throttle <= 100:
        raise ValueError(f"throttle muss zwischen 0 und 100 liegen, war {throttle}")
    if serial_connection is None:
        raise RuntimeError("Nicht mit dem Arduino verbunden, zuerst connect() aufrufen")

    try:
        serial_connection.write(f"{int(throttle)}\n".encode())
    except serial.SerialException as error:
        # Nicht abbrechen: Ein verlorener Befehl ist besser als eine hängende Steuerung.
        print(f"Fehler beim Senden an Arduino: {error}")


def close() -> None:
    """Stoppt das Auto und schließt die Verbindung."""
    global serial_connection
    if serial_connection is not None and serial_connection.is_open:
        set_throttle(0)
        serial_connection.flush()
        serial_connection.close()
    serial_connection = None


atexit.register(close)

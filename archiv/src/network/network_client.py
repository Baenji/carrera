"""
Network client for communication with Godot simulator.
Handles socket connection, JSON protocol, and Arduino signal control.
"""
import socket
import json
import re


class Network:
    """
    Network client for Godot simulator communication.
    Manages non-blocking socket I/O, JSON message protocol, and Arduino interface.
    """
    
    def __init__(self, ip, port, arduino_port=None, enable_arduino=True):
        """
        Initialize network client.
        
        Args:
            ip: Simulation server IP address
            port: Simulation server port
            arduino_port: Serial port for Arduino (optional)
            enable_arduino: Whether to initialize Arduino interface
        """
        self.ip = ip
        self.port = port
        self.socket = None
        self.connected = False
        self.enable_arduino = enable_arduino
        self.arduino = None
        self.receive_buffer = ""  # Persistent buffer for incomplete data
        self.should_block_buffer = False

        # Initialize Arduino interface if enabled
        if enable_arduino:
            try:
                from ..hardware.arduino import ArduinoInterface
                self.arduino = ArduinoInterface(port=arduino_port)
                print(f"Arduino interface initialized")
            except Exception as e:
                print(f"Failed to initialize Arduino: {e}")
                self.arduino = None

        # Connect to simulation
        self._connect()

    def block_buffer(self):
        self.should_block_buffer = True

    def unblock_buffer(self):
        self.should_block_buffer = False

    def _connect(self):
        """Establish connection to simulation server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.ip, self.port))
            # IMPORTANT: Set non-blocking, NO timeout!
            self.socket.setblocking(False)
            self.connected = True
            print(f"Connected to simulation at {self.ip}:{self.port}")
        except Exception as e:
            print(f"Failed to connect to simulation: {e}")
            self.connected = False
            self.socket = None

    def receive_once(self):
        """
        Receive data NON-BLOCKING and process all available JSON objects.
        
        Returns:
            dict: Last received JSON message or None
        """
        json_pattern = re.compile(r'{[^{}]*}')

        try:
            # Try to receive new data (does NOT block)
            data = self.socket.recv(4096)  # Larger buffer
            if not data:
                self.connected = False
                return None

            # Add new data to persistent buffer
            self.receive_buffer += data.decode('utf-8')

        except BlockingIOError:
            # No new data available - this is OK
            pass
        except Exception as e:
            print(f"[SOCKET RECV ERROR] Error receiving data: {e}")
            self.connected = False
            return None

        # Process ALL JSON objects in buffer
        last_json = None
        last_match_end = 0

        for match in json_pattern.finditer(self.receive_buffer):
            json_str = match.group()
            try:
                json_data = json.loads(json_str)
                if 'signal_rate_level' in json_data:
                    signal_rate = json_data['signal_rate_level']
                    # Import config here to avoid circular dependency with global
                    from ..config import last_signal_rate as prev_rate
                    if signal_rate != prev_rate:
                        print(f"Setting Arduino signal_rate to {signal_rate}")
                    if not self.should_block_buffer:
                        self._set_arduino_signal_rate(signal_rate)
                    # Update global (not ideal but maintains compatibility)
                    import sys
                    if 'src.config' in sys.modules:
                        sys.modules['src.config'].last_signal_rate = signal_rate
                last_json = json_data
                last_match_end = match.end()
            except json.JSONDecodeError:
                continue

        # Remove all processed data from buffer
        if last_match_end > 0:
            self.receive_buffer = self.receive_buffer[last_match_end:]

        # IMPORTANT: Limit buffer size to prevent memory issues and performance problems
        if len(self.receive_buffer) > 8192:
            print(f"⚠️ Buffer overflow detected ({len(self.receive_buffer)} bytes), clearing...")
            self.receive_buffer = ""

        return last_json

    def _set_arduino_signal_rate(self, signal_rate):
        """
        Set Arduino signal rate.
        
        Args:
            signal_rate: Signal rate value (0-100)
        """
        if not self.arduino:
            return
        try:
            # Clamp signal_rate to 0-100 range
            signal_rate = max(0, min(100, int(signal_rate)))
            self.arduino.set_signal_rate(signal_rate)
        except Exception as e:
            print(f"Error setting Arduino signal_rate: {e}")

    def send(self, data_dict):
        """
        Send data NON-BLOCKING to server.
        
        Args:
            data_dict: Dictionary to send as JSON
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.connected or self.socket is None:
            return False

        try:
            json_data = json.dumps(data_dict)
            message = json_data.encode('utf-8')
            # sendall can throw BlockingIOError on non-blocking sockets
            # when send buffer is full - this is OK, just skip
            self.socket.sendall(message)
            return True
        except BlockingIOError:
            # Send buffer is full, skip
            return False
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"Connection lost: {e}")
            self.connected = False
            return False
        except Exception as e:
            print(f"Error sending data: {e}")
            return False

    def close(self):
        """Close connection and cleanup."""
        self.connected = False
        
        # Close socket connection
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        print("Disconnected from simulation")

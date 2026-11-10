"""
Auto-reset controller for handling episode termination and car repositioning.
"""
import time
from src.config import AUTO_RESET_THROTTLES, AUTO_RESET_PROGRESS_THRESHOLD, AUTO_RESET_TIMEOUT, AUTO_RESET_WAIT_AT_START_DURATION, AUTO_RESET_GRACE_PERIOD

# Enable to see all throttle commands sent to Arduino
DEBUG_THROTTLE = True  # Temporarily enabled to diagnose issue


class AutoResetController:

    def __init__(self, network, crash_detector):
        self.network = network
        self.crash_detector = crash_detector
        
        # Reset state
        self.state = 'RUNNING'  # RUNNING, WAITING_PLACEMENT, RETURNING_TO_START, WAITING_AT_START, COMPLETE
        self.state_start_time = None
        self.wait_duration = AUTO_RESET_WAIT_AT_START_DURATION
        
        # Throttle tracking for continuous updates
        self.last_throttle_time = None
        self.current_throttle = 0
        self.throttle_update_interval = 0.05  # Send throttle every 50ms during reset
        
        # Arduino status checking
        self.last_status_check_time = None
        self.status_check_interval = 3.0  # Check Arduino status every 3 seconds

        # grace period tracking
        self.grace_period = float('inf')  # Time since last reset completed
        
    def update(self, car_pos, progress_percentage):
        # Check Arduino status periodically (every 3 seconds)
        self._check_arduino_status()
        
        if self.state == 'RUNNING':
            # Normal operation - no action needed
            # Update grace period timer
            self.grace_period += 1.0
            return self.state
            
        elif self.state == 'WAITING_PLACEMENT':

            # Set base speed throttle while waiting to escape
            self._send_throttle_continuous(AUTO_RESET_THROTTLES[0])

            # Waiting for manual placement back on track
            if car_pos is None:
                if self._check_timeout():
                    self._reset_to_running()
                return self.state

            # Car detected - check if manually placed
            if self.crash_detector.check_manual_placement(car_pos):
                print(f"Car detected at progress {progress_percentage:.1f}%")
                
                # Check if already at start position
                if AUTO_RESET_PROGRESS_THRESHOLD[0] < progress_percentage <= AUTO_RESET_PROGRESS_THRESHOLD[1]:
                    print("Already at start position!")
                    self._complete_reset()
                else:
                    print(f"Auto-positioning to start (currently at {progress_percentage:.1f}%)...")
                    self._start_return_to_start()
                    
        elif self.state == 'RETURNING_TO_START':
            # Actively driving car back to start position
            if car_pos is None:
                print("Lost car during auto-positioning - waiting for placement again")
                self._wait_for_placement()
                return self.state


            # Check if reached start position
            if AUTO_RESET_PROGRESS_THRESHOLD[0] < progress_percentage <= AUTO_RESET_PROGRESS_THRESHOLD[1]:
                print(f"Start position reached! (Progress: {progress_percentage:.1f}%)")
                self._start_wait_at_start()
                return self.state  # Return early after state transition
            elif progress_percentage > 97.0:
                # Car is near the end, keep going to wrap around to start
                print(f"Approaching start line (Progress: {progress_percentage:.1f}%)...")
            elif progress_percentage > 80.0:
                # Reduce speed on at end to avoid overshooting
                self._send_throttle_continuous(AUTO_RESET_THROTTLES[2])
            elif progress_percentage > 50.0:
                # Reduce speed on at end to avoid overshooting
                self._send_throttle_continuous(AUTO_RESET_THROTTLES[1])
            else:
                # Normal speed
                self._send_throttle_continuous(AUTO_RESET_THROTTLES[0])
                # Still moving towards start
                #n = 0.25
                #if int(time.time() * n) % n == 0:  # Print every 1/n seconds
                #    print(f"Auto-positioning: {progress_percentage:.1f}% -> 0%")
            
            # Check timeout
            if self._check_timeout():
                print("Auto-reset timeout during positioning")
                self._reset_to_running()
        
        elif self.state == 'WAITING_AT_START':
            # Non-blocking wait at start position
            # Keep sending 0 throttle to ensure car stays stopped
            self._send_throttle_continuous(0)
            
            if self._check_wait_complete():
                print(f"Wait at start complete ({self.wait_duration}s elapsed)")
                self._complete_reset()
            else:
                elapsed = time.time() - self.state_start_time if self.state_start_time else 0
                if DEBUG_THROTTLE and int(elapsed * 2) % 2 == 0:  # Print every 0.5s
                    print(f"Waiting at start: {elapsed:.1f}/{self.wait_duration}s")
                    
        return self.state
    
    def can_start_reset(self) -> bool:
        return self.grace_period > AUTO_RESET_GRACE_PERIOD
    
    def start_reset(self):
        
        if not self.can_start_reset():
            print(f"⚠️ Cannot start reset - in grace period ({self.grace_period:.1f}s elapsed)")
            

        if self.state != 'RUNNING':
            print(f"⚠️ Cannot start reset - already in state: {self.state}")
            return
        
        print("🔄 Starting reset sequence...")
        self.network.block_buffer() # Ignore model throttle during reset
        self.state = 'WAITING_PLACEMENT'
        self.state_start_time = time.time()

        # Notify crash detector
        self.crash_detector.start_reset()
        
    def _wait_for_placement(self):
        self.state = 'WAITING_PLACEMENT'
        self.state_start_time = time.time()
        self._apply_throttle(0)
        
    def _start_return_to_start(self):
        self.state = 'RETURNING_TO_START'
        self.state_start_time = time.time()
    
    def _start_wait_at_start(self):
        print(f"⏸️  Waiting at start for {self.wait_duration}s...")
        self.state = 'WAITING_AT_START'
        self.state_start_time = time.time()
        self._apply_throttle(0)
    
    def _check_wait_complete(self):
        """Check if wait duration at start is complete."""
        if self.state_start_time is None:
            return True
        elapsed = time.time() - self.state_start_time
        return elapsed >= self.wait_duration + 0.5

    def _complete_reset(self):
        print("🏁 Reset complete - returning control to model")
        
        # Notify crash detector first
        self.crash_detector.finish_reset()

        # Signal to Godot that reset is complete and model can take over
        if self.network:
            self.network.send({'reset_complete': True})
        
        # Return to running state (this stops sending throttle from auto_reset)
        self._reset_to_running()
        
    def _reset_to_running(self):
        print("[AUTO_RESET] Entering RUNNING state - model will control throttle")
        self.state = 'RUNNING'
        self.grace_period = 0.0
        self.state_start_time = None
        self.last_throttle_time = None
        self.current_throttle = 0
        self.network.unblock_buffer()
        # Don't send throttle here - let the model take over immediately
        
    def _apply_throttle(self, throttle=None):
        """Apply throttle once (for state transitions)"""
        if throttle is None:
            throttle = AUTO_RESET_THROTTLES[0]
        
        self.current_throttle = throttle
        self._send_throttle_now(throttle)
    
    def _send_throttle_continuous(self, throttle):
        self._send_throttle_now(throttle)
        return # debug use throttle now function always
        """Send throttle continuously with rate limiting to prevent Arduino from timing out"""
        now = time.time()
        
        # Always update current throttle
        self.current_throttle = throttle
        
        # Rate-limited sending
        if self.last_throttle_time is None or (now - self.last_throttle_time) >= self.throttle_update_interval:
            self._send_throttle_now(throttle)
            self.last_throttle_time = now
    
    def _send_throttle_now(self, throttle):
        """Actually send throttle command to Arduino"""
        # Send via network (which controls Arduino)
        if self.network and self.network.arduino:
            try:
                sent_bytes = self.network.arduino.set_signal_rate(throttle)
                #if DEBUG_THROTTLE:
                #    print(f"[THROTTLE] Sent {throttle} to Arduino (state: {self.state}) -> bytes written: {sent_bytes}")
            except Exception as e:
                print(f"⚠️ Error setting throttle: {e}")


            # check arduino status
            # self.network.arduino.get_status()
        else:
            if DEBUG_THROTTLE:
                print(f"⚠️ Warning: No Arduino connection available!")

    def _check_arduino_status(self):
        """Check Arduino status every 3 seconds"""
        now = time.time()
        
        # Only check if enough time has passed
        if self.last_status_check_time is None or (now - self.last_status_check_time) >= self.status_check_interval:
            if self.network and self.network.arduino:
                try:
                    status = self.network.arduino.get_status(timeout=0.5)
                    
                    if status.get('communication_ok'):
                        error_count = status.get('errors', 0)
                        
                        # Show any Serial messages (error logs, etc.)
                        serial_msgs = status.get('serial_messages', [])
                        if serial_msgs:
                            print(f"📝 Arduino Serial Output:")
                            for msg in serial_msgs:
                                if 'ERROR' in msg:
                                    print(f"   ❌ {msg}")
                                else:
                                    pass
                                    #print(f"   ℹ️  {msg}")
                        
                        # Display status
                        status_icon = "✅" if error_count == 0 else "⚠️"
                        print(f"{status_icon} Arduino: Speed={status.get('speed')}%, Uptime={status.get('uptime')}ms, Errors={error_count}")
                    else:
                        error_msg = status.get('error_message', 'Unknown error')
                        print(f"⚠️ Arduino communication failed: {error_msg}")
                        
                except Exception as e:
                    print(f"⚠️ Failed to check Arduino status: {e}")
            
            self.last_status_check_time = now

    def _check_timeout(self):
        if self.state_start_time is None:
            return False
            
        elapsed = time.time() - self.state_start_time
        return elapsed > AUTO_RESET_TIMEOUT
        
    def is_resetting(self):
        return self.state != 'RUNNING'
    
    def get_status(self):
        """Get detailed status for debugging"""
        return {
            'state': self.state,
            'current_throttle': self.current_throttle,
            'time_in_state': time.time() - self.state_start_time if self.state_start_time else 0,
            'last_throttle_sent': time.time() - self.last_throttle_time if self.last_throttle_time else None
        }

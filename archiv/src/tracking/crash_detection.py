import numpy as np
import time
from collections import deque

class CrashDetection:
    def __init__(self, network=None):
        self.network = network

        # Crash Parameter
        self.N_CRASH_FRAMES = 10 # Anzahl Frames, die als Crash gewertet sein müssen
        self.V_THRESHOLD = 30.0 # Grenze zwischen Crash / Nicht-Crash (Noise 50px)
        self.DEV_THRESHOLD = 100.0 # Grenze der Abweichung von der Predicteten Strecke
        self.CRASH_CUE_COUNT = 1 # Anzahl an cues die gegeben sein müssen, um als Crash zu zählen
        self.max_dev = 200.0 # for debuggung max deviation value
        self.v_buffer = deque(maxlen=5)

        self.prev_pos = None
        self.prev_v = 0
        self.last_time = None

        self.confirm_buffer = deque(maxlen=self.N_CRASH_FRAMES)
        
        # Reset state tracking
        self.is_resetting = False
        self.reset_start_time = None
        self.waiting_for_manual_placement = False

    def detect_crash(self, pos, area):
        now = time.time()

        self.dev_test = 0

        if self.last_time is None:
            self.last_time = now
            self.prev_pos = pos
            return False

        # Geschwindigkeit berechnen und mit Threshhold abgleichen
        time_delta = now - self.last_time
        dist = np.linalg.norm(np.array(pos) - np.array(self.prev_pos))
        v = dist / time_delta

        self.v_buffer.append(v)
        v = np.median(self.v_buffer)

        predicted = np.array(self.prev_pos) + self.prev_v * time_delta
        deviation = np.linalg.norm(pos - predicted)

        cue_v = v <= self.V_THRESHOLD
        cue_dev = deviation > self.max_dev
        cue_area = area is None

        crash_frame = sum([cue_v, cue_dev, cue_area]) >= self.CRASH_CUE_COUNT

        self.confirm_buffer.append(crash_frame) # Füllt Confirm Buffer mit 1/0 je nach Crash

        crash = sum(self.confirm_buffer) >= self.N_CRASH_FRAMES # Wenn Confirm Buffer voll mit Crash Frames ist -> Crash detected

        if (self.max_dev < deviation) and (deviation < self.DEV_THRESHOLD):
            self.max_dev = deviation

        #print(  f"v: {v:.2f} | dev: {deviation:.2f} | max_dev: {self.max_dev:.2f} | ")

        if crash:
            self.confirm_buffer.clear()
            # Debug output
            print(f"CRASH DETECTED at pos {pos} | v: {v:.3f} | dev: {deviation:.2f} | max_dev: {self.max_dev:.2f} | cues: v({cue_v}), dev({cue_dev}), area({cue_area})")

        self.prev_v = v
        self.prev_pos = pos
        self.last_time = now
        return crash
    
    def start_reset(self):
        self.is_resetting = True
        self.waiting_for_manual_placement = True
        self.reset_start_time = time.time()

        print("Starting reset...")
        
    def check_manual_placement(self, current_pos):
        if not self.waiting_for_manual_placement:
            return False
        
        # Check if position has changed significantly (manual placement)
        if self.prev_pos is not None:
            dist = np.linalg.norm(np.array(current_pos) - np.array(self.prev_pos))
            # If car moved more than 50 pixels, assume manual placement
            if dist > 50:
                self.waiting_for_manual_placement = False
                print("Manual placement detected - starting auto-positioning...")
                return True
        
        return False
    
    def finish_reset(self):
        self.is_resetting = False
        self.waiting_for_manual_placement = False
        self.reset_start_time = None
        self.confirm_buffer.clear()
        print("RESET COMPLETE - EPISODE RESTARTING")
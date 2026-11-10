"""
Main application for Carrera object tracking.
"""
import traceback
import cv2
import time
import numpy as np
from pupil_apriltags import Detector

from .config import (
    SIMULATION_IP, SIMULATION_PORT, MAIN_WINDOW_NAME, 
    STABLE_TAG_FRAMES, TRACK_YELLOW, TRACK_VISUALIZATION_ENABLED,
    SHOW_TRACK_GRAPH, SIMULATION_CAR_SAMPLING_RATE, DISPLAY_WINDOW_SIZE,
    AUTO_RESET_ENABLED
)
from .camera import CarTracker, initialize_camera
from .network import Network
from .tracking import TrackRecognizer
from src.tracking.auto_reset import AutoResetController
from src.tracking.crash_detection import CrashDetection


class QuickObjectTrackingApp:
    """Main application for object tracking and simulation integration."""
    
    def __init__(self):
        """Initialize application components."""
        # Initialize camera
        self.cap = initialize_camera()
        if self.cap is None:
            exit(1)
        
        # Initialize components
        self.car_path = []
        self.track_mapped = False
        self.track_order_result = None
        self.track_order_tags = None
        self.show_track_graph = SHOW_TRACK_GRAPH
        self.tracker = CarTracker()
        self.network = Network(SIMULATION_IP, SIMULATION_PORT)
        self.recognizer = TrackRecognizer(self.network)
        self.last_progress_send_time = 0.0
        
        # Initialize crash detection and auto-reset
        self.crash_detector = CrashDetection(network=self.network)
        self.auto_reset = AutoResetController(self.network, self.crash_detector) if AUTO_RESET_ENABLED else None
        self.last_car_area = None
        
        # Initialize AprilTag detector
        # With higher resolution (FHD/4K), we can use better quality settings
        self.apriltag_detector = Detector(
            families='tag16h5',
            nthreads=1,  # Use 2 threads for better performance with high-res images
            quad_decimate=1.0,  # No decimation for full resolution quality
            quad_sigma=0.0,  # No blur - high res images have better quality
            refine_edges=1,
            decode_sharpening=0.25,
            debug=0
        )

    def run(self):
        """Main application loop."""
        failed_frame_count = 0
        max_failed_frames = 10
        frame_count = 0
        apriltag_detection_interval = 60  # Detect AprilTags every N frames
        yellow_dot_detection_interval = 20
        apriltag_cache = []
        yellow_centers_cache = []

        while True:
            frame_count += 1
            ret, frame = self.cap.read()
            
            if not ret:
                failed_frame_count += 1
                print(f"⚠️ Frame read failed ({failed_frame_count}/{max_failed_frames})")

                if failed_frame_count >= max_failed_frames:
                    print("❌ Too many failed frames, exiting...")
                    break

                time.sleep(0.05)
                continue

            # Frame successfully read - reset counter
            failed_frame_count = 0

            try:



                # Anti-reflection mask (placeholder for now)
                anti_reflection_mask = np.ones_like(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)) * 255
                
                # Detect car position
                car_pos, mask = self.tracker.find_car(frame)

                # debug
                stable_apriltags = apriltag_cache

                if not self.track_mapped:
                    # Detect yellow reference dots
                    should_track = TRACK_YELLOW and (frame_count % yellow_dot_detection_interval == 0)
                    yellow_centers, _ = (self.tracker.find_yellow_dot(frame) if should_track else (yellow_centers_cache, None))

                    if yellow_centers_cache != yellow_centers:
                        yellow_centers_cache = yellow_centers

                    # AprilTag detection (only every N frames for performance)
                    if self.apriltag_detector is not None and (not self.track_mapped or frame_count % apriltag_detection_interval == 0):
                        apriltags_detected = self.recognizer.detect_apriltags(frame, self.apriltag_detector)
                        stable_apriltags = self.recognizer.update_tag_history(apriltags_detected, STABLE_TAG_FRAMES)

                        apriltag_cache = stable_apriltags

                if stable_apriltags:
                    frame = self.recognizer.draw_apriltags(frame, stable_apriltags)

                    # Map track order if not yet mapped
                    if not self.track_mapped and yellow_centers:
                        vis_frame = frame if TRACK_VISUALIZATION_ENABLED else None
                        vis_mask = mask if TRACK_VISUALIZATION_ENABLED else None
                        result = self.recognizer.map_track_order(stable_apriltags, yellow_centers, vis_frame, vis_mask)

                        if result:
                            self.track_order_result, self.track_order_tags = result
                            self.recognizer.send_to_simulation(self.track_order_result)
                            self.track_mapped = True
                            print("\n" + "="*60)
                            print("TRACK ORDER MAPPED SUCCESSFULLY!")
                            print("="*60)
                            for idx, piece in enumerate(self.track_order_result, 1):
                                print(f"{idx}. {piece}")
                            print("="*60 + "\n")

                # Apply anti-reflection mask
                mask = cv2.bitwise_and(mask, anti_reflection_mask)
                
                # Store car area for crash detection
                if mask is not None:
                    self.last_car_area = cv2.countNonZero(mask)
                
                # Crash detection (only when track is mapped and not already resetting)
                current_progress = 0.0
                if self.track_mapped and AUTO_RESET_ENABLED:

                    if not car_pos:
                        car_pos = self.crash_detector.prev_pos if self.crash_detector.prev_pos is not None else (0, 0)

                    current_progress = self.recognizer.track_graph.get_progress_percentage(car_pos)
                    
                    # Only detect crashes when not in reset mode
                    if not self.auto_reset.is_resetting():
                        crash_detected = self.crash_detector.detect_crash(car_pos, self.last_car_area)
                        
                        if crash_detected and self.auto_reset.can_start_reset():
                            print("\n🚨 CRASH/OFF-TRACK DETECTED!")
                            self.network.send({'crash_detected': True})
                            self.auto_reset.start_reset()
                    
                    # Update auto-reset state machine
                    reset_state = self.auto_reset.update(car_pos, current_progress)
                    
                    # Draw reset status on frame
                    if self.auto_reset.is_resetting():
                        status_text = f"RESET MODE: {reset_state}"
                        cv2.putText(frame, status_text, (10, frame.shape[0] - 20),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                # Draw car position
                if car_pos:
                    cv2.circle(frame, car_pos, 8, (0, 0, 255), -1)
                
                # Draw yellow dots
                if TRACK_YELLOW:
                    for yc in yellow_centers:
                        cv2.circle(frame, yc, 6, (0, 255, 255), -1)

                # Calculate and display progress percentage
                if self.track_mapped and car_pos and self.show_track_graph:
                    # Use progress calculated earlier or calculate now
                    if current_progress == 0.0:
                        progress = self.recognizer.track_graph.get_progress_percentage(car_pos)
                    else:
                        progress = current_progress

                    # Send to simulation with rate limiting (only when not resetting)
                    if not (AUTO_RESET_ENABLED and self.auto_reset.is_resetting()):
                        current_time = time.time()
                        time_since_last_send = current_time - self.last_progress_send_time
                        min_interval = 1.0 / SIMULATION_CAR_SAMPLING_RATE if SIMULATION_CAR_SAMPLING_RATE > 0 else 0

                        if time_since_last_send >= min_interval:
                            self.recognizer.track_graph.send_to_simulation(progress)
                            self.last_progress_send_time = current_time

                    # Draw progress bar
                    bar_width = 300
                    bar_height = 30
                    bar_x = 10
                    bar_y = 10

                    # Background
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (50, 50, 50), -1)
                    # Progress fill
                    fill_width = int((progress / 100.0) * bar_width)
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_width, bar_y + bar_height), (0, 255, 0), -1)
                    # Border
                    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height), (255, 255, 255), 2)

                    # Progress text
                    progress_text = f"Progress: {progress:.1f}%"
                    cv2.putText(frame, progress_text, (bar_x + 10, bar_y + 20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    # Draw track graph nodes
                    if self.recognizer.track_graph.nodes:
                        for i, node in enumerate(self.recognizer.track_graph.nodes):
                            cv2.circle(frame, node, 4, (255, 0, 255), -1)
                            # Draw lines between nodes
                            next_i = (i + 1) % len(self.recognizer.track_graph.nodes)
                            next_node = self.recognizer.track_graph.nodes[next_i]
                            cv2.line(frame, node, next_node, (255, 0, 255), 1)

                # Poll network for incoming data
                net_data = self.network.receive_once()
                if net_data is not None:
                    # Handle received data if needed
                    pass

                # Resize frame for display if configured
                display_frame = frame
                if DISPLAY_WINDOW_SIZE is not None:
                    display_frame = cv2.resize(frame, DISPLAY_WINDOW_SIZE, interpolation=cv2.INTER_LINEAR)

                # Display frame
                cv2.imshow(MAIN_WINDOW_NAME, display_frame)

            except Exception as e:
                print(f"⚠️ Error processing frame: {e}")
                traceback.print_exc()
                # Show window with original frame if possible
                try:
                    display_frame = frame
                    if DISPLAY_WINDOW_SIZE is not None:
                        display_frame = cv2.resize(frame, DISPLAY_WINDOW_SIZE, interpolation=cv2.INTER_LINEAR)
                    cv2.imshow(MAIN_WINDOW_NAME, display_frame)
                except:
                    pass

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC key
                break
            elif key == ord('g') or key == ord('G'):  # Toggle track graph
                self.show_track_graph = not self.show_track_graph
                state = "ON" if self.show_track_graph else "OFF"
                print(f"Track graph visualization: {state}")

        # Cleanup
        self.cap.release()
        cv2.destroyAllWindows()
        self.network.close()


def main():
    """Entry point for the application."""
    app = QuickObjectTrackingApp()
    app.run()


if __name__ == "__main__":
    main()

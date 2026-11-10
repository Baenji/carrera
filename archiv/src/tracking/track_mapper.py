"""
Track mapper - complex algorithm for determining track order from AprilTags.
Includes inline visualization of the mapping process.
"""
import cv2
import numpy as np
from .track_graph import TrackGraph
from .apriltag_detector import detect_apriltags, draw_apriltags
from ..config import (
    TAG_MAP, TRACK_VISUALIZATION_ENABLED, TRACK_VISUALIZATION_SIGNAL_RATE_FACTOR,
    MAIN_WINDOW_NAME, NAME_TO_PART, PARTS
)


class TrackRecognizer:
    """Recognizes track layout from AprilTag detections."""
    
    def __init__(self, network=None):
        """
        Initialize track recognizer.
        
        Args:
            network: Network client for sending track order
        """
        self.tag_detection_history = {}
        self.track_graph = TrackGraph(network)
        self.network = network

    def detect_apriltags(self, frame, detector):
        """Detect AprilTags in frame (wrapper for compatibility)."""
        return detect_apriltags(frame, detector)

    def draw_apriltags(self, frame, tags_info):
        """Draw AprilTags on frame (wrapper for compatibility)."""
        return draw_apriltags(frame, tags_info)

    def update_tag_history(self, detected_tags, threshold):
        """
        Filter tags based on detection stability.
        
        Args:
            detected_tags: List of currently detected tags
            threshold: Minimum consecutive detections required
            
        Returns:
            list: Stable tags that meet threshold
        """
        current_ids = set(tag['id'] for tag in detected_tags)
        
        for tag_id in current_ids:
            self.tag_detection_history[tag_id] = self.tag_detection_history.get(tag_id, 0) + 1
        
        for tag_id in list(self.tag_detection_history.keys()):
            if tag_id not in current_ids:
                self.tag_detection_history[tag_id] -= 1
                if self.tag_detection_history[tag_id] <= 0:
                    del self.tag_detection_history[tag_id]
        
        stable_ids = [tag_id for tag_id, count in self.tag_detection_history.items() if count >= threshold]
        stable_tags = [tag for tag in detected_tags if tag['id'] in stable_ids]
        
        return stable_tags

    @staticmethod
    def determine_turn_direction(prev_pos, current_pos, next_pos):
        """
        Determine turn direction (left/right) using cross product.
        
        Args:
            prev_pos: Previous position (x, y)
            current_pos: Current position (x, y)
            next_pos: Next position (x, y)
            
        Returns:
            str: 'Rechts', 'Links', or None if straight
        """
        vec1 = np.array(current_pos) - np.array(prev_pos)
        vec2 = np.array(next_pos) - np.array(current_pos)
        vec1_norm = np.linalg.norm(vec1)
        vec2_norm = np.linalg.norm(vec2)
        
        if vec1_norm < 1 or vec2_norm < 1:
            return None
        
        vec1 = vec1 / vec1_norm
        vec2 = vec2 / vec2_norm
        cross_product = vec1[0] * vec2[1] - vec1[1] * vec2[0]
        
        if abs(cross_product) > 0.25:
            return 'Rechts' if cross_product > 0 else 'Links'
        
        return None

    def map_track_order(self, tags_info, yellow_centers, visualize_frame=None, visualize_mask=None):
        """
        Map track order from AprilTags using complex pathfinding algorithm.
        Includes inline visualization of the mapping process.
        
        Args:
            tags_info: List of detected tag info dictionaries
            yellow_centers: List of yellow dot positions for orientation
            visualize_frame: Optional frame for visualization
            visualize_mask: Optional mask for visualization
            
        Returns:
            tuple: (track_names, track_order_tags) or None if mapping failed
        """
        if not tags_info:
            return None

        # Find start tag (ID 1)
        start_tag = None
        for tag in tags_info:
            if tag['id'] == 1:
                start_tag = tag
                break

        if not start_tag:
            return None

        if not yellow_centers:
            return None

        # Find nearest yellow dot to determine initial direction
        start_pos = np.array(start_tag['center'])
        nearest_yellow = min(yellow_centers, key=lambda y: np.linalg.norm(np.array(y) - start_pos))
        yellow_vector = np.array(nearest_yellow) - start_pos

        # Initialize track order
        track_order = [start_tag]
        visited_positions = {tuple(start_tag['center'])}
        current_pos = start_pos
        previous_pos = start_pos - yellow_vector

        max_iterations = 60
        iteration = 0

        # Visualization helper function
        def show_vis_img(vis_img, wait_time):
            """Show visualization with adjustable signal rate."""
            if TRACK_VISUALIZATION_ENABLED:
                signal_rate = max(0.01, TRACK_VISUALIZATION_SIGNAL_RATE_FACTOR)
                cv2.imshow(MAIN_WINDOW_NAME, vis_img)
                wait_ms = min(1000, int(wait_time / signal_rate))
                cv2.waitKey(wait_ms)

        # Main pathfinding loop
        while iteration < max_iterations:
            iteration += 1
            candidate_tags = [tag for tag in tags_info if tuple(tag['center']) not in visited_positions]
            
            if not candidate_tags:
                break

            # Visualization of current state
            if visualize_frame is not None:
                vis_img = visualize_frame.copy()

                for tag in tags_info:
                    color = (100, 100, 100)
                    if tuple(tag['center']) in visited_positions:
                        color = (0, 255, 0)
                    elif tag in candidate_tags:
                        color = (0, 165, 255)
                    cv2.circle(vis_img, tuple(map(int, tag['center'])), 15, color, 3)
                    cv2.putText(vis_img, f"{tag['id']}",
                               (int(tag['center'][0]) - 10, int(tag['center'][1]) + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                cv2.circle(vis_img, tuple(map(int, current_pos[:2])), 25, (255, 0, 255), 3)
                cv2.putText(vis_img, "CURRENT",
                           (int(current_pos[0]) - 40, int(current_pos[1]) - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

                cv2.circle(vis_img, tuple(map(int, nearest_yellow)), 10, (0, 255, 255), -1)
                cv2.putText(vis_img, "YELLOW",
                           (int(nearest_yellow[0]) - 30, int(nearest_yellow[1]) - 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                for i in range(1, len(track_order)):
                    prev_tag = track_order[i-1]
                    curr_tag = track_order[i]
                    cv2.line(vis_img, tuple(map(int, prev_tag['center'])), tuple(map(int, curr_tag['center'])), (0, 255, 0), 2)
                    cv2.arrowedLine(vis_img, tuple(map(int, prev_tag['center'])), tuple(map(int, curr_tag['center'])), (0, 255, 0), 2)

                show_vis_img(vis_img, 1000)

            best_tag = None
            best_distance = float('inf')
            backwards_vector = previous_pos - current_pos
            backwards_distance = np.linalg.norm(backwards_vector)

            # Visualization of backwards direction
            if visualize_frame is not None:
                vis_img = visualize_frame.copy()

                for tag in tags_info:
                    color = (100, 100, 100)
                    if tuple(tag['center']) in visited_positions:
                        color = (0, 255, 0)
                    elif tag in candidate_tags:
                        color = (0, 165, 255)
                    cv2.circle(vis_img, tuple(map(int, tag['center'])), 15, color, 3)
                    cv2.putText(vis_img, f"{tag['id']}",
                               (int(tag['center'][0]) - 10, int(tag['center'][1]) + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                if backwards_distance > 10:
                    backwards_endpoint = current_pos.astype(int) + (backwards_vector / backwards_distance * 100).astype(int)
                    backwards_endpoint = tuple(map(int, backwards_endpoint[:2]))
                    cv2.arrowedLine(vis_img, tuple(map(int, current_pos[:2])), backwards_endpoint, (0, 0, 255), 2, tipLength=0.2)
                    cv2.putText(vis_img, "BACKWARDS",
                               (backwards_endpoint[0] + 10, backwards_endpoint[1]),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                cv2.circle(vis_img, tuple(map(int, current_pos[:2])), 25, (255, 0, 255), 3)
                cv2.putText(vis_img, "CURRENT",
                           (int(current_pos[0]) - 40, int(current_pos[1]) - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

                show_vis_img(vis_img, 800)

            # Select best next tag (reject backwards movement)
            rejected_tags = []
            for tag in candidate_tags:
                tag_pos = np.array(tag['center'])
                to_tag_vector = tag_pos - current_pos
                distance = np.linalg.norm(to_tag_vector)

                if distance < 1:
                    continue

                is_backwards = False
                if backwards_distance > 10:
                    backwards_normalized = backwards_vector / backwards_distance
                    to_tag_normalized = to_tag_vector / distance

                    alignment_with_backwards = np.dot(to_tag_normalized, backwards_normalized)
                    if alignment_with_backwards > 0.0:
                        is_backwards = True
                        rejected_tags.append((tag, alignment_with_backwards))
                        continue

                if distance < best_distance:
                    best_distance = distance
                    best_tag = tag

            # Visualization of rejected tags
            if visualize_frame is not None and rejected_tags:
                vis_img = visualize_frame.copy()

                for tag in tags_info:
                    color = (100, 100, 100)
                    if tuple(tag['center']) in visited_positions:
                        color = (0, 255, 0)
                    cv2.circle(vis_img, tuple(map(int, tag['center'])), 15, color, 3)
                    cv2.putText(vis_img, f"{tag['id']}",
                               (int(tag['center'][0]) - 10, int(tag['center'][1]) + 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

                for rejected_tag, alignment in rejected_tags:
                    cv2.circle(vis_img, tuple(map(int, rejected_tag['center'])), 15, (0, 0, 255), 3)
                    cv2.line(vis_img,
                            (int(rejected_tag['center'][0]) - 10, int(rejected_tag['center'][1]) - 10),
                            (int(rejected_tag['center'][0]) + 10, int(rejected_tag['center'][1]) + 10),
                            (0, 0, 255), 2)
                    cv2.line(vis_img,
                            (int(rejected_tag['center'][0]) + 10, int(rejected_tag['center'][1]) - 10),
                            (int(rejected_tag['center'][0]) - 10, int(rejected_tag['center'][1]) + 10),
                            (0, 0, 255), 2)
                    cv2.putText(vis_img, f"REJECTED: {alignment:.2f}",
                               (int(rejected_tag['center'][0]) - 50, int(rejected_tag['center'][1]) + 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

                show_vis_img(vis_img, 1000)

            if best_tag is None:
                break

            # Visualization of chosen next tag
            if visualize_frame is not None and best_tag is not None:
                vis_img = visualize_frame.copy()

                for tag in tags_info:
                    if tuple(tag['center']) in visited_positions:
                        cv2.circle(vis_img, tuple(map(int, tag['center'])), 15, (0, 255, 0), 3)
                        cv2.putText(vis_img, f"{tag['id']}",
                                   (int(tag['center'][0]) - 10, int(tag['center'][1]) + 5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                cv2.circle(vis_img, tuple(map(int, best_tag['center'])), 20, (255, 255, 0), 4)
                cv2.putText(vis_img, f"NEXT: {best_tag['id']}",
                           (int(best_tag['center'][0]) - 40, int(best_tag['center'][1]) - 25),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.arrowedLine(vis_img, tuple(map(int, current_pos[:2])), tuple(map(int, best_tag['center'])), (255, 255, 0), 3, tipLength=0.3)

                show_vis_img(vis_img, 1500)

            # Check if loop completed
            if best_tag['id'] == 1 and len(track_order) > 1:
                print("Track loop completed!")
                break

            track_order.append(best_tag)
            visited_positions.add(tuple(best_tag['center']))

            previous_pos = current_pos
            current_pos = np.array(best_tag['center'])

        # Determine track names and curve directions
        track_names = []
        for i, tag in enumerate(track_order):
            base_name = TAG_MAP.get(tag['id'], f"Unknown ({tag['id']})")

            if tag['id'] == 5 and len(track_order) >= 3:
                prev_idx = (i - 1) % len(track_order)
                next_idx = (i + 1) % len(track_order)

                prev_pos = track_order[prev_idx]['center']
                current_pos = tag['center']
                next_pos = track_order[next_idx]['center']

                turn_direction = self.determine_turn_direction(prev_pos, current_pos, next_pos)

                if turn_direction:
                    base_name = f"Curve {turn_direction}"

            track_names.append(base_name)

        # Build track graph for progress tracking
        self.track_graph.build_from_track_order(track_order)

        return track_names, track_order

    def send_to_simulation(self, track_order):
        """
        Send track order to simulation as numeric PARTS enum values.
        
        Args:
            track_order: List of track piece names
        """
        # Convert track names to PARTS enum numbers
        track_order_numbers = []
        for name in track_order:
            # Curve without direction as NONE
            if name.startswith('Curve') and name not in NAME_TO_PART:
                track_order_numbers.append(PARTS['NONE'])
            else:
                track_order_numbers.append(NAME_TO_PART.get(name, PARTS['NONE']))

        # Send to simulation
        # TODO: REMOVE HARDCODED TESTING VALUES
        track_order_numbers = [1, 4, 5, 5, 6, 4, 6, 5, 5, 4, 2, 5, 4, 4, 4, 5]
        if self.network and self.network.connected:
            success = self.network.send({'track_order': track_order_numbers})
            if success:
                print(f"Track order sent")
            return

        if self.network and self.network.connected:
            success = self.network.send({'track_order': track_order_numbers})
            if success:
                print(f"Track order sent: {track_order_numbers}")
        else:
            print("Cannot send track order: Not connected to simulation")

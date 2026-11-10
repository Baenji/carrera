"""
Track graph for progress calculation along the circuit.
"""
import numpy as np


class TrackGraph:
    """Represents the track as a graph of connected segments."""
    
    def __init__(self, network=None):
        """
        Initialize track graph.
        
        Args:
            network: Network client for sending progress updates
        """
        self.nodes = []
        self.total_distance = 0.0
        self.segment_distances = []
        self.cumulative_distances = []
        self.network = network

    def build_from_track_order(self, track_order_tags):
        """
        Build graph from ordered AprilTags.
        
        Args:
            track_order_tags: List of tag dictionaries with 'center' key
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not track_order_tags:
            return False

        self.nodes = [tag['center'] for tag in track_order_tags]
        self.segment_distances = []
        self.cumulative_distances = [0.0]

        for i in range(len(self.nodes)):
            next_i = (i + 1) % len(self.nodes)
            dist = np.linalg.norm(np.array(self.nodes[next_i]) - np.array(self.nodes[i]))
            self.segment_distances.append(dist)
            self.cumulative_distances.append(self.cumulative_distances[-1] + dist)

        self.total_distance = self.cumulative_distances[-1]
        return True

    def get_progress_percentage(self, car_position):
        """
        Calculate car's progress around the track as percentage.
        
        Args:
            car_position: (x, y) tuple of car position
            
        Returns:
            float: Progress percentage (0-100)
        """
        if not self.nodes or car_position is None:
            return 0.0

        car_pos = np.array(car_position)
        min_distance = float('inf')
        closest_segment_idx = 0
        projection_ratio = 0.0

        # Find closest segment and projection point
        for i in range(len(self.nodes)):
            next_i = (i + 1) % len(self.nodes)
            p1 = np.array(self.nodes[i])
            p2 = np.array(self.nodes[next_i])

            # Vector from p1 to p2
            segment_vec = p2 - p1
            segment_length = np.linalg.norm(segment_vec)

            if segment_length < 1e-6:
                continue

            # Project car position onto segment
            t = np.dot(car_pos - p1, segment_vec) / (segment_length ** 2)
            t = np.clip(t, 0, 1)  # Clamp to segment bounds

            # Closest point on segment
            projection = p1 + t * segment_vec
            distance = np.linalg.norm(car_pos - projection)

            if distance < min_distance:
                min_distance = distance
                closest_segment_idx = i
                projection_ratio = t

        # Calculate progress distance
        progress_distance = self.cumulative_distances[closest_segment_idx]
        progress_distance += projection_ratio * self.segment_distances[closest_segment_idx]

        # Calculate percentage
        percentage = (progress_distance / self.total_distance) * 100.0 if self.total_distance > 0 else 0.0
        return percentage

    def send_to_simulation(self, percentage):
        """
        Send progress percentage to simulation.
        
        Args:
            percentage: Progress percentage (0-100)
        """
        if self.network and self.network.connected:
            self.network.send({'progress': percentage / 100})

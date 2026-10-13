"""
Color-based car detection using HSV color space.
"""
import cv2
import numpy as np
from ..config import GREEN_LOW, GREEN_HIGH, YELLOW_LOW, YELLOW_HIGH


class CarTracker:
    """Tracks car position using green color detection."""
    
    @staticmethod
    def find_car(frame):
        """
        Detect car position using green color detection.
        
        Args:
            frame: BGR image frame
            
        Returns:
            tuple: (position, mask) where position is (x, y) or None, mask is binary image
        """
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (30, 30))

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, GREEN_LOW, GREEN_HIGH)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, mask
        
        largest = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest)
        
        if M["m00"] == 0:
            return None, mask

        cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
        return (cx, cy), mask

    @staticmethod
    def find_yellow_dot(frame):
        """
        Detect yellow reference dots for track orientation.
        
        Args:
            frame: BGR image frame
            
        Returns:
            tuple: (dot_centers, mask) where dot_centers is list of (x, y) positions
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, YELLOW_LOW, YELLOW_HIGH)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, np.ones((2, 2), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        dot_centers = []
        for cnt in contours:
            if cv2.contourArea(cnt) > 4:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                    dot_centers.append((cx, cy))
        
        return dot_centers, mask

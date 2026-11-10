"""
AprilTag detection utilities.
"""
import cv2


def detect_apriltags(frame, detector):
    """
    Detect AprilTags in frame.
    
    Args:
        frame: BGR image frame
        detector: pupil_apriltags Detector instance
        
    Returns:
        list: List of tag info dictionaries
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections = detector.detect(gray)
    tags_info = []

    for detection in detections:
        center = detection.center
        cx, cy = int(center[0]), int(center[1])
        corners = detection.corners.astype(int)
        tags_info.append({
            'id': detection.tag_id,
            'center': (cx, cy),
            'corners': corners,
            'hamming': detection.hamming,
            'decision_margin': detection.decision_margin
        })
    
    return tags_info


def draw_apriltags(frame, tags_info):
    """
    Draw AprilTag detections on frame.
    
    Args:
        frame: BGR image frame (modified in-place)
        tags_info: List of tag info dictionaries
        
    Returns:
        frame: Frame with drawn tags
    """
    for tag in tags_info:
        corners = tag['corners']
        for i in range(4):
            pt1 = tuple(corners[i])
            pt2 = tuple(corners[(i + 1) % 4])
            cv2.line(frame, pt1, pt2, (0, 255, 0), 2)
        
        center = tag['center']
        cv2.circle(frame, center, 5, (255, 255, 255), -1)
        cv2.putText(frame, f"ID: {tag['id']}",
                    (center[0] - 20, center[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    return frame

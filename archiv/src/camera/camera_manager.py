"""
Platform-specific camera initialization.
"""
import cv2
import platform
import time
from ..config import CAM_INDEX, CAMERA_RESOLUTION, RESOLUTIONS


def initialize_camera():
    """
    Initialize camera with platform-specific backends.
    
    Returns:
        cv2.VideoCapture: Initialized camera object or None if failed
    """
    system = platform.system()
    camera_found = False
    cap = None
    
    # Get resolution
    if isinstance(CAMERA_RESOLUTION, str):
        width, height = RESOLUTIONS.get(CAMERA_RESOLUTION, RESOLUTIONS['FHD'])
    else:
        width, height = CAMERA_RESOLUTION

    print(f"Initializing camera with resolution: {width}x{height}...")

    if system == 'Windows':
        cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Set resolution before reading frames
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if cap.isOpened():
            for attempt in range(3):
                ret, frame = cap.read()
                if ret:
                    cap.set(cv2.CAP_PROP_BRIGHTNESS, 1000.0)
                    cap.set(cv2.CAP_PROP_EXPOSURE, -6)
                    cap.set(cv2.CAP_PROP_GAIN, 1.0)
                    camera_found = True

                    # Verify actual resolution
                    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"Camera initialized successfully on attempt {attempt+1}")
                    print(f"Requested: {width}x{height}, Actual: {actual_width}x{actual_height}")

                    if actual_width != width or actual_height != height:
                        print(f"⚠️ Warning: Camera does not support {width}x{height}, using {actual_width}x{actual_height}")

                    break
                time.sleep(0.1)

        if not camera_found and cap:
            cap.release()
            cap = None

    elif system == 'Darwin':  # macOS
        cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_AVFOUNDATION)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Set resolution before reading frames
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if cap.isOpened():
            for attempt in range(3):
                ret, frame = cap.read()
                if ret:
                    cap.set(cv2.CAP_PROP_SETTINGS, 1)
                    camera_found = True

                    # Verify actual resolution
                    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"Camera initialized successfully on attempt {attempt+1}")
                    print(f"Requested: {width}x{height}, Actual: {actual_width}x{actual_height}")

                    if actual_width != width or actual_height != height:
                        print(f"⚠️ Warning: Camera does not support {width}x{height}, using {actual_width}x{actual_height}")

                    break
                time.sleep(0.1)

        if not camera_found and cap:
            cap.release()
            cap = None
    
    else:  # Linux and others
        cap = cv2.VideoCapture(CAM_INDEX)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Set resolution before reading frames
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if cap.isOpened():
            for attempt in range(3):
                ret, frame = cap.read()
                if ret:
                    camera_found = True

                    # Verify actual resolution
                    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"Camera initialized successfully on attempt {attempt+1}")
                    print(f"Requested: {width}x{height}, Actual: {actual_width}x{actual_height}")

                    if actual_width != width or actual_height != height:
                        print(f"⚠️ Warning: Camera does not support {width}x{height}, using {actual_width}x{actual_height}")

                    break
                time.sleep(0.1)

        if not camera_found and cap:
            cap.release()
            cap = None

    if not camera_found:
        print("❌ Keine Kamera gefunden! Bitte prüfen Sie die Verbindung.")
        return None
    
    return cap

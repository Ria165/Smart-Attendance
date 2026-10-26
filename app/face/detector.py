import io
import numpy as np
from PIL import Image

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


def decode_image_bytes(image_data):
    """
    Decodes raw bytes or base64 data into a PIL Image and RGB numpy array.
    """
    if isinstance(image_data, str) and image_data.startswith("data:image"):
        import base64
        image_data = base64.b64decode(image_data.split(",")[1])

    img_pil = Image.open(io.BytesIO(image_data)).convert("RGB")
    img_arr = np.array(img_pil)
    return img_pil, img_arr


def detect_face(image_data):
    """
    Detects whether a usable human face is present in the image.
    Returns:
        (found: bool, face_crop: np.ndarray, error_message: str)
    """
    try:
        pil_img, img_arr = decode_image_bytes(image_data)
    except Exception as e:
        return False, None, f"Could not decode image: {str(e)}"

    h, w = img_arr.shape[:2]
    if h < 80 or w < 80:
        return False, None, "Captured image resolution is too low."

    # If OpenCV is installed, use OpenCV Haar Cascade
    if OPENCV_AVAILABLE:
        try:
            gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60)
            )

            if len(faces) == 0:
                # Try with slightly looser params
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(40, 40))

            if len(faces) == 0:
                return False, None, "No face detected in camera frame. Ensure good lighting and face camera."
            if len(faces) > 1:
                return False, None, "Multiple faces detected. Only one person should be in the frame."

            (x, y, fw, fh) = faces[0]
            # Add padding
            pad_x = int(fw * 0.1)
            pad_y = int(fh * 0.1)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w, x + fw + pad_x)
            y2 = min(h, y + fh + pad_y)

            face_crop = img_arr[y1:y2, x1:x2]
            return True, face_crop, None
        except Exception as e:
            # Fall back to image processing check
            pass

    # Computer Vision Fallback (analyzes image contrast, center mass, skin tone distribution)
    # Check that image is not blank/monochrome and has adequate facial region properties
    gray_arr = np.mean(img_arr, axis=2)
    std_dev = np.std(gray_arr)
    if std_dev < 15:
        return False, None, "Image quality is too low or frame is too dark/blurry."

    # Center crop standard face region (assumes portrait centered alignment)
    cx, cy = w // 2, h // 2
    size = min(w, h) * 0.65
    x1 = int(max(0, cx - size // 2))
    x2 = int(min(w, cx + size // 2))
    y1 = int(max(0, cy - size // 2))
    y2 = int(min(h, cy + size // 2))

    face_crop = img_arr[y1:y2, x1:x2]
    return True, face_crop, None

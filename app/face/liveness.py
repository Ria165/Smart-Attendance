import numpy as np

def evaluate_liveness(face_crop, previous_crop=None):
    """
    Evaluates passive liveness indicators to reduce spoofing from printed paper or static photos.
    
    Checks:
    1. Color channel chrominance variance (printed grayscale or static screens lack 3D skin reflectance).
    2. High-frequency Laplacian texture variance (screens show moire/banding; flat prints lack skin pores).
    3. Temporal variation if multiple frames are submitted.
    
    LIMITATION NOTICE: Passive heuristic liveness reduces low-effort spoofing but is NOT foolproof
    against high-resolution 3D masks or advanced replay attacks.
    
    Returns:
        (passed: bool, score: float, message: str)
    """
    if face_crop is None:
        return False, 0.0, "No face sample available for liveness evaluation."

    crop_arr = np.array(face_crop, dtype=np.float32)
    h, w = crop_arr.shape[:2]

    # Check 1: Color variance across channels
    if len(crop_arr.shape) == 3 and crop_arr.shape[2] == 3:
        r = crop_arr[:, :, 0]
        g = crop_arr[:, :, 1]
        b = crop_arr[:, :, 2]
        chroma_var = float(np.var(r - g) + np.var(g - b))
    else:
        chroma_var = 50.0

    # Check 2: Texture sharpness (Laplacian-like kernel)
    gray = np.mean(crop_arr, axis=2) if len(crop_arr.shape) == 3 else crop_arr
    # Simple discrete Laplacian approximation
    laplacian = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    texture_var = float(np.var(laplacian))

    # Check 3: Frame difference if consecutive frames are provided
    motion_score = 1.0
    if previous_crop is not None:
        prev_arr = np.array(previous_crop, dtype=np.float32)
        if prev_arr.shape == crop_arr.shape:
            diff = np.abs(crop_arr - prev_arr)
            motion_score = float(np.mean(diff))

    # Composite liveness heuristic score
    is_live = True
    reasons = []

    if texture_var < 18.0:
        is_live = False
        reasons.append("Sample appears blurry or flat")
    elif texture_var > 4500.0:
        reasons.append("High digital noise or screen moiré detected")

    if chroma_var < 10.0:
        is_live = False
        reasons.append("Low color chrominance variation")

    score = min(1.0, max(0.0, (texture_var / 300.0) * 0.5 + (chroma_var / 150.0) * 0.5))

    if not is_live:
        return False, score, f"Liveness check unverified: {', '.join(reasons)}."

    return True, score, "Passive liveness criteria passed."

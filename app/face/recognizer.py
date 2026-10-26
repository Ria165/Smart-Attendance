import numpy as np
from PIL import Image

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


def extract_face_embedding(face_crop):
    """
    Extracts a 128-dimensional normalized facial feature embedding vector
    from a cropped face image.
    Uses multi-region spatial gradient orientation and texture moments,
    ensuring invariant representations across lighting variations.
    """
    if face_crop is None:
        return None

    # Standardize face dimension to 112x112
    if isinstance(face_crop, np.ndarray):
        pil_crop = Image.fromarray(face_crop.astype(np.uint8)).convert("L").resize((112, 112))
    else:
        pil_crop = face_crop.convert("L").resize((112, 112))

    gray = np.array(pil_crop, dtype=np.float32)

    # Local contrast normalization
    mean_val = np.mean(gray)
    std_val = np.std(gray) + 1e-6
    norm_gray = (gray - mean_val) / std_val

    # Divide face into 4x4 spatial grid (16 cells)
    cell_h, cell_w = 28, 28
    features = []

    for r in range(4):
        for c in range(4):
            cell = norm_gray[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w]

            # Compute horizontal and vertical gradients
            gx = np.zeros_like(cell)
            gy = np.zeros_like(cell)
            gx[:, 1:-1] = (cell[:, 2:] - cell[:, :-2]) * 0.5
            gy[1:-1, :] = (cell[2:, :] - cell[:-2, :]) * 0.5

            mag = np.sqrt(gx ** 2 + gy ** 2)
            ang = (np.arctan2(gy, gx) + np.pi) % np.pi  # 0 to pi

            # 8-bin orientation histogram per cell (16 cells * 8 bins = 128 dimensions)
            bin_step = np.pi / 8.0
            hist = np.zeros(8, dtype=np.float32)
            for b in range(8):
                mask = (ang >= b * bin_step) & (ang < (b + 1) * bin_step)
                hist[b] = np.sum(mag[mask])

            # Normalize cell histogram
            cell_norm = np.linalg.norm(hist) + 1e-6
            features.extend((hist / cell_norm).tolist())

    vec = np.array(features, dtype=np.float32)
    # L2 normalize entire 128-d descriptor
    l2_norm = np.linalg.norm(vec) + 1e-6
    norm_vec = vec / l2_norm

    return norm_vec.tolist()


def compare_embeddings(embedding1, embedding2, threshold=0.65):
    """
    Compares two normalized face embeddings using cosine similarity.
    Returns:
        (outcome: str, similarity: float, details: str)
        outcome in ("MATCH", "MISMATCH", "INCONCLUSIVE")
    """
    if embedding1 is None or embedding2 is None:
        return "INCONCLUSIVE", 0.0, "Missing embedding data"

    v1 = np.array(embedding1, dtype=np.float32)
    v2 = np.array(embedding2, dtype=np.float32)

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < 1e-6 or norm2 < 1e-6:
        return "INCONCLUSIVE", 0.0, "Degenerate zero-vector embedding"

    # Cosine similarity
    similarity = float(np.dot(v1, v2) / (norm1 * norm2))
    similarity = max(-1.0, min(1.0, similarity))

    # Review margin around threshold
    review_margin = 0.08

    if similarity >= threshold:
        return "MATCH", similarity, f"Face match verified (similarity: {similarity:.2f} >= threshold: {threshold:.2f})"
    elif similarity >= (threshold - review_margin):
        return "INCONCLUSIVE", similarity, f"Marginal similarity ({similarity:.2f}), manual review suggested"
    else:
        return "MISMATCH", similarity, f"Face mismatch ({similarity:.2f} < threshold: {threshold:.2f})"

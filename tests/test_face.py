import unittest
import numpy as np
from app import create_app
from app.face.recognizer import compare_embeddings
from app.face.liveness import evaluate_liveness

class FaceRecognitionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_cosine_similarity_identical_embeddings(self):
        # Deterministic normalized 128-d vector
        np.random.seed(42)
        v = np.random.randn(128).astype(np.float32)
        v = (v / np.linalg.norm(v)).tolist()

        outcome, similarity, details = compare_embeddings(v, v, threshold=0.65)
        self.assertEqual(outcome, "MATCH")
        self.assertAlmostEqual(similarity, 1.0, places=4)

    def test_cosine_similarity_slight_variation_match(self):
        np.random.seed(42)
        v1 = np.random.randn(128).astype(np.float32)
        v1 = v1 / np.linalg.norm(v1)

        # Add small perturbation to simulate realistic lighting/expression change
        noise = np.random.normal(0, 0.03, 128).astype(np.float32)
        v2 = v1 + noise
        v2 = (v2 / np.linalg.norm(v2)).tolist()
        v1 = v1.tolist()

        outcome, similarity, details = compare_embeddings(v1, v2, threshold=0.65)
        self.assertEqual(outcome, "MATCH")
        self.assertGreaterEqual(similarity, 0.65)

    def test_cosine_similarity_mismatch(self):
        np.random.seed(10)
        v1 = np.random.randn(128).astype(np.float32)
        v1 = (v1 / np.linalg.norm(v1)).tolist()

        np.random.seed(999)
        v2 = np.random.randn(128).astype(np.float32)
        v2 = (v2 / np.linalg.norm(v2)).tolist()

        outcome, similarity, details = compare_embeddings(v1, v2, threshold=0.65)
        self.assertEqual(outcome, "MISMATCH")
        self.assertLess(similarity, 0.65)

    def test_marginal_similarity_inconclusive(self):
        # Craft vector similarity right below threshold (e.g. 0.60 when threshold is 0.65)
        np.random.seed(42)
        base = np.random.randn(128).astype(np.float32)
        base = base / np.linalg.norm(base)

        ortho = np.random.randn(128).astype(np.float32)
        ortho -= np.dot(ortho, base) * base
        ortho /= np.linalg.norm(ortho)

        # angle for cosine ~ 0.60: cos(theta) = 0.60 => sin(theta) = 0.80
        target = 0.60 * base + 0.80 * ortho
        target /= np.linalg.norm(target)

        outcome, similarity, details = compare_embeddings(base.tolist(), target.tolist(), threshold=0.65)
        self.assertEqual(outcome, "INCONCLUSIVE")
        self.assertIn("inconclusive", outcome.lower())

    def test_liveness_heuristic_evaluation(self):
        # A synthetic flat gray image (simulating blank/spoof print)
        flat_crop = np.full((100, 100, 3), 128, dtype=np.uint8)
        passed, score, msg = evaluate_liveness(flat_crop)
        self.assertFalse(passed)
        self.assertIn("flat", msg.lower())

if __name__ == "__main__":
    unittest.main()

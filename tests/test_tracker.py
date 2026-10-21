import os, sys, unittest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from face_reco.tracker import CentroidTracker


class TrackerTestCase(unittest.TestCase):
    def test_close_bbox_matches_existing_track(self):
        t = CentroidTracker(max_distance=80)
        tid1 = t.update((100, 100, 50, 50))
        tid2 = t.update((105, 102, 50, 50))
        self.assertEqual(tid1, tid2)

    def test_far_bbox_creates_new_track(self):
        t = CentroidTracker(max_distance=80)
        tid1 = t.update((100, 100, 50, 50))
        tid2 = t.update((500, 500, 50, 50))
        self.assertNotEqual(tid1, tid2)

    def test_identity_persists_across_frames(self):
        t = CentroidTracker(max_distance=80)
        tid = t.update((100, 100, 50, 50))
        t.set_identity(tid, "STU001")
        t.update((103, 101, 50, 50))
        self.assertEqual(t.get_identity(tid), "STU001")

    def test_track_ages_out_after_repeated_misses(self):
        t = CentroidTracker(max_distance=80)
        tid = t.update((100, 100, 50, 50))
        for _ in range(11):
            t.update(None)
        self.assertNotIn(tid, t.tracked)

    def test_none_bbox_returns_none_track_id(self):
        t = CentroidTracker()
        self.assertIsNone(t.update(None))


if __name__ == "__main__":
    unittest.main()

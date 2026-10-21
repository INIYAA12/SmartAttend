import math

class CentroidTracker:
    def __init__(self, max_distance=80):
        self.tracked = {}
        self.next_id = 0
        self.max_distance = max_distance

    @staticmethod
    def _centroid(bbox):
        x, y, w, h = bbox
        return (x + w / 2, y + h / 2)

    def update(self, bbox):
        if bbox is None:
            for tid in list(self.tracked.keys()):
                self.tracked[tid]["misses"] += 1
                if self.tracked[tid]["misses"] > 10:
                    del self.tracked[tid]
            return None
        centroid = self._centroid(bbox)
        best_id, best_dist = None, self.max_distance
        for tid, data in self.tracked.items():
            dist = math.dist(centroid, data["centroid"])
            if dist < best_dist:
                best_dist = dist
                best_id = tid
        if best_id is not None:
            self.tracked[best_id]["centroid"] = centroid
            self.tracked[best_id]["bbox"] = bbox
            self.tracked[best_id]["misses"] = 0
            return best_id
        tid = self.next_id
        self.next_id += 1
        self.tracked[tid] = {"centroid": centroid, "bbox": bbox, "student_id": None, "misses": 0}
        return tid

    def set_identity(self, track_id, student_id):
        if track_id in self.tracked:
            self.tracked[track_id]["student_id"] = student_id

    def get_identity(self, track_id):
        if track_id in self.tracked:
            return self.tracked[track_id]["student_id"]
        return None

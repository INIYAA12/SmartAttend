import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_fast_app = None
_full_app = None

def get_fast_app():
    global _fast_app
    if _fast_app is None:
        from insightface.app import FaceAnalysis
        _fast_app = FaceAnalysis(name=config.ARCFACE_MODEL_NAME, allowed_modules=["detection"], providers=["CPUExecutionProvider"])
        _fast_app.prepare(ctx_id=config.ARCFACE_CTX_ID, det_size=config.ARCFACE_DET_SIZE)
    return _fast_app

def get_full_app():
    global _full_app
    if _full_app is None:
        from insightface.app import FaceAnalysis
        _full_app = FaceAnalysis(name=config.ARCFACE_MODEL_NAME, allowed_modules=["detection", "recognition"], providers=["CPUExecutionProvider"])
        _full_app.prepare(ctx_id=config.ARCFACE_CTX_ID, det_size=config.ARCFACE_DET_SIZE)
    return _full_app

def get_faces_fast(frame):
    faces = get_fast_app().get(frame)
    return sorted(faces, key=lambda f: f.det_score, reverse=True)

def get_faces(frame):
    faces = get_full_app().get(frame)
    return sorted(faces, key=lambda f: f.det_score, reverse=True)

def largest_face_fast(frame):
    faces = get_faces_fast(frame)
    if not faces: return None
    best = faces[0]
    return best if best.det_score >= config.ARCFACE_MIN_DET_SCORE else None

def largest_face(frame):
    faces = get_faces(frame)
    if not faces: return None
    best = faces[0]
    return best if best.det_score >= config.ARCFACE_MIN_DET_SCORE else None

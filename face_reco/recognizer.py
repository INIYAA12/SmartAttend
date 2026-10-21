"""
Builds and queries the face gallery.

ArcFace is pretrained, so "training the recognizer" just means collecting
every saved embedding sample (data/faces/<student_id>/*.npy) into a
searchable VectorIndex and persisting it. Every individual sample is kept
(not averaged), so a live frame can match whichever registered pose it
most resembles.
"""

import os
import sys

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from face_reco.vector_index import VectorIndex


class NoTrainingDataError(Exception):
    pass


def _list_student_samples():
    result = {}
    if not os.path.isdir(config.FACES_DIR):
        return result
    for student_id in sorted(os.listdir(config.FACES_DIR)):
        student_dir = os.path.join(config.FACES_DIR, student_id)
        if not os.path.isdir(student_dir):
            continue
        samples = [os.path.join(student_dir, f) for f in sorted(os.listdir(student_dir)) if f.lower().endswith(".npy")]
        if samples:
            result[student_id] = samples
    return result


def train_recognizer():
    samples = _list_student_samples()
    if not samples:
        raise NoTrainingDataError("No registered face samples found. Register at least one student's face first.")
    X, y = [], []
    for student_id, paths in samples.items():
        for p in paths:
            X.append(np.load(p))
            y.append(student_id)
    index = VectorIndex(config.VECTOR_BACKEND).build(np.vstack(X), y)
    os.makedirs(os.path.dirname(config.FACE_GALLERY_PATH), exist_ok=True)
    index.save(config.FACE_GALLERY_PATH)
    return {"students_trained": len(samples), "total_samples": len(y), "backend": index.backend}


_cache = {"key": None, "index": None}


def load_gallery(force_reload=False):
    path = config.FACE_GALLERY_PATH
    if not os.path.exists(path):
        raise NoTrainingDataError("Face recognizer gallery has not been built yet. Register faces, then build the recognizer.")
    key = (path, os.stat(path).st_mtime_ns, config.VECTOR_BACKEND)  # rebuilt file => automatic reload
    if force_reload or _cache["key"] != key:
        _cache["index"] = VectorIndex.load(path, config.VECTOR_BACKEND)
        _cache["key"] = key
    return _cache["index"]


def gallery_info():
    """Summary for health checks, or None if no gallery has been built."""
    try:
        index = load_gallery()
    except NoTrainingDataError:
        return None
    return {"backend": index.backend, "samples": len(index), "students": len(set(index.labels))}


def recognize_embedding(embedding):
    """Returns (student_id or None, cosine similarity). HIGHER similarity =
    better match; below ARCFACE_SIMILARITY_THRESHOLD the face is 'unknown'."""
    label, similarity = load_gallery().search(embedding)
    if similarity >= config.ARCFACE_SIMILARITY_THRESHOLD:
        return label, similarity
    return None, similarity


def remove_student_face_data(student_id):
    """
    Safely deletes a student's face embedding directory from disk and rebuilds
    the recognition gallery. If no face samples remain, safely removes gallery.npz.
    """
    import shutil
    student_dir = os.path.join(config.FACES_DIR, student_id)
    if os.path.exists(student_dir):
        shutil.rmtree(student_dir, ignore_errors=True)

    try:
        train_recognizer()
    except NoTrainingDataError:
        if os.path.exists(config.FACE_GALLERY_PATH):
            try:
                os.remove(config.FACE_GALLERY_PATH)
            except OSError:
                pass
        _cache["key"] = None
        _cache["index"] = None


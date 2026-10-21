import os
import json
import datetime
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import joblib


def _ensure_dir():
    os.makedirs(config.MODEL_REGISTRY_DIR, exist_ok=True)


def save_version(pipeline, metrics: dict, baseline_stats: dict):
    _ensure_dir()
    version = "v" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    model_path = os.path.join(config.MODEL_REGISTRY_DIR, f"{version}.pkl")
    metrics_path = os.path.join(config.MODEL_REGISTRY_DIR, f"{version}_metrics.json")

    if os.path.exists(model_path):
        raise RuntimeError(f"Version collision on {version} — aborting save.")

    joblib.dump(pipeline, model_path)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({"version": version, "created_at": datetime.datetime.now().isoformat(), **metrics}, f, indent=2)

    with open(config.BASELINE_STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(baseline_stats, f, indent=2)

    previous = get_current_version_info()
    promoted = True
    reason = "No existing model — first version promoted automatically."

    if previous is not None:
        if metrics["mae"] <= previous["mae"]:
            reason = f"MAE improved ({previous['mae']} -> {metrics['mae']}) — promoted."
        else:
            promoted = False
            reason = (
                f"New model MAE ({metrics['mae']}) is worse than current "
                f"live model MAE ({previous['mae']}) — kept in registry but NOT promoted."
            )

    if promoted:
        with open(config.CURRENT_VERSION_POINTER, "w", encoding="utf-8") as f:
            f.write(version)

    return {"version": version, "promoted": promoted, "reason": reason, "metrics": metrics}


def get_current_version():
    if not os.path.exists(config.CURRENT_VERSION_POINTER):
        return None
    with open(config.CURRENT_VERSION_POINTER, "r", encoding="utf-8") as f:
        return f.read().strip()


def get_current_version_info():
    version = get_current_version()
    if version is None:
        return None
    metrics_path = os.path.join(config.MODEL_REGISTRY_DIR, f"{version}_metrics.json")
    if not os.path.exists(metrics_path):
        return None
    with open(metrics_path, "r", encoding="utf-8") as f:
        return json.load(f)


_model_cache = {}


def load_current_model():
    """Loads the live model, cached in memory per (file, mtime) so a bulk
    prediction run doesn't re-read the pickle for every student."""
    version = get_current_version()
    if version is None:
        return None, None
    model_path = os.path.join(config.MODEL_REGISTRY_DIR, f"{version}.pkl")
    if not os.path.exists(model_path):
        return None, None
    mtime = os.path.getmtime(model_path)
    cached = _model_cache.get(model_path)
    if cached and cached[0] == mtime:
        return cached[1], version
    model = joblib.load(model_path)
    _model_cache[model_path] = (mtime, model)
    return model, version


def list_versions():
    _ensure_dir()
    versions = []
    for fname in sorted(os.listdir(config.MODEL_REGISTRY_DIR), reverse=True):
        if fname.endswith("_metrics.json"):
            with open(os.path.join(config.MODEL_REGISTRY_DIR, fname), "r", encoding="utf-8") as f:
                versions.append(json.load(f))
    current = get_current_version()
    for v in versions:
        v["is_current"] = (v["version"] == current)
    return versions


def rollback_to(version: str):
    model_path = os.path.join(config.MODEL_REGISTRY_DIR, f"{version}.pkl")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Version {version} not found in registry.")
    with open(config.CURRENT_VERSION_POINTER, "w", encoding="utf-8") as f:
        f.write(version)
    return version


def load_baseline_stats():
    if not os.path.exists(config.BASELINE_STATS_PATH):
        return None
    with open(config.BASELINE_STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

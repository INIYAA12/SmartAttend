import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def load_dataset(path=None):
    path = path or config.ML_DATASET_PATH
    return pd.read_csv(path)


def clean_dataset(df):
    required_cols = config.ML_FEATURE_COLUMNS + [config.ML_TARGET_COLUMN]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Dataset is missing required columns: {missing_cols}")

    df = df.copy()
    for col in required_cols:
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    df = df[(df[config.ML_TARGET_COLUMN] >= 0) & (df[config.ML_TARGET_COLUMN] <= 100)]
    return df


def get_features_and_target(df):
    X = df[config.ML_FEATURE_COLUMNS]
    y = df[config.ML_TARGET_COLUMN]
    return X, y


def category_for_score(score):
    for low, high, label in config.PERFORMANCE_BANDS:
        if low <= score <= high:
            return label
    return "Unknown"


def risk_for_score(score):
    for low, high, label in config.RISK_BANDS:
        if low <= score <= high:
            return label
    return "Unknown"

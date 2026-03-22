"""
CSV Loader Service
Handles parsing and initial analysis of uploaded CSV files.
Returns a pandas DataFrame and basic metadata about the dataset.
"""

import pandas as pd
from pathlib import Path
from backend.logging_config import logger_upload

MAX_CSV_SIZE_MB = 50
MAX_ROWS = 100000


def load_csv(file_path: str) -> dict:
    """
    Load a CSV file and return its data + metadata.

    Args:
        file_path: Absolute path to the CSV file.

    Returns:
        dict with keys:
            - success (bool)
            - filename (str)
            - rows (int)
            - columns (int)
            - column_names (list[str])
            - dtypes (dict): column name → data type
            - preview (list[dict]): first 5 rows as dicts
            - summary (str): basic stats description
            - error (str|None)
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_CSV_SIZE_MB:
            return {
                "success": False,
                "error": f"CSV exceeds max size ({file_size_mb:.1f}MB > {MAX_CSV_SIZE_MB}MB)",
            }

        df = pd.read_csv(file_path, nrows=MAX_ROWS)

        # Build basic summary stats
        summary_lines = [
            f"Dataset: {path.name}",
            f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
            f"Columns: {', '.join(df.columns.tolist())}",
            f"Missing values: {df.isnull().sum().sum()} total",
        ]

        # Add numeric column stats
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if numeric_cols:
            summary_lines.append(f"Numeric columns: {', '.join(numeric_cols)}")

        # Add categorical column info
        cat_cols = df.select_dtypes(include=["object"]).columns.tolist()
        if cat_cols:
            summary_lines.append(f"Categorical columns: {', '.join(cat_cols)}")

        return {
            "success": True,
            "filename": path.name,
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "column_names": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "preview": df.head(5).to_dict(orient="records"),
            "summary": "\n".join(summary_lines),
            "error": None,
        }

    except Exception as exc:
        logger_upload.error(f"CSV loading error: {exc}")
        return {"success": False, "error": str(exc)[:200]}


def get_dataframe(file_path: str) -> pd.DataFrame | None:
    """
    Load a CSV and return the raw DataFrame.
    Used by the Python execution tool and agent for analysis.
    """
    try:
        return pd.read_csv(file_path)
    except Exception as exc:
        logger_upload.error(f"Failed to load DataFrame from {file_path}: {exc}")
        return None

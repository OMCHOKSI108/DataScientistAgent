"""
Parquet Loader Service
Handles parsing and initial analysis of uploaded Parquet files.
Returns a pandas DataFrame and basic metadata about the dataset.
"""

import pandas as pd
from pathlib import Path
from backend.logging_config import logger_upload

MAX_PARQUET_SIZE_MB = 100

def load_parquet(file_path: str) -> dict:
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_PARQUET_SIZE_MB:
            return {"success": False, "error": f"Parquet exceeds max size ({file_size_mb:.1f}MB)"}

        df = pd.read_parquet(file_path)

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
        logger_upload.error(f"Parquet loading error: {exc}")
        return {"success": False, "error": str(exc)[:200]}

"""Conversion of geospatial values into JSON-compatible Python values."""

import json
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def json_compatible(value: Any) -> Any:
    """Return a JSON-safe value, normalizing NumPy and pandas scalars."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_compatible(item) for item in value]
    if hasattr(value, "__geo_interface__"):
        return json_compatible(value.__geo_interface__)
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError):
        return str(value)

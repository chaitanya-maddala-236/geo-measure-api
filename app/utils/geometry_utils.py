"""Geometry transformation helpers shared by CRS selection and measurement."""

import numpy as np
from pyproj import Transformer
from shapely import transform
from shapely.geometry.base import BaseGeometry


def reproject_geometry(
    geometry: BaseGeometry, transformer: Transformer
) -> BaseGeometry:
    """Apply a PyProj transformer to Shapely coordinates, preserving Z values."""

    def transform_coordinates(coordinates: np.ndarray) -> np.ndarray:
        x_values, y_values = transformer.transform(coordinates[:, 0], coordinates[:, 1])
        if coordinates.shape[1] > 2:
            return np.column_stack((x_values, y_values, coordinates[:, 2:]))
        return np.column_stack((x_values, y_values))

    return transform(geometry, transform_coordinates, include_z=geometry.has_z)

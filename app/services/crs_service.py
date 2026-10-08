"""Selection of safe, meter-based coordinate reference systems."""

from collections.abc import Sequence

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.utils.geometry_utils import reproject_geometry


def select_measurement_crs(
    source_crs: CRS | str, geometries: Sequence[BaseGeometry | None]
) -> CRS:
    """Choose a projected CRS in meters for measuring a dataset.

    Meter-based projected source CRSs are retained. Geographic and projected
    non-meter CRSs use a UTM zone based on the dataset's transformed centroid;
    polar datasets use the corresponding UPS polar stereographic CRS.
    """
    source = CRS.from_user_input(source_crs)
    if source.is_projected and _uses_meters(source):
        return source

    usable = [
        geometry
        for geometry in geometries
        if geometry is not None and not geometry.is_empty
    ]
    if not usable:
        raise ValueError(
            "A dataset with no non-empty geometries has no measurement CRS."
        )

    geographic = source.geodetic_crs or CRS.from_epsg(4326)
    to_geographic = Transformer.from_crs(source, geographic, always_xy=True)
    try:
        geographic_union = unary_union(
            [reproject_geometry(geometry, to_geographic) for geometry in usable]
        )
        center_lon = float(geographic_union.centroid.x)
        center_lat = float(geographic_union.centroid.y)
    except Exception as exc:
        raise ValueError(
            "The dataset extent could not be transformed to geographic CRS."
        ) from exc

    if not (-180.0 <= center_lon <= 180.0 and -90.0 <= center_lat <= 90.0):
        raise ValueError(
            "The dataset extent is outside valid longitude/latitude bounds."
        )
    if center_lat >= 84:
        return CRS.from_epsg(32661)  # WGS 84 / UPS North
    if center_lat <= -80:
        return CRS.from_epsg(32761)  # WGS 84 / UPS South

    zone = min(60, max(1, int((center_lon + 180.0) // 6.0) + 1))
    epsg = (32600 if center_lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _uses_meters(crs: CRS) -> bool:
    """Whether the projected CRS coordinate unit converts to meters 1:1."""
    axes = crs.axis_info
    return bool(axes) and all(
        axis.unit_conversion_factor is not None
        and abs(float(axis.unit_conversion_factor) - 1.0) < 1e-9
        for axis in axes[:2]
    )

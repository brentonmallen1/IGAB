"""Pure geo helpers for nearby-payee suggestions. No PostGIS at household scale:
a bounding-box prefilter in SQL plus exact haversine here is plenty."""

import math

EARTH_RADIUS_M = 6_371_000.0
# Meters per degree of latitude (and of longitude at the equator)
METERS_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lng, max_lng) box that contains the radius.

    The longitude span widens with latitude; cos is clamped so polar inputs
    degrade to a huge box instead of dividing by ~zero. Antimeridian wrap is
    ignored — a household budget doesn't straddle it, and the exact haversine
    filter afterwards keeps results correct regardless.
    """
    dlat = radius_m / METERS_PER_DEG_LAT
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    dlng = radius_m / (METERS_PER_DEG_LAT * cos_lat)
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng

"""Hand-computed fixtures for the nearby-payee geo helpers.

One degree of latitude is 111,194.93 m on the sphere used (R = 6,371,000 m):
2πR / 360. Longitude degrees shrink by cos(latitude).
"""

import math

from igab.utils.geo import bounding_box, haversine_m

M_PER_DEG = 2 * math.pi * 6_371_000 / 360  # 111,194.93 m


def test_zero_distance():
    assert haversine_m(40.0, -75.0, 40.0, -75.0) == 0.0


def test_one_degree_latitude_at_equator():
    assert abs(haversine_m(0.0, 0.0, 1.0, 0.0) - M_PER_DEG) < 1.0


def test_one_degree_longitude_at_equator():
    assert abs(haversine_m(0.0, 0.0, 0.0, 1.0) - M_PER_DEG) < 1.0


def test_hundred_meters_north():
    # 0.0009° of latitude ≈ 100.08 m regardless of longitude
    d = haversine_m(40.0, -75.0, 40.0009, -75.0)
    assert abs(d - 0.0009 * M_PER_DEG) < 0.1


def test_longitude_shrinks_with_latitude():
    # 0.0012° of longitude at 40°N ≈ 0.0012 · M_PER_DEG · cos(40°) ≈ 102.2 m
    expected = 0.0012 * M_PER_DEG * math.cos(math.radians(40.0))
    d = haversine_m(40.0, -75.0, 40.0, -74.9988)
    assert abs(d - expected) < 0.2


def test_symmetry():
    a = haversine_m(37.7749, -122.4194, 47.6062, -122.3321)
    b = haversine_m(47.6062, -122.3321, 37.7749, -122.4194)
    assert abs(a - b) < 1e-6


def test_bounding_box_contains_radius():
    lat, lng, radius = 40.0, -75.0, 500.0
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius)

    # Points exactly `radius` away in the four cardinal directions must fall
    # inside the box (bounding boxes over-approximate, never clip).
    dlat = radius / M_PER_DEG
    dlng = radius / (M_PER_DEG * math.cos(math.radians(lat)))
    assert min_lat <= lat - dlat * 0.999 and lat + dlat * 0.999 <= max_lat
    assert min_lng <= lng - dlng * 0.999 and lng + dlng * 0.999 <= max_lng


def test_bounding_box_survives_polar_latitude():
    # cos → 0 near the poles; the clamp must produce a finite (huge) box
    min_lat, max_lat, min_lng, max_lng = bounding_box(89.99, 0.0, 500.0)
    assert all(math.isfinite(v) for v in (min_lat, max_lat, min_lng, max_lng))
    assert max_lng > min_lng

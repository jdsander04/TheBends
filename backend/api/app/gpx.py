"""Minimal GPX 1.1 serialisation for road / route export."""
from typing import List, Tuple
from xml.sax.saxutils import escape

# A "segment" is a list of (lon, lat) coordinate pairs.
Segment = List[Tuple[float, float]]


def gpx_route(name: str, points: Segment) -> str:
    """GPX <rte> with one <rtept> per (lon, lat) point.

    A route (not a track) so riding apps (Kurviger/OsmAnd/Calimoto) re-route
    THROUGH the points as via points with their own curve-aware routing.
    """
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="TheBends" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <rte><name>{escape(name)}</name>",
    ]
    for lon, lat in points:
        parts.append(f'    <rtept lat="{lat:.6f}" lon="{lon:.6f}"/>')
    parts.append("  </rte>")
    parts.append("</gpx>")
    return "\n".join(parts)


def gpx_track(name: str, segments: List[Segment]) -> str:
    """Build a GPX document with one track containing one <trkseg> per segment."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="TheBends" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <trk><name>{escape(name)}</name>",
    ]
    for seg in segments:
        parts.append("    <trkseg>")
        for lon, lat in seg:
            parts.append(f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>')
        parts.append("    </trkseg>")
    parts.append("  </trk>")
    parts.append("</gpx>")
    return "\n".join(parts)

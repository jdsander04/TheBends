import math
from typing import Generator, List, Tuple

# Road classes a driver would actually seek out. `residential` is INCLUDED
# because many great rural backroads are tagged residential in OSM -- but
# subdivision streets share that tag, so they're separated later by local road
# density (see prune_urban_residential in load.py): isolated residential roads
# are kept, residential packed into a street grid is dropped.
HIGHWAY_TYPES = frozenset({
    "primary", "secondary", "tertiary", "unclassified",
    "residential", "primary_link", "secondary_link", "tertiary_link",
    "trunk", "trunk_link", "road",
})

_EARTH_R      = 6_371_000.0
_MIN_LENGTH_M = 400.0    # shortest scoreable segment (1/4 mile)
_WINDOW_M     = 1000.0   # sliding window size (1 km)
_STEP_M       = 500.0    # window step (50% overlap)


def _to_meters(lon: float, lat: float, ref_lat_rad: float) -> Tuple[float, float]:
    x = math.radians(lon) * _EARTH_R * math.cos(ref_lat_rad)
    y = math.radians(lat) * _EARTH_R
    return x, y


def _menger(p1: Tuple, p2: Tuple, p3: Tuple) -> float:
    """Menger curvature K = 1/R for three cartesian points."""
    d12 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    d23 = math.hypot(p3[0] - p2[0], p3[1] - p2[1])
    d31 = math.hypot(p1[0] - p3[0], p1[1] - p3[1])
    denom = d12 * d23 * d31
    if denom < 1e-6:
        return 0.0
    area = abs(
        (p2[0] - p1[0]) * (p3[1] - p1[1]) -
        (p3[0] - p1[0]) * (p2[1] - p1[1])
    ) / 2.0
    return (4.0 * area) / denom


def _radius_weight(K: float) -> float:
    """
    Quality weight for curvature K = 1/R (Adam Franco method).

    Monotonic: tighter curve = more driver engagement = higher weight.
    Hairpins are the *point* of roads like the Tail of the Dragon, so they
    must not be penalised. Residential loops / parking lots are excluded
    upstream by the displacement-ratio filter and road-class selection.

    Bends gentler than 175 m radius count as ZERO, not a small value: that is
    what separates a real driving road (Mt Baldy's 7-24 m hairpins) from a
    highway full of gentle sweepers (I-40), which otherwise leaks score from
    its many 175-400 m curves and never reaches a true 0.

       > 175 m radius : not a real curve            → 0.0
      100–175 m       : gentle sweeper              → 1.0
       60–100 m       : sweet spot, fun at pace     → 2.0
       30– 60 m       : tight, technical            → 3.0
        < 30 m        : hairpin, full engagement    → 4.0
    """
    if K < 1e-6:
        return 0.0
    R = 1.0 / K
    if R > 175: return 0.0
    if R > 100: return 1.0
    if R > 60:  return 2.0
    if R > 30:  return 3.0
    return 4.0


def _score_pts(pts: List[Tuple], segs: List[Tuple]) -> float:
    """
    Score a pre-projected segment (pts in meters, segs = (dx,dy,length) list).

    Tight-curve density: the length-weighted average of radius weights, i.e.
    how much real curvature you get per metre of road. Because gentle bends
    weigh 0 (see _radius_weight), straights and lone corners dilute this
    naturally -- no separate consistency penalty is needed, and punctuated
    roads with a few serious hairpins (Mt Baldy) are no longer double-punished.

    Returns 0.0 for:
      - too short (< _MIN_LENGTH_M)
      - loops/circles: endpoint displacement < 10% of total length
      - roads with no curve tighter than 175 m radius (e.g. interstates)
    """
    total_length = sum(s[2] for s in segs)
    if total_length < _MIN_LENGTH_M:
        return 0.0

    endpoint_dist = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    if endpoint_dist / total_length < 0.10:   # circle / residential loop
        return 0.0

    weighted_sum = 0.0
    for i in range(len(pts) - 2):
        K = _menger(pts[i], pts[i + 1], pts[i + 2])
        weighted_sum += _radius_weight(K) * segs[i][2]

    if weighted_sum < 1e-9:
        return 0.0

    return weighted_sum / total_length


def slice_road(
    nodes: List[Tuple[float, float]],
) -> Generator[Tuple[int, List[Tuple[float, float]], float], None, None]:
    """
    Yield (seg_idx, node_slice, raw_score) for each _WINDOW_M-meter sliding
    window of a road, stepping _STEP_M at a time.

    Only windows that pass the quality filters are yielded; seg_idx is always
    incremented so (way_id, seg_idx) stays stable across pipeline runs.
    """
    if len(nodes) < 5:
        return

    avg_lat_rad = math.radians(sum(n[1] for n in nodes) / len(nodes))
    pts = [_to_meters(lon, lat, avg_lat_rad) for lon, lat in nodes]

    # Cumulative distances along the way
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + math.hypot(
            pts[i + 1][0] - pts[i][0],
            pts[i + 1][1] - pts[i][1],
        ))

    total_length = cum[-1]
    if total_length < _MIN_LENGTH_M:
        return

    def idx_at(d: float) -> int:
        """First index where cum[i] >= d."""
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo

    seg_idx = 0
    start_d = 0.0

    while start_d <= total_length - _MIN_LENGTH_M * 0.5:
        end_d = min(start_d + _WINDOW_M, total_length)

        i0 = max(0, idx_at(start_d) - 1)
        i1 = idx_at(end_d)

        w_pts   = pts[i0: i1 + 1]
        w_nodes = nodes[i0: i1 + 1]

        if len(w_pts) >= 5:
            w_segs = []
            for i in range(len(w_pts) - 1):
                dx = w_pts[i + 1][0] - w_pts[i][0]
                dy = w_pts[i + 1][1] - w_pts[i][1]
                w_segs.append((dx, dy, math.hypot(dx, dy)))

            score = _score_pts(w_pts, w_segs)
            if score > 0.0:
                yield seg_idx, w_nodes, score

        seg_idx += 1
        start_d += _STEP_M

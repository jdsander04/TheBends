import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Generator, List, Optional, Tuple

from .curvature import HIGHWAY_TYPES, slice_road
from .elevation import ElevationData, profile_features

_PAVED = frozenset({
    "asphalt", "concrete", "paved", "chipseal", "concrete:plates",
    "concrete:lanes", "paving_stones", "sett", "metal", "wood", "bricks",
})
_UNPAVED = frozenset({
    "unpaved", "gravel", "fine_gravel", "compacted", "dirt", "earth",
    "ground", "grass", "sand", "mud", "pebblestone", "rock", "woodchips",
    "clay", "gravel;grass", "dirt/sand",
})


def classify_surface(tag: Optional[str]) -> str:
    """Normalise an OSM surface tag to paved / unpaved / unknown."""
    if not tag:
        return "unknown"
    t = tag.strip().lower()
    if t in _PAVED:
        return "paved"
    if t in _UNPAVED:
        return "unpaved"
    return "unknown"


@dataclass
class RoadRecord:
    way_id: int       # OSM way ID (may appear multiple times, once per segment)
    seg_idx: int      # window index within the way (0, 1, 2 …)
    name: str
    highway: str
    nodes: List[Tuple[float, float]]   # geographic coords for this segment
    raw_curvature: float = 0.0
    surface: str = "unknown"
    access: Optional[str] = None
    elev: dict = field(default_factory=dict)   # profile_features output


def parse_pbf(
    pbf_path: str,
    elev: Optional[ElevationData] = None,
) -> Generator[RoadRecord, None, None]:
    """
    Stream RoadRecord segments from an OSM PBF file.

    Each OSM way is sliced into 1 km windows; only windows that pass the
    curvature quality filters are yielded. Surface/access come from OSM tags;
    elevation/grade features are sampled from SRTM if `elev` is provided.
    Memory stays flat.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".osm.pbf", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [
                "osmium", "tags-filter",
                pbf_path, "w/highway",
                "--no-progress",
                "--overwrite",
                "-o", tmp.name,
            ],
            check=True,
        )

        proc = subprocess.Popen(
            [
                "osmium", "export",
                tmp.name,
                "--geometry-types=linestring",
                "--attributes=id",
                "--no-progress",
                "-f", "geojsonseq",
                "-o", "-",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    feature = json.loads(line)
                except json.JSONDecodeError:
                    continue

                props = feature.get("properties") or {}
                highway = props.get("highway")
                if highway not in HIGHWAY_TYPES:
                    continue

                geom = feature.get("geometry") or {}
                if geom.get("type") != "LineString":
                    continue

                nodes = [(c[0], c[1]) for c in geom.get("coordinates", [])]
                raw_id = props.get("@id") or feature.get("id") or 0
                way_id = int(raw_id)
                name = props.get("name", "")
                surface = classify_surface(props.get("surface"))
                access = props.get("access")

                for seg_idx, seg_nodes, score in slice_road(nodes):
                    feats = profile_features(seg_nodes, elev) if elev else {}
                    yield RoadRecord(
                        way_id=way_id,
                        seg_idx=seg_idx,
                        name=name,
                        highway=highway,
                        nodes=seg_nodes,
                        raw_curvature=score,
                        surface=surface,
                        access=access,
                        elev=feats,
                    )

        finally:
            proc.stdout.close()
            proc.wait()
            if proc.returncode not in (0, None):
                raise RuntimeError(f"osmium export failed: {proc.returncode}")

    finally:
        os.unlink(tmp.name)

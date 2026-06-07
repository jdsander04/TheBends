import os
from pathlib import Path

import psycopg2

from .download import REGIONS, US_STATES, download_region
from .elevation import ElevationData
from .load import (
    insert_raw,
    normalize_in_db,
    prune_short_residential,
    prune_urban_residential,
    recreate_table,
)
from .parse import parse_pbf

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATABASE_URL = os.environ["DATABASE_URL"]

# What to process when REGIONS is unset.
DEFAULT_REGIONS = ["pennsylvania", "new-york", "tennessee"]

# Convenience tags for the REGIONS env var.
_TAGS = {
    # Entire US as one ~12 GB extract: a single download/pass.
    "us":            ["united-states"],
    "usa":           ["united-states"],
    "us-full":       ["united-states"],
    "united-states": ["united-states"],
    # Entire US, state by state: smaller cached downloads, easier to retry.
    "all":           list(US_STATES),
    "all-states":    list(US_STATES),
    "us-states":     list(US_STATES),
}


def _resolve_regions(raw: str | None) -> list[str]:
    """Map the REGIONS env var to a concrete list of region slugs."""
    if not raw or not raw.strip():
        return DEFAULT_REGIONS
    key = raw.strip().lower()
    if key in _TAGS:
        return _TAGS[key]
    requested = [r.strip() for r in raw.split(",") if r.strip()]
    unknown = [r for r in requested if r not in REGIONS]
    if unknown:
        raise SystemExit(
            f"Unknown region(s): {', '.join(unknown)}\n"
            f"Use a tag (us, all-states) or a Geofabrik slug "
            f"(e.g. california, west-virginia)."
        )
    return requested


def main():
    conn = psycopg2.connect(DATABASE_URL)
    elev = ElevationData(str(DATA_DIR / "srtm"))

    regions = _resolve_regions(os.getenv("REGIONS"))

    print("Recreating osm_roads table ...")
    recreate_table(conn)

    for i, region in enumerate(regions):
        print(f"\n[{i+1}/{len(regions)}] {region}")
        pbf = download_region(region, DATA_DIR)
        print(f"  Streaming {pbf.name} (with surface + elevation) ...")
        insert_raw(parse_pbf(str(pbf), elev), conn)

    print("\nPruning dense-grid (subdivision) residential segments ...")
    removed = prune_urban_residential(conn)
    print(f"  removed {removed:,} segments")

    print("\nPruning short (cottage-lane) residential roads ...")
    removed = prune_short_residential(conn)
    print(f"  removed {removed:,} segments")

    print("\nNormalizing scores in database ...")
    normalize_in_db(conn)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()

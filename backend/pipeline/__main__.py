import os
from pathlib import Path

import psycopg2

from .download import REGIONS, download_region
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


def main():
    conn = psycopg2.connect(DATABASE_URL)
    elev = ElevationData(str(DATA_DIR / "srtm"))

    # REGIONS env var (comma-separated) overrides which regions to process.
    region_filter = os.getenv("REGIONS")
    if region_filter:
        regions = [r.strip() for r in region_filter.split(",") if r.strip()]
    else:
        regions = list(REGIONS)

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

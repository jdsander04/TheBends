from pathlib import Path

import httpx

_GEOFABRIK = "https://download.geofabrik.de/north-america/us"

REGIONS = {
    "pennsylvania": f"{_GEOFABRIK}/pennsylvania-latest.osm.pbf",
    "new-york":     f"{_GEOFABRIK}/new-york-latest.osm.pbf",
    "tennessee":    f"{_GEOFABRIK}/tennessee-latest.osm.pbf",
}


def download_region(region: str, data_dir: Path) -> Path:
    url = REGIONS[region]
    dest = data_dir / f"{region}-latest.osm.pbf"
    if dest.exists():
        print(f"  {dest.name} already cached, skipping download")
        return dest
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {url} ...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65_536):
                f.write(chunk)
    print(f"  Saved {dest} ({dest.stat().st_size / 1_048_576:.0f} MB)")
    return dest

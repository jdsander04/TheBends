from pathlib import Path

import httpx

_NA = "https://download.geofabrik.de/north-america"
_US = f"{_NA}/us"

# Geofabrik per-state extract slugs (50 states + DC).
US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "district-of-columbia", "florida", "georgia",
    "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york", "north-carolina",
    "north-dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode-island", "south-carolina", "south-dakota", "tennessee", "texas",
    "utah", "vermont", "virginia", "washington", "west-virginia", "wisconsin",
    "wyoming",
]

# Each state -> its Geofabrik extract, plus a single whole-country extract.
REGIONS = {state: f"{_US}/{state}-latest.osm.pbf" for state in US_STATES}
REGIONS["united-states"] = f"{_NA}/us-latest.osm.pbf"


def download_region(region: str, data_dir: Path) -> Path:
    url = REGIONS[region]
    dest = data_dir / f"{region}-latest.osm.pbf"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  {dest.name} already cached, skipping download")
        return dest
    data_dir.mkdir(parents=True, exist_ok=True)
    # Download to a .part file and rename on success, so an interrupted
    # download never gets left behind looking like a valid cached file.
    tmp = dest.with_name(dest.name + ".part")
    print(f"  Downloading {url} ...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65_536):
                f.write(chunk)
    tmp.rename(dest)
    print(f"  Saved {dest} ({dest.stat().st_size / 1_048_576:.0f} MB)")
    return dest

// adb reverse tcp:8000 tcp:8000 — tunnels device localhost to host
const String kApiBase = 'http://localhost:8000';

// Minimum map zoom level before we bother fetching roads.
// Below this the bounding box is too large to be useful.
const double kMinFetchZoom = 10.0;

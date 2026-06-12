// API base URL. Override per build with:
//   flutter build web --dart-define=API_BASE=https://thebends.example.com
//   flutter run        --dart-define=API_BASE=http://192.168.1.x:8000
// Default targets local dev (mobile uses `adb reverse tcp:8000 tcp:8000`).
const String kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://localhost:8000',
);

// Minimum map zoom before we bother fetching roads — below this the bounding
// box is too large. The floor eases down as the min-twistiness filter rises:
// with a strict filter only a handful of elite roads remain, so they're cheap
// and genuinely useful to render from a much wider, more zoomed-out view.
//   twistiness <= 0.3  -> zoom 10   (lots of roads; keep the view tight)
//   twistiness == 1.0  -> zoom 6    (only the best; show them region-wide)
double minFetchZoomFor(double minTwistiness) {
  const lowT = 0.3, highT = 1.0;
  const floorAtLow = 10.0, floorAtHigh = 6.0;
  final t = ((minTwistiness - lowT) / (highT - lowT)).clamp(0.0, 1.0);
  return floorAtLow + (floorAtHigh - floorAtLow) * t;
}

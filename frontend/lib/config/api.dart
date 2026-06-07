// API base URL. Override per build with:
//   flutter build web --dart-define=API_BASE=https://thebends.example.com
//   flutter run        --dart-define=API_BASE=http://192.168.1.x:8000
// Default targets local dev (mobile uses `adb reverse tcp:8000 tcp:8000`).
const String kApiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://localhost:8000',
);

// Minimum map zoom level before we bother fetching roads.
// Below this the bounding box is too large to be useful.
const double kMinFetchZoom = 10.0;

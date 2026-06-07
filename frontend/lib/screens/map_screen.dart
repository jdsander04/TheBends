import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import 'package:url_launcher/url_launcher_string.dart';

import '../config/api.dart';
import '../models/road.dart';
import '../services/api_service.dart';
import '../widgets/filter_slider.dart';
import '../widgets/road_detail_sheet.dart';

const _kDefaultCenter = LatLng(42.05, -74.35);
const _kDefaultZoom = 11.0;
const _kTapRadiusM = 80.0;
const _kSnapRadiusM = 150.0; // snap a route pin to a road within this radius
const _kPinHitRadiusM = 60.0; // tapping within this of a pin selects it

final filterProvider = StateProvider<double>((ref) => 0.3);
final pavedOnlyProvider = StateProvider<bool>((ref) => true);

// Used by RoadDetailSheet for the overall road color chip
Color twistinessColor(double score) {
  if (score >= 0.85) return const Color(0xFFFF0090);
  if (score >= 0.70) return const Color(0xFFFF2222);
  if (score >= 0.50) return const Color(0xFFFF6B00);
  return const Color(0xFFFFB300);
}

// Per-segment color based on local turn angle at that point
Color _curveColor(double angleDeg) {
  if (angleDeg < 3)  return const Color(0xFF7A5C00); // dim — straight section
  if (angleDeg < 10) return const Color(0xFFFFB300);  // amber — gentle
  if (angleDeg < 20) return const Color(0xFFFF6B00);  // orange — moderate
  if (angleDeg < 35) return const Color(0xFFFF2222);  // crimson — good curve
  return const Color(0xFFFF0090);                      // magenta — tight!
}

double _curveWidth(double angleDeg, double roadScore) {
  final base = 2.5 + roadScore * 2.0;
  if (angleDeg < 3)  return base * 0.5;
  if (angleDeg < 10) return base;
  if (angleDeg < 20) return base * 1.3;
  if (angleDeg < 35) return base * 1.6;
  return base * 2.0;
}

// Equirectangular bearing-change angle at node b, given neighbors a and c
double _angleDeg(LatLng a, LatLng b, LatLng c) {
  final refLat = b.latitude * math.pi / 180.0;
  const R = 6371000.0;
  final cosLat = math.cos(refLat);
  final ax = a.longitude * math.pi / 180.0 * R * cosLat;
  final ay = a.latitude  * math.pi / 180.0 * R;
  final bx = b.longitude * math.pi / 180.0 * R * cosLat;
  final by = b.latitude  * math.pi / 180.0 * R;
  final cx = c.longitude * math.pi / 180.0 * R * cosLat;
  final cy = c.latitude  * math.pi / 180.0 * R;
  final dx1 = bx - ax, dy1 = by - ay;
  final dx2 = cx - bx, dy2 = cy - by;
  final l1 = math.sqrt(dx1 * dx1 + dy1 * dy1);
  final l2 = math.sqrt(dx2 * dx2 + dy2 * dy2);
  if (l1 < 0.1 || l2 < 0.1) return 0.0;
  final cosA = ((dx1 * dx2 + dy1 * dy2) / (l1 * l2)).clamp(-1.0, 1.0);
  return math.acos(cosA) * 180.0 / math.pi;
}

// Split each road into per-segment Polylines colored by local curve angle.
// Computed once when roads arrive, not on every frame.
List<Polyline> _buildPolylines(List<Road> roads) {
  final result = <Polyline>[];
  for (final road in roads) {
    final pts = road.points;
    if (pts.length < 2) continue;

    // Angle at each node (endpoints inherit from their inner neighbor)
    final angles = List<double>.filled(pts.length, 0.0);
    for (int i = 1; i < pts.length - 1; i++) {
      angles[i] = _angleDeg(pts[i - 1], pts[i], pts[i + 1]);
    }
    angles[0] = pts.length > 2 ? angles[1] : 0.0;
    angles[pts.length - 1] = pts.length > 2 ? angles[pts.length - 2] : 0.0;

    for (int i = 0; i < pts.length - 1; i++) {
      final angle = (angles[i] + angles[i + 1]) / 2.0;
      result.add(Polyline(
        points: [pts[i], pts[i + 1]],
        color: _curveColor(angle),
        strokeWidth: _curveWidth(angle, road.twistinessScore),
        strokeCap: StrokeCap.round,
      ));
    }
  }
  return result;
}

class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final _mapController = MapController();
  List<Road> _roads = [];
  List<Polyline> _polylines = [];
  bool _fetching = false;
  Timer? _debounce;
  double _currentZoom = _kDefaultZoom;

  bool _planMode = false;
  final List<LatLng> _waypoints = [];
  int? _selectedPin; // index of the pin being moved, if any

  @override
  void dispose() {
    _debounce?.cancel();
    _mapController.dispose();
    super.dispose();
  }

  void _onMapEvent(MapEvent event) {
    if (event is MapEventMoveEnd ||
        event is MapEventRotateEnd ||
        event is MapEventFlingAnimationEnd) {
      setState(() => _currentZoom = _mapController.camera.zoom);
      _scheduleFetch();
    }
  }

  void _scheduleFetch() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 600), _fetchRoads);
  }

  Future<void> _fetchRoads() async {
    final camera = _mapController.camera;
    if (camera.zoom < kMinFetchZoom) {
      if (_roads.isNotEmpty) {
        setState(() { _roads = []; _polylines = []; });
      }
      return;
    }

    if (_fetching) return;
    setState(() => _fetching = true);

    final bounds = camera.visibleBounds;
    final minTwistiness = ref.read(filterProvider);
    final pavedOnly = ref.read(pavedOnlyProvider);

    try {
      final roads = await ApiService.fetchRoads(
        minLat: bounds.south,
        minLon: bounds.west,
        maxLat: bounds.north,
        maxLon: bounds.east,
        minTwistiness: minTwistiness,
        includeUnpaved: !pavedOnly,
      );
      if (mounted) {
        setState(() {
          _roads = roads;
          _polylines = _buildPolylines(roads);
        });
      }
    } catch (_) {
      // silent fail — roads stay as-is
    } finally {
      if (mounted) setState(() => _fetching = false);
    }
  }

  void _togglePlanMode() {
    setState(() {
      _planMode = !_planMode;
      _selectedPin = null;
    });
  }

  /// Nearest point on a displayed road within [_kSnapRadiusM], else null.
  LatLng? _snapToRoad(LatLng tapped) {
    const distance = Distance();
    LatLng? best;
    double minDist = _kSnapRadiusM;
    for (final road in _roads) {
      for (final point in road.points) {
        final d = distance.distance(tapped, point);
        if (d < minDist) {
          minDist = d;
          best = point;
        }
      }
    }
    return best;
  }

  /// Index of an existing pin near [tapped], or null.
  int? _pinAt(LatLng tapped) {
    const distance = Distance();
    int? hit;
    double minDist = _kPinHitRadiusM;
    for (int i = 0; i < _waypoints.length; i++) {
      final d = distance.distance(tapped, _waypoints[i]);
      if (d < minDist) {
        minDist = d;
        hit = i;
      }
    }
    return hit;
  }

  void _onPlanTap(LatLng tapped) {
    final hit = _pinAt(tapped);
    setState(() {
      if (_selectedPin != null) {
        // A pin is armed: tapping it again cancels, tapping elsewhere moves it.
        if (hit == _selectedPin) {
          _selectedPin = null;
        } else {
          _waypoints[_selectedPin!] = _snapToRoad(tapped) ?? tapped;
          _selectedPin = null;
        }
      } else if (hit != null) {
        _selectedPin = hit; // arm this pin to move
      } else {
        // Snap a new pin to the nearest twisty road so Google routes ALONG it.
        _waypoints.add(_snapToRoad(tapped) ?? tapped);
      }
    });
  }

  void _undoWaypoint() {
    if (_waypoints.isNotEmpty) {
      setState(() {
        _waypoints.removeLast();
        _selectedPin = null;
      });
    }
  }

  void _clearRoute() {
    setState(() {
      _waypoints.clear();
      _selectedPin = null;
    });
  }

  /// Google Maps directions URL (documented `?api=1` form — the only one the
  /// mobile app honours). First pin = origin, last = destination, the rest are
  /// waypoints. NOTE: the mobile app treats these as STOPS, not via points —
  /// there is no URL way to make via points in the consumer app. Built by hand
  /// so `api=1` is preserved (Uri.replace would drop it) and commas stay literal.
  String _googleMapsUrl() {
    String ll(LatLng p) =>
        '${p.latitude.toStringAsFixed(6)},${p.longitude.toStringAsFixed(6)}';
    final origin = _waypoints.first;
    final dest = _waypoints.last;
    final mid = _waypoints.sublist(1, _waypoints.length - 1);

    final buf = StringBuffer('https://www.google.com/maps/dir/?api=1');
    buf.write('&origin=${ll(origin)}');
    buf.write('&destination=${ll(dest)}');
    if (mid.isNotEmpty) {
      buf.write('&waypoints=${mid.map(ll).join('%7C')}'); // %7C = pipe
    }
    buf.write('&travelmode=driving');
    return buf.toString();
  }

  Future<void> _openInGoogleMaps() async {
    if (_waypoints.length < 2) return;
    await launchUrlString(_googleMapsUrl(),
        mode: LaunchMode.externalApplication);
  }

  /// Waze deep link — supports a SINGLE destination only (no multi-waypoint
  /// routes via URL), so we navigate to the route's first pin (the trailhead).
  Future<void> _openInWaze() async {
    if (_waypoints.isEmpty) return;
    final start = _waypoints.first;
    final url = 'https://www.waze.com/ul?ll=${start.latitude},'
        '${start.longitude}&navigate=yes';
    await launchUrlString(url, mode: LaunchMode.externalApplication);
  }

  /// Download the route as a GPX file (via points, one per pin) to the
  /// device's Downloads folder, for import into a riding nav app
  /// (Kurviger / OsmAnd / Calimoto). The backend serves it with a
  /// Content-Disposition: attachment header, so the system download manager
  /// saves it to Downloads — no storage permissions needed.
  Future<void> _downloadRouteGpx() async {
    if (_waypoints.length < 2) return;
    final pts = _waypoints
        .map((p) => '${p.latitude.toStringAsFixed(6)},'
            '${p.longitude.toStringAsFixed(6)}')
        .join(';');
    final url = '$kApiBase/api/v1/routes/gpx?points=$pts';
    await launchUrlString(url, mode: LaunchMode.externalApplication);
  }

  void _copyRouteUrl() {
    if (_waypoints.length < 2) return;
    Clipboard.setData(ClipboardData(text: _googleMapsUrl()));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Route link copied to clipboard'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _onMapTap(TapPosition _, LatLng tapped) {
    if (_planMode) {
      _onPlanTap(tapped);
      return;
    }

    const distance = Distance();
    Road? nearest;
    double minDist = double.infinity;

    for (final road in _roads) {
      for (final point in road.points) {
        final d = distance.distance(tapped, point);
        if (d < minDist) {
          minDist = d;
          nearest = road;
        }
      }
    }

    if (nearest != null && minDist <= _kTapRadiusM) {
      showModalBottomSheet(
        context: context,
        backgroundColor: Colors.transparent,
        isScrollControlled: true,
        builder: (_) => RoadDetailSheet(road: nearest!),
      );
    }
  }

  Future<void> _goToMyLocation() async {
    if (!await Geolocator.isLocationServiceEnabled()) return;
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) return;
    }
    if (permission == LocationPermission.deniedForever) return;
    final pos = await Geolocator.getCurrentPosition();
    _mapController.move(LatLng(pos.latitude, pos.longitude), 13.0);
  }

  @override
  Widget build(BuildContext context) {
    final minTwistiness = ref.watch(filterProvider);
    final zoom = _currentZoom;

    return Scaffold(
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _kDefaultCenter,
              initialZoom: _kDefaultZoom,
              onMapEvent: _onMapEvent,
              onMapReady: () {
                setState(() => _currentZoom = _mapController.camera.zoom);
                _scheduleFetch();
              },
              onTap: _onMapTap,
            ),
            children: [
              TileLayer(
                urlTemplate:
                    'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
                subdomains: const ['a', 'b', 'c', 'd'],
                userAgentPackageName: 'com.thebends.app',
                maxZoom: 19,
              ),
              if (_polylines.isNotEmpty)
                PolylineLayer(polylines: _polylines),
              if (_waypoints.length >= 2)
                PolylineLayer(polylines: [
                  Polyline(
                    points: _waypoints,
                    color: const Color(0xFF21E6FF),
                    strokeWidth: 3,
                  ),
                ]),
              if (_waypoints.isNotEmpty)
                MarkerLayer(
                  markers: [
                    for (int i = 0; i < _waypoints.length; i++)
                      Marker(
                        point: _waypoints[i],
                        width: 40,
                        height: 40,
                        child: _PinMarker(
                          index: i + 1,
                          selected: _selectedPin == i,
                        ),
                      ),
                  ],
                ),
              const RichAttributionWidget(
                attributions: [
                  TextSourceAttribution('OpenStreetMap contributors'),
                  TextSourceAttribution('CARTO'),
                ],
              ),
            ],
          ),

          Positioned(
            top: 0, left: 0, right: 0,
            child: Container(
              height: 80,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.black38, Colors.transparent],
                ),
              ),
            ),
          ),

          if (zoom < kMinFetchZoom)
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'Zoom in to see twisty roads',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
            ),

          Positioned(
            left: 0, right: 0, bottom: 0,
            child: _planMode
                ? _RoutePlanBar(
                    count: _waypoints.length,
                    movingPin: _selectedPin,
                    onExit: _togglePlanMode,
                    onUndo: _waypoints.isEmpty ? null : _undoWaypoint,
                    onClear: _waypoints.isEmpty ? null : _clearRoute,
                    onOpen:
                        _waypoints.length >= 2 ? _openInGoogleMaps : null,
                    onCopy: _waypoints.length >= 2 ? _copyRouteUrl : null,
                    onShareGpx:
                        _waypoints.length >= 2 ? _downloadRouteGpx : null,
                    onWaze: _waypoints.isEmpty ? null : _openInWaze,
                  )
                : FilterSlider(
                    value: minTwistiness,
                    onChanged: (v) {
                      ref.read(filterProvider.notifier).state = v;
                      _scheduleFetch();
                    },
                    pavedOnly: ref.watch(pavedOnlyProvider),
                    onPavedChanged: (v) {
                      ref.read(pavedOnlyProvider.notifier).state = v;
                      _scheduleFetch();
                    },
                  ),
          ),

          // Floating buttons only outside plan mode, so they don't cover the
          // route bar's undo / clear / exit controls.
          if (!_planMode)
            Positioned(
              right: 16,
              bottom: 120,
              child: Column(
                children: [
                  FloatingActionButton(
                    heroTag: 'plan',
                    onPressed: _togglePlanMode,
                    child: const Icon(Icons.add_road),
                  ),
                  const SizedBox(height: 12),
                  FloatingActionButton(
                    heroTag: 'myloc',
                    onPressed: _goToMyLocation,
                    child: const Icon(Icons.my_location),
                  ),
                ],
              ),
            ),

          if (_fetching)
            const Positioned(
              top: 48, right: 16,
              child: SizedBox(
                width: 16, height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation(Color(0xFF00FF87)),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _PinMarker extends StatelessWidget {
  final int index;
  final bool selected;
  const _PinMarker({required this.index, this.selected = false});

  @override
  Widget build(BuildContext context) {
    final size = selected ? 32.0 : 26.0;
    return Center(
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: selected ? Colors.white : const Color(0xFF21E6FF),
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? const Color(0xFF21E6FF) : Colors.black,
            width: selected ? 3 : 2,
          ),
          boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 4)],
        ),
        alignment: Alignment.center,
        child: Text(
          '$index',
          style: TextStyle(
            color: selected ? const Color(0xFF0A7C8C) : Colors.black,
            fontWeight: FontWeight.bold,
            fontSize: 13,
          ),
        ),
      ),
    );
  }
}

class _RoutePlanBar extends StatelessWidget {
  final int count;
  final int? movingPin;
  final VoidCallback onExit;
  final VoidCallback? onUndo;
  final VoidCallback? onClear;
  final VoidCallback? onOpen;
  final VoidCallback? onCopy;
  final VoidCallback? onShareGpx;
  final VoidCallback? onWaze;

  const _RoutePlanBar({
    required this.count,
    required this.movingPin,
    required this.onExit,
    required this.onUndo,
    required this.onClear,
    required this.onOpen,
    required this.onCopy,
    required this.onShareGpx,
    required this.onWaze,
  });

  @override
  Widget build(BuildContext context) {
    final hint = movingPin != null
        ? 'Tap a new spot to move pin ${movingPin! + 1}'
        : count == 0
            ? 'Tap twisty roads to drop pins'
            : count == 1
                ? 'Add at least one more pin'
                : '$count stops · tap a pin to move it';
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      padding: EdgeInsets.only(
        left: 8,
        right: 8,
        top: 32,
        bottom: MediaQuery.of(context).padding.bottom + 12,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              IconButton(
                onPressed: onExit,
                icon: const Icon(Icons.close),
                color: Colors.white70,
                tooltip: 'Exit route planning',
              ),
              Expanded(
                child: Text(hint,
                    style: const TextStyle(color: Colors.white70, fontSize: 13)),
              ),
              IconButton(
                onPressed: onUndo,
                icon: const Icon(Icons.undo),
                color: Colors.white70,
                tooltip: 'Undo',
              ),
              IconButton(
                onPressed: onClear,
                icon: const Icon(Icons.delete_outline),
                color: Colors.white70,
                tooltip: 'Clear',
              ),
            ],
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: GestureDetector(
              onLongPress: onCopy,
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: onOpen,
                  icon: const Icon(Icons.navigation),
                  label: const Text('Open in Google Maps'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF21E6FF),
                    foregroundColor: Colors.black,
                    disabledBackgroundColor: const Color(0xFF30363D),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onShareGpx,
                    icon: const Icon(Icons.download, size: 18),
                    label: const Text('Download GPX'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF21E6FF),
                      side: const BorderSide(color: Color(0xFF30363D)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onWaze,
                    icon: const Icon(Icons.navigation_outlined, size: 18),
                    label: const Text('Waze → start'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF21E6FF),
                      side: const BorderSide(color: Color(0xFF30363D)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Pins are stops in Google Maps · long-press to copy link · '
            'GPX = via points in a riding app',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white38, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

import 'package:latlong2/latlong.dart';

class Road {
  final int id;
  final String name;
  final String highway;
  final double twistinessScore;
  final List<LatLng> points;

  // Surface + terrain (summary fields, present on /roads/bounds)
  final String surface; // paved | unpaved | unknown
  final double? maxGrade; // steepest %, null if elevation unavailable
  final double? avgGrade;
  final double? elevGain; // total ascent (m)

  // Detail-only fields (present on /roads/{id})
  final double? elevMin;
  final double? elevMax;
  final double? elevLoss;
  final List<double>? elevProfile;
  final double? lengthM;
  final String? access;

  const Road({
    required this.id,
    required this.name,
    required this.highway,
    required this.twistinessScore,
    required this.points,
    this.surface = 'unknown',
    this.maxGrade,
    this.avgGrade,
    this.elevGain,
    this.elevMin,
    this.elevMax,
    this.elevLoss,
    this.elevProfile,
    this.lengthM,
    this.access,
  });

  bool get isPaved => surface != 'unpaved';

  factory Road.fromFeature(Map<String, dynamic> feature) {
    final props = feature['properties'] as Map<String, dynamic>;
    final coords = (feature['geometry']['coordinates'] as List)
        .map((c) => LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()))
        .toList();

    double? d(String k) => (props[k] as num?)?.toDouble();
    List<double>? profile;
    if (props['elev_profile'] is List) {
      profile = (props['elev_profile'] as List)
          .map((e) => (e as num).toDouble())
          .toList();
    }

    return Road(
      id: (props['id'] as num).toInt(),
      name: (props['name'] as String?) ?? '',
      highway: props['highway'] as String,
      twistinessScore: (props['twistiness_score'] as num).toDouble(),
      points: coords,
      surface: (props['surface'] as String?) ?? 'unknown',
      maxGrade: d('max_grade'),
      avgGrade: d('avg_grade'),
      elevGain: d('elev_gain'),
      elevMin: d('elev_min'),
      elevMax: d('elev_max'),
      elevLoss: d('elev_loss'),
      elevProfile: profile,
      lengthM: d('length_m'),
      access: props['access'] as String?,
    );
  }
}

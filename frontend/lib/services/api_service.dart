import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api.dart';
import '../models/road.dart';

class ApiService {
  static final _client = http.Client();

  /// Raw GeoJSON body for the map viewport. Decoding + polyline building is the
  /// expensive part, so we hand the unparsed body to the caller to run off the
  /// UI isolate (via compute()) rather than decoding here on the main thread.
  static Future<String> fetchRoadsBody({
    required double minLat,
    required double minLon,
    required double maxLat,
    required double maxLon,
    required double minTwistiness,
    bool includeUnpaved = false,
    double minGrade = 0.0,
  }) async {
    final uri = Uri.parse('$kApiBase/api/v1/roads/bounds').replace(
      queryParameters: {
        'min_lat': minLat.toStringAsFixed(6),
        'min_lon': minLon.toStringAsFixed(6),
        'max_lat': maxLat.toStringAsFixed(6),
        'max_lon': maxLon.toStringAsFixed(6),
        'min_twistiness': minTwistiness.toStringAsFixed(2),
        'include_unpaved': includeUnpaved.toString(),
        if (minGrade > 0) 'min_grade': minGrade.toStringAsFixed(1),
      },
    );

    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('API ${response.statusCode}');
    }
    return response.body;
  }

  /// Full detail for one road, including the elevation profile.
  static Future<Road> fetchRoadDetail(int id) async {
    final uri = Uri.parse('$kApiBase/api/v1/roads/$id');
    final response = await _client.get(uri);
    if (response.statusCode != 200) {
      throw Exception('API ${response.statusCode}');
    }
    final feature = jsonDecode(response.body) as Map<String, dynamic>;
    return Road.fromFeature(feature);
  }

  /// URL that downloads a road segment as GPX.
  static String roadGpxUrl(int id) => '$kApiBase/api/v1/roads/$id/gpx';
}

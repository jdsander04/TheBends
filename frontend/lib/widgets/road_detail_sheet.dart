import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/road.dart';
import '../services/api_service.dart';
import '../screens/map_screen.dart' show twistinessColor;

class RoadDetailSheet extends StatefulWidget {
  final Road road;

  const RoadDetailSheet({super.key, required this.road});

  @override
  State<RoadDetailSheet> createState() => _RoadDetailSheetState();
}

class _RoadDetailSheetState extends State<RoadDetailSheet> {
  late Road _road;

  @override
  void initState() {
    super.initState();
    _road = widget.road;
    _loadDetail();
  }

  Future<void> _loadDetail() async {
    try {
      final detail = await ApiService.fetchRoadDetail(widget.road.id);
      if (mounted) setState(() => _road = detail);
    } catch (_) {
      // keep the summary we already have
    }
  }

  String _surfaceLabel(String s) => switch (s) {
        'paved' => 'Paved',
        'unpaved' => 'Unpaved',
        _ => 'Surface ?',
      };

  @override
  Widget build(BuildContext context) {
    final road = _road;
    final color = twistinessColor(road.twistinessScore);

    return DraggableScrollableSheet(
      initialChildSize: 0.45,
      minChildSize: 0.2,
      maxChildSize: 0.75,
      expand: false,
      builder: (context, scrollController) => Container(
        decoration: const BoxDecoration(
          color: Color(0xFF161B22),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                margin: const EdgeInsets.only(top: 12, bottom: 4),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFF30363D),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      road.name.isNotEmpty ? road.name : 'Unnamed Road',
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        _Chip(road.highway),
                        _Chip(
                          _surfaceLabel(road.surface),
                          bgColor: road.surface == 'unpaved'
                              ? const Color(0xFF6B4A1F)
                              : const Color(0xFF30363D),
                          textColor: road.surface == 'unpaved'
                              ? const Color(0xFFFFB85C)
                              : Colors.white70,
                        ),
                        _Chip(
                          '${(road.twistinessScore * 10).toStringAsFixed(1)}/10 twisty',
                          bgColor: color.withOpacity(0.2),
                          textColor: color,
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    _StatsRow(road: road),
                    const SizedBox(height: 22),
                    Text('TWISTINESS',
                        style: Theme.of(context).textTheme.labelSmall),
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: road.twistinessScore,
                        backgroundColor: const Color(0xFF30363D),
                        valueColor: AlwaysStoppedAnimation(color),
                        minHeight: 8,
                      ),
                    ),
                    if (road.elevProfile != null &&
                        road.elevProfile!.length > 2) ...[
                      const SizedBox(height: 22),
                      Text('ELEVATION',
                          style: Theme.of(context).textTheme.labelSmall),
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 70,
                        width: double.infinity,
                        child: CustomPaint(
                          painter: _ProfilePainter(road.elevProfile!, color),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('${road.elevMin?.round()} m',
                              style: const TextStyle(
                                  color: Colors.white38, fontSize: 11)),
                          Text('${road.elevMax?.round()} m',
                              style: const TextStyle(
                                  color: Colors.white38, fontSize: 11)),
                        ],
                      ),
                    ],
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () => launchUrl(
                          Uri.parse(ApiService.roadGpxUrl(road.id)),
                          mode: LaunchMode.externalApplication,
                        ),
                        icon: const Icon(Icons.download, size: 18),
                        label: const Text('Export GPX'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF00FF87),
                          side: const BorderSide(color: Color(0xFF00FF87)),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatsRow extends StatelessWidget {
  final Road road;
  const _StatsRow({required this.road});

  @override
  Widget build(BuildContext context) {
    final grade = road.maxGrade;
    final gain = road.elevGain;
    final len = road.lengthM;
    return Row(
      children: [
        _Stat(
          icon: Icons.trending_up,
          label: 'MAX GRADE',
          value: grade != null ? '${grade.toStringAsFixed(0)}%' : '—',
        ),
        _Stat(
          icon: Icons.terrain,
          label: 'CLIMB',
          value: gain != null ? '${gain.round()} m' : '—',
        ),
        _Stat(
          icon: Icons.straighten,
          label: 'LENGTH',
          value: len != null ? '${(len / 1000).toStringAsFixed(1)} km' : '—',
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  const _Stat({required this.icon, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Icon(icon, size: 18, color: const Color(0xFF00FF87)),
          const SizedBox(height: 6),
          Text(value,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.bold)),
          const SizedBox(height: 2),
          Text(label,
              style: const TextStyle(color: Colors.white38, fontSize: 10)),
        ],
      ),
    );
  }
}

class _ProfilePainter extends CustomPainter {
  final List<double> elev;
  final Color color;
  _ProfilePainter(this.elev, this.color);

  @override
  void paint(Canvas canvas, Size size) {
    if (elev.length < 2) return;
    final lo = elev.reduce((a, b) => a < b ? a : b);
    final hi = elev.reduce((a, b) => a > b ? a : b);
    final range = (hi - lo).abs() < 1 ? 1.0 : (hi - lo);

    Offset at(int i) {
      final x = size.width * i / (elev.length - 1);
      final y = size.height - (elev[i] - lo) / range * (size.height - 6) - 3;
      return Offset(x, y);
    }

    final line = Path()..moveTo(at(0).dx, at(0).dy);
    for (int i = 1; i < elev.length; i++) {
      line.lineTo(at(i).dx, at(i).dy);
    }
    final fill = Path.from(line)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();

    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [color.withOpacity(0.35), color.withOpacity(0.02)],
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      line,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_ProfilePainter old) => old.elev != elev;
}

class _Chip extends StatelessWidget {
  final String label;
  final Color bgColor;
  final Color textColor;

  const _Chip(
    this.label, {
    this.bgColor = const Color(0xFF30363D),
    this.textColor = Colors.white70,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: TextStyle(color: textColor, fontSize: 12)),
    );
  }
}

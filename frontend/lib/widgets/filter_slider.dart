import 'package:flutter/material.dart';

class FilterSlider extends StatelessWidget {
  final double value;
  final ValueChanged<double> onChanged;
  final bool pavedOnly;
  final ValueChanged<bool> onPavedChanged;

  const FilterSlider({
    super.key,
    required this.value,
    required this.onChanged,
    required this.pavedOnly,
    required this.onPavedChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [Colors.black87, Colors.transparent],
        ),
      ),
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 32,
        bottom: MediaQuery.of(context).padding.bottom + 12,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('MIN TWISTINESS',
                  style: Theme.of(context).textTheme.labelSmall),
              Row(
                children: [
                  _SurfacePill(
                    label: 'Paved',
                    selected: pavedOnly,
                    onTap: () => onPavedChanged(true),
                  ),
                  const SizedBox(width: 6),
                  _SurfacePill(
                    label: '+ Gravel',
                    selected: !pavedOnly,
                    onTap: () => onPavedChanged(false),
                  ),
                ],
              ),
            ],
          ),
          Row(
            children: [
              Expanded(
                child: Slider(
                  value: value,
                  min: 0.0,
                  max: 1.0,
                  divisions: 20,
                  onChanged: onChanged,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                (value * 10).toStringAsFixed(1),
                style: const TextStyle(
                  color: Color(0xFF00FF87),
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SurfacePill extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _SurfacePill({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF00FF87) : const Color(0xFF30363D),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.black : Colors.white70,
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

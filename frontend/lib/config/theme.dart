import 'package:flutter/material.dart';

class AppTheme {
  // Palette
  static const background = Color(0xFF0D1117);
  static const surface = Color(0xFF161B22);
  static const border = Color(0xFF30363D);
  static const accent = Color(0xFF00FF87); // electric green

  static final dark = ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: background,
    colorScheme: const ColorScheme.dark(
      surface: surface,
      primary: accent,
      onPrimary: background,
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: accent,
      thumbColor: accent,
      overlayColor: accent.withOpacity(0.15),
      inactiveTrackColor: border,
      trackHeight: 3,
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: surface,
      foregroundColor: accent,
      elevation: 4,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
    ),
    textTheme: const TextTheme(
      headlineSmall: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
      bodyMedium: TextStyle(color: Colors.white70),
      labelSmall: TextStyle(color: Colors.white54, letterSpacing: 1.2),
    ),
  );
}

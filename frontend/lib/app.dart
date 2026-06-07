import 'package:flutter/material.dart';
import 'config/theme.dart';
import 'screens/map_screen.dart';

class TheBendsApp extends StatelessWidget {
  const TheBendsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TheBends',
      theme: AppTheme.dark,
      home: const MapScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

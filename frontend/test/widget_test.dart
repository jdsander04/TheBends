import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:thebends/screens/map_screen.dart';

void main() {
  test('twistinessColor maps score bands to the right colors', () {
    expect(twistinessColor(0.90), const Color(0xFFFF0090)); // tight
    expect(twistinessColor(0.75), const Color(0xFFFF2222)); // good
    expect(twistinessColor(0.55), const Color(0xFFFF6B00)); // moderate
    expect(twistinessColor(0.20), const Color(0xFFFFB300)); // gentle
  });
}

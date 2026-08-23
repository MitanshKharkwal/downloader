import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SpeedSparkline extends StatefulWidget {
  const SpeedSparkline({
    super.key,
    required this.speedBytesPerSec,
    required this.active,
  });

  final double speedBytesPerSec;
  final bool active;

  @override
  State<SpeedSparkline> createState() => _SpeedSparklineState();
}

class _SpeedSparklineState extends State<SpeedSparkline> {
  final List<double> _history = <double>[];
  static const int _maxSamples = 30;

  @override
  void initState() {
    super.initState();
    _addSample(widget.speedBytesPerSec);
  }

  @override
  void didUpdateWidget(SpeedSparkline oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.active && widget.active) {
      _history.clear();
    }
    if (oldWidget.speedBytesPerSec != widget.speedBytesPerSec) {
      _addSample(widget.speedBytesPerSec);
    }
  }

  void _addSample(double speed) {
    _history.add(speed);
    if (_history.length > _maxSamples) {
      _history.removeAt(0);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_history.isEmpty || _history.every((double v) => v == 0.0)) {
      return const SizedBox(width: 60, height: 20);
    }

    double maxY = _history.reduce((double a, double b) => a > b ? a : b);
    if (maxY == 0) maxY = 1; // Prevent division by zero

    final List<FlSpot> spots = <FlSpot>[];
    for (int i = 0; i < _history.length; i++) {
      spots.add(FlSpot(i.toDouble(), _history[i]));
    }

    return SizedBox(
      width: 60,
      height: 20,
      child: LineChart(
        LineChartData(
          minX: 0,
          maxX: (_history.length - 1).clamp(1, _maxSamples - 1).toDouble(),
          minY: 0,
          maxY: maxY * 1.1, // 10% headroom
          lineTouchData: const LineTouchData(enabled: false),
          gridData: const FlGridData(show: false),
          titlesData: const FlTitlesData(show: false),
          borderData: FlBorderData(show: false),
          lineBarsData: <LineChartBarData>[
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: AppColors.accent,
              barWidth: 1.5,
              isStrokeCapRound: true,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                color: AppColors.accentSoft,
              ),
            ),
          ],
        ),
        duration: const Duration(milliseconds: 0),
      ),
    );
  }
}

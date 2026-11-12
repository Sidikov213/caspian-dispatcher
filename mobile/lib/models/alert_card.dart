/// Компактная карточка алерта из `Alert.card` (контракт с бэком).
class AlertCardData {
  const AlertCardData({
    required this.kind,
    required this.headline,
    required this.subtitle,
    required this.period,
    required this.metrics,
    this.route,
    this.impact,
    this.decision,
  });

  final String kind; // ice | storm | congestion | customs | …
  final String headline;
  final String subtitle;
  final String period;
  final List<AlertCardMetric> metrics;
  final AlertCardRoute? route;
  final AlertCardImpact? impact;
  final AlertCardDecision? decision;

  factory AlertCardData.fromJson(Map<String, dynamic> json) {
    final metricsRaw = json['metrics'];
    final metrics = <AlertCardMetric>[];
    if (metricsRaw is List) {
      for (final m in metricsRaw) {
        if (m is Map) {
          metrics.add(
            AlertCardMetric(
              key: '${m['key'] ?? ''}',
              label: '${m['label'] ?? ''}',
              value: '${m['value'] ?? ''}',
            ),
          );
        }
      }
    }

    AlertCardRoute? route;
    final routeRaw = json['route'];
    if (routeRaw is Map) {
      route = AlertCardRoute(
        sailingLabel: routeRaw['sailing_label']?.toString(),
        from: routeRaw['from']?.toString(),
        to: routeRaw['to']?.toString(),
        departure: routeRaw['departure']?.toString(),
      );
    }

    AlertCardImpact? impact;
    final impactRaw = json['impact'];
    if (impactRaw is Map) {
      impact = AlertCardImpact(
        shipments: (impactRaw['shipments'] as num?)?.toInt(),
        weightT: (impactRaw['weight_t'] as num?)?.toDouble(),
        maxRiskPct: (impactRaw['max_risk_pct'] as num?)?.toInt(),
      );
    }

    AlertCardDecision? decision;
    final decisionRaw = json['decision'];
    if (decisionRaw is Map) {
      decision = AlertCardDecision(
        status: decisionRaw['status']?.toString(),
        title: decisionRaw['title']?.toString(),
        detail: decisionRaw['detail']?.toString(),
        via: decisionRaw['via']?.toString(),
        viaLabel: decisionRaw['via_label']?.toString(),
        acceptedByName: decisionRaw['accepted_by_name']?.toString(),
      );
    }

    return AlertCardData(
      kind: '${json['kind'] ?? ''}',
      headline: '${json['headline'] ?? ''}',
      subtitle: '${json['subtitle'] ?? ''}',
      period: '${json['period'] ?? ''}',
      metrics: metrics,
      route: route,
      impact: impact,
      decision: decision,
    );
  }

  /// Заглушка до появления `card` на бэке (ледовый сценарий).
  factory AlertCardData.stub() => const AlertCardData(
    kind: 'ice',
    headline: 'Лёд на Волго-Каспийском канале',
    subtitle: '3 груза под риском',
    period: '14 ноя 07:00 – 15 ноя 02:00',
    metrics: [
      AlertCardMetric(key: 'ice', label: 'Толщина льда', value: 'до 18 см'),
      AlertCardMetric(key: 'limit', label: 'Предел проводки', value: '12 см'),
    ],
    route: AlertCardRoute(
      sailingLabel: 'Паром А',
      from: 'Астрахань',
      to: 'Энзели',
      departure: '14 ноя, 15:00',
    ),
    impact: AlertCardImpact(shipments: 3, weightT: 120, maxRiskPct: 82),
    decision: AlertCardDecision(
      status: 'accepted',
      title: 'Через Махачкалу',
      detail: '+6 ч к плану',
      via: 'web',
      viaLabel: 'сайт',
      acceptedByName: 'Логист (демо)',
    ),
  );
}

class AlertCardMetric {
  const AlertCardMetric({
    required this.key,
    required this.label,
    required this.value,
  });

  final String key;
  final String label;
  final String value;
}

class AlertCardRoute {
  const AlertCardRoute({
    this.sailingLabel,
    this.from,
    this.to,
    this.departure,
  });

  final String? sailingLabel;
  final String? from;
  final String? to;
  final String? departure;

  String get line {
    final parts = <String>[];
    if (sailingLabel != null && sailingLabel!.isNotEmpty) {
      parts.add(sailingLabel!);
    }
    if (from != null && to != null) {
      parts.add('$from → $to');
    } else if (from != null) {
      parts.add(from!);
    } else if (to != null) {
      parts.add(to!);
    }
    if (departure != null && departure!.isNotEmpty) {
      parts.add(departure!);
    }
    return parts.join(' · ');
  }
}

class AlertCardImpact {
  const AlertCardImpact({this.shipments, this.weightT, this.maxRiskPct});

  final int? shipments;
  final double? weightT;
  final int? maxRiskPct;

  String? get line {
    final parts = <String>[];
    if (shipments != null) {
      final n = shipments!;
      final word = (n % 10 == 1 && n % 100 != 11)
          ? 'груз'
          : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20))
          ? 'груза'
          : 'грузов';
      parts.add('$n $word');
    }
    if (weightT != null) {
      final w = weightT!;
      final raw = w % 1 == 0 ? w.toInt().toString() : '$w'.replaceAll('.', ',');
      parts.add('$raw т');
    }
    if (maxRiskPct != null) {
      parts.add('риск до $maxRiskPct%');
    }
    if (parts.isEmpty) return null;
    return parts.join(' · ');
  }
}

class AlertCardDecision {
  const AlertCardDecision({
    this.status,
    this.title,
    this.detail,
    this.via,
    this.viaLabel,
    this.acceptedByName,
  });

  final String? status;
  final String? title;
  final String? detail;
  final String? via;
  final String? viaLabel;
  final String? acceptedByName;

  List<String> get chips {
    final out = <String>[];
    if (title != null && title!.isNotEmpty) out.add(title!);
    if (detail != null && detail!.isNotEmpty) out.add(detail!);
    if (acceptedByName != null && acceptedByName!.isNotEmpty) {
      out.add(acceptedByName!);
    } else if (viaLabel != null && viaLabel!.isNotEmpty) {
      out.add(viaLabel!);
    }
    return out;
  }
}

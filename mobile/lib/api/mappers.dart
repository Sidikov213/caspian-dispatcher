import '../models/alert_card.dart';
import '../models/cargo.dart';

/// Заглушка `Alert.card` только для вёрстки.
/// Включить: `--dart-define=ALERT_CARD_STUB=true`. На показе по умолчанию выкл.
const _alertCardStubEnabled = bool.fromEnvironment(
  'ALERT_CARD_STUB',
  defaultValue: false,
);

/// Имя узла только из `/api/graph`. Без локального словаря.
String nodeLabel(String id, [Map<String, String>? fromGraph]) {
  if (fromGraph != null && fromGraph.containsKey(id)) return fromGraph[id]!;
  return id;
}

CargoStatus mapDisplayStatus(String? raw) => switch (raw) {
  'planned' => CargoStatus.planned,
  'in_transit' => CargoStatus.inTransit,
  'at_risk' => CargoStatus.atRisk,
  'rerouted' => CargoStatus.rerouted,
  'delivered' => CargoStatus.delivered,
  _ => CargoStatus.unknown,
};

PassStatus mapPassState(String? raw) => switch (raw) {
  'active' => PassStatus.active,
  'reissue_pending' => PassStatus.awaitingReissue,
  'reissued' => PassStatus.reissued,
  'revoked' => PassStatus.invalid,
  'none' || null || '' => PassStatus.none,
  _ => PassStatus.unknown,
};

PassStatus mapPassApiStatus(String? raw) => switch (raw) {
  'active' => PassStatus.active,
  'reissued' => PassStatus.reissued,
  'revoked' => PassStatus.invalid,
  _ => PassStatus.unknown,
};

String fmtTons(num t) {
  final v = t % 1 == 0
      ? t.toInt().toString()
      : t.toString().replaceAll('.', ',');
  return '$v т';
}

/// Как на бэке `k_rub`: «597 тыс ₽».
num? _asNum(Object? v) {
  if (v is num) return v;
  if (v is String) return num.tryParse(v.replaceAll(' ', '').replaceAll(',', '.'));
  return null;
}

String fmtRub(num n) {
  final a = n.abs();
  if (a >= 1000000) {
    final m = n / 1000000;
    final raw = m % 1 == 0
        ? m.toInt().toString()
        : m.toStringAsFixed(1).replaceAll('.', ',');
    return '$raw млн ₽';
  }
  if (a >= 1000) return '${(n / 1000).round()} тыс ₽';
  return '${n.round()} ₽';
}

String fmtCargoHours(num hours) => '${hours.round()}';

/// `stats.co2_saved_pct` 6.9 → «−6,9%»; 0/null → null.
String? fmtCo2SavedPct(num? pct) {
  if (pct == null || pct == 0) return null;
  final raw = pct % 1 == 0
      ? pct.toInt().toString()
      : pct.toString().replaceAll('.', ',');
  return '−$raw%';
}

/// Москва (UTC+3), месяц «мая», формат «12 ноя, 14:30».
String fmtDt(String? iso) {
  if (iso == null || iso.isEmpty) return '-';
  final parsed = DateTime.tryParse(iso);
  if (parsed == null) return iso;
  final dt = parsed.toUtc().add(const Duration(hours: 3));
  const months = [
    'янв',
    'фев',
    'мар',
    'апр',
    'мая',
    'июн',
    'июл',
    'авг',
    'сен',
    'окт',
    'ноя',
    'дек',
  ];
  final hh = dt.hour.toString().padLeft(2, '0');
  final mm = dt.minute.toString().padLeft(2, '0');
  return '${dt.day} ${months[dt.month - 1]}, $hh:$mm';
}

String shortHash(String? h) {
  if (h == null || h.isEmpty) return '-';
  if (h.length <= 8) return h;
  return '${h.substring(0, 4)}…${h.substring(h.length - 4)}';
}

String numberFromId(String id) {
  final m = RegExp(r'(\d+)').firstMatch(id);
  if (m == null) return id;
  return '№${m.group(1)!.padLeft(2, '0')}';
}

String fmtHoursDelta(num hours) {
  if (hours == 0) return '0 ч';
  final sign = hours > 0 ? '+' : '−';
  return '$sign${hours.abs().round()} ч';
}

String cargoTypeLabel(String type) => switch (type) {
  'grain' => 'Сыпучий груз',
  'metal' => 'Металлопрокат',
  'equipment' => 'Генеральный груз',
  'textile' => 'Генеральный груз',
  'fertilizer' => 'Навалочный груз',
  _ => type.isEmpty ? 'Груз' : type,
};

DateTime? _mskDt(String? iso) {
  final parsed = DateTime.tryParse(iso ?? '');
  if (parsed == null) return null;
  return parsed.toUtc().add(const Duration(hours: 3));
}

String fmtTime(String? iso) {
  final dt = _mskDt(iso);
  if (dt == null) return '-';
  final hh = dt.hour.toString().padLeft(2, '0');
  final mm = dt.minute.toString().padLeft(2, '0');
  return '$hh:$mm';
}

String? _addHoursIso(String? iso, num hours) {
  final parsed = DateTime.tryParse(iso ?? '');
  if (parsed == null) return null;
  return parsed
      .toUtc()
      .add(Duration(minutes: (hours * 60).round()))
      .toIso8601String();
}

String stageTimeLine({
  required String? plannedIso,
  String? forecastIso,
  bool done = false,
}) {
  final planned = fmtDt(plannedIso);
  if (forecastIso == null || forecastIso.isEmpty) {
    return done ? '$planned ✓' : planned;
  }
  final p = _mskDt(plannedIso);
  final f = _mskDt(forecastIso);
  final sameDay = p != null &&
      f != null &&
      p.year == f.year &&
      p.month == f.month &&
      p.day == f.day;
  final to = sameDay ? fmtTime(forecastIso) : fmtDt(forecastIso);
  return '$planned → $to';
}

/// Как `routeStops` на сайте: узлы смены режима + старт/финиш.
List<RouteStage> stagesFromRoute(
  Map<String, dynamic>? route,
  int? currentLeg,
  Map<String, String> nodes, {
  num departureShiftH = 0,
}) {
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  if (legs.isEmpty) return const [];

  final first = legs.first;
  final firstMode = '${first['mode'] ?? 'rail'}';
  final firstStatus = '${first['status'] ?? ''}';
  final departed = firstStatus == 'done' || firstStatus == 'active';
  final stages = <RouteStage>[
    RouteStage(
      title: nodeLabel('${first['from']}', nodes),
      subtitle: departed ? 'Пройден' : 'Отправление',
      mode: firstMode,
      planned: fmtDt(first['planned_start']?.toString()),
      forecast: '',
      timeLine: stageTimeLine(
        plannedIso: first['planned_start']?.toString(),
        done: departed,
      ),
      done: departed,
      current: !departed,
      warning: false,
    ),
  ];

  for (var i = 0; i < legs.length; i++) {
    final leg = legs[i];
    final next = i + 1 < legs.length ? legs[i + 1] : null;
    final mode = '${leg['mode'] ?? 'rail'}';
    final status = '${leg['status'] ?? ''}';
    final delay = (leg['predicted_delay_h'] as num?) ?? 0;

    if (next != null && '${next['mode']}' == mode) continue;

    if (next != null && '${next['status']}' == 'blocked') {
      final shift = departureShiftH > 0
          ? departureShiftH
          : ((next['predicted_delay_h'] as num?) ?? 0);
      final plannedIso = next['planned_start']?.toString();
      final forecastIso =
          shift > 0 ? _addHoursIso(plannedIso, shift) : null;
      final sea = '${next['mode']}' == 'sea';
      stages.add(
        RouteStage(
          title: nodeLabel('${leg['to']}', nodes),
          subtitle: sea
              ? 'Стыковка с паромом · под угрозой'
              : 'Стыковка · под угрозой',
          mode: mode,
          planned: fmtDt(plannedIso),
          forecast: forecastIso == null ? '' : fmtDt(forecastIso),
          timeLine: stageTimeLine(
            plannedIso: plannedIso,
            forecastIso: forecastIso,
          ),
          done: false,
          current: true,
          warning: true,
        ),
      );
      continue;
    }

    final forecastIso =
        delay > 0 ? _addHoursIso(leg['planned_end']?.toString(), delay) : null;
    final done = status == 'done' || status == 'completed';
    final active = status == 'active';
    stages.add(
      RouteStage(
        title: nodeLabel('${leg['to']}', nodes),
        subtitle: done
            ? 'Пройден'
            : active
                ? 'В пути'
                : 'Впереди',
        mode: mode,
        planned: fmtDt(leg['planned_end']?.toString()),
        forecast: forecastIso == null ? '' : fmtDt(forecastIso),
        timeLine: stageTimeLine(
          plannedIso: leg['planned_end']?.toString(),
          forecastIso: forecastIso,
          done: done,
        ),
        done: done,
        current: currentLeg != null
            ? leg['index'] == currentLeg
            : active,
        warning: delay > 0,
      ),
    );
  }
  return stages;
}

String routeLabel(Map<String, dynamic>? route, Map<String, String> nodes) {
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  if (legs.isEmpty) return '-';
  final ids = <String>[
    '${legs.first['from']}',
    ...legs.map((l) => '${l['to']}'),
  ];
  return ids.map((id) => nodeLabel(id, nodes)).join(' → ');
}

Map<String, String> nodesFromGraph(Map<String, dynamic> graph) {
  final nodes =
      (graph['nodes'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  return {
    for (final n in nodes)
      if (n['id'] != null)
        '${n['id']}': '${n['name'] ?? n['label'] ?? n['id']}',
  };
}

Map<String, GraphEdgeInfo> edgesFromGraph(Map<String, dynamic> graph) {
  final edges =
      (graph['edges'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  return {
    for (final e in edges)
      if (e['id'] != null)
        '${e['id']}': GraphEdgeInfo(
          id: '${e['id']}',
          mode: '${e['mode'] ?? 'rail'}',
          distanceKm: ((e['distance_km'] as num?) ?? 0).toDouble(),
          co2GPerTkm: ((e['co2_g_per_tkm'] as num?) ?? 0).toDouble(),
        ),
  };
}

({double rail, double sea, double road}) co2ByMode({
  required Map<String, dynamic>? route,
  required double weightTons,
  required Map<String, GraphEdgeInfo> edges,
}) {
  var rail = 0.0;
  var sea = 0.0;
  var road = 0.0;
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  for (final leg in legs) {
    final edge = edges['${leg['edge_id']}'];
    if (edge == null) continue;
    final kg = weightTons * edge.distanceKm * edge.co2GPerTkm / 1000;
    switch ('${leg['mode'] ?? edge.mode}') {
      case 'sea':
        sea += kg;
      case 'road':
        road += kg;
      default:
        rail += kg;
    }
  }
  return (rail: rail, sea: sea, road: road);
}

Cargo shipmentToCargo(
  Map<String, dynamic> sh, {
  Map<String, String> nodes = const {},
  Map<String, GraphEdgeInfo> edges = const {},
  Map<String, dynamic>? pass,
}) {
  final risk = sh['risk'] as Map<String, dynamic>? ?? const {};
  final miss = (risk['miss_probability'] as num?)?.toDouble() ?? 0;
  final factors =
      (risk['factors'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  final driversRaw = risk['probability_drivers'];
  final drivers = driversRaw is List
      ? driversRaw.cast<Map<String, dynamic>>()
      : const <Map<String, dynamic>>[];
  final route = sh['route'] as Map<String, dynamic>?;
  final currentLeg = sh['current_leg'] as int?;
  final departureShift =
      (risk['departure_shift_h'] as num?)?.toDouble() ?? 0;
  final next = currentLeg == null
      ? nodeLabel('${sh['destination']}', nodes)
      : () {
          final legs =
              (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ??
              const [];
          for (final leg in legs) {
            if (leg['index'] == currentLeg) {
              return nodeLabel('${leg['to']}', nodes);
            }
          }
          return nodeLabel('${sh['destination']}', nodes);
        }();

  final passState = mapPassState(sh['pass_state']?.toString());
  final apiPassStatus = pass == null
      ? passState
      : mapPassApiStatus(pass['status']?.toString());
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  final hasFerry = legs.any((l) => l['sailing_id'] != null);
  final co2 = co2ByMode(
    route: route,
    weightTons: ((sh['weight_t'] as num?) ?? 0).toDouble(),
    edges: edges,
  );
  final routeTotal = (route?['total_co2_kg'] as num?)?.toDouble();
  final partsSum = co2.rail + co2.sea + co2.road;
  final totalCo2 = (routeTotal != null && routeTotal > 0) ? routeTotal : partsSum;
  final cargoType = '${sh['cargo_type'] ?? ''}';
  final riskLevel = '${risk['level'] ?? 'low'}';

  return Cargo(
    id: '${sh['id']}',
    number: numberFromId('${sh['id']}'),
    title: '${sh['title'] ?? ''}',
    weight: fmtTons((sh['weight_t'] as num?) ?? 0),
    weightTons: ((sh['weight_t'] as num?) ?? 0).toDouble(),
    cargoType: cargoType,
    cargoTypeLabel: cargoTypeLabel(cargoType),
    route: routeLabel(route, nodes),
    origin: nodeLabel('${sh['origin']}', nodes),
    destination: nodeLabel('${sh['destination']}', nodes),
    status: mapDisplayStatus(sh['display_status']?.toString()),
    nextPoint: next,
    arrival: fmtDt(sh['eta']?.toString()),
    missProbability: miss,
    riskLevel: riskLevel,
    departureShiftH: departureShift,
    arrivalDelayH: (risk['arrival_delay_h'] as num?)?.toDouble(),
    riskFactors: [
      for (final f in factors)
        RiskFactor(
          name: '${f['name'] ?? ''}',
          label: '${f['label'] ?? ''}',
          impactHours: ((f['impact_hours'] as num?) ?? 0).toDouble(),
        ),
    ],
    probabilityDrivers: [
      for (final d in drivers)
        ProbabilityDriver(
          name: '${d['name'] ?? ''}',
          label: '${d['label'] ?? ''}',
          impactPp: ((d['impact_pp'] as num?) ?? 0).toDouble(),
        ),
    ],
    routeChanged: sh['rerouted'] == true,
    routeChangedNote: sh['rerouted'] == true ? 'Маршрут изменён' : null,
    passStatus: passState == PassStatus.awaitingReissue
        ? PassStatus.awaitingReissue
        : apiPassStatus,
    passId: pass?['id']?.toString() ?? sh['pass_id']?.toString(),
    passPort: pass == null
        ? null
        : nodeLabel('${pass['checkpoint_node']}', nodes),
    passValidUntil: pass == null
        ? null
        : fmtDt(pass['valid_until']?.toString()),
    passRecord: pass?['id']?.toString() ?? sh['pass_id']?.toString(),
    passHash: shortHash(pass?['doc_hash']?.toString()),
    passToken: pass?['token']?.toString(),
    passDocHash: pass?['doc_hash']?.toString(),
    passBlockHash: pass?['block_hash']?.toString(),
    hasFerry: hasFerry,
    totalCo2Kg: totalCo2,
    co2RailKg: co2.rail,
    co2SeaKg: co2.sea,
    co2RoadKg: co2.road,
    stages: stagesFromRoute(
      route,
      currentLeg,
      nodes,
      departureShiftH: departureShift,
    ),
    cancellationForecast: riskLevel == 'high' || miss >= 0.7,
  );
}

/// Все точки из `/weather.points`, имена из graph.
List<WavePort> wavesFromWeather(
  Map<String, dynamic> weather,
  Map<String, String> nodes,
) {
  final points =
      (weather['points'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  return [
    for (final point in points)
      () {
        final id = '${point['node_id'] ?? ''}';
        final h = (point['wave_height_m'] as num?)?.toDouble() ?? 0;
        return WavePort(
          nodeId: id,
          name: nodeLabel(id, nodes),
          heightM: h,
          heightLabel: '${h.toStringAsFixed(1).replaceAll('.', ',')} м',
        );
      }(),
  ];
}

OverviewData buildOverview({
  required Map<String, dynamic> stats,
  required Map<String, dynamic> weather,
  required List<Map<String, dynamic>> alerts,
  required List<Cargo> cargos,
  Map<String, String> nodes = const {},
}) {
  final waves = wavesFromWeather(weather, nodes);
  final updated = fmtDt(weather['updated_at']?.toString());
  final sourceRaw = '${weather['source'] ?? ''}';
  final source = switch (sourceRaw) {
    'open-meteo' => 'Метеосервис',
    'cache' => 'Кэш',
    '' || '-' => '—',
    _ => sourceRaw,
  };
  final stale = weather['stale'] == true;

  String? title;
  String? body;
  String? cargoId;
  String? decision;
  AlertCardData? card;

  if (alerts.isNotEmpty) {
    final sorted = [...alerts]
      ..sort((a, b) {
        final sa = '${a['status']}';
        final sb = '${b['status']}';
        if (sa == 'new' && sb != 'new') return -1;
        if (sb == 'new' && sa != 'new') return 1;
        return 0;
      });
    final a = sorted.first;
    title = '${a['title'] ?? 'Алерт'}';
    body = '${a['text'] ?? ''}';
    final items =
        (a['items'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
    if (items.isNotEmpty) {
      cargoId = items.first['shipment_id']?.toString();
    }
    decision = decisionSummaryFromAlert(a);

    final rawCard = a['card'];
    if (rawCard is Map<String, dynamic>) {
      card = AlertCardData.fromJson(rawCard);
    } else if (rawCard is Map) {
      card = AlertCardData.fromJson(Map<String, dynamic>.from(rawCard));
    } else if (_alertCardStubEnabled) {
      card = AlertCardData.stub();
    }
  }

  // Если /stats ещё 0, а решение уже в алерте — берём totals с алерта.
  num savedRub = _asNum(stats['saved_rub']) ?? 0;
  num savedHours = _asNum(stats['saved_hours']) ?? 0;
  num? co2Pct = _asNum(stats['co2_saved_pct']);
  if (savedRub == 0) {
    for (final a in alerts) {
      if ('${a['status']}' != 'accepted') continue;
      final totals = a['totals'];
      if (totals is! Map) continue;
      savedRub = _asNum(totals['saved_rub']) ?? savedRub;
      savedHours = _asNum(totals['saved_hours']) ?? savedHours;
      final deltaPct = _asNum(totals['co2_delta_pct']);
      if (deltaPct != null) co2Pct = deltaPct.abs();
      break;
    }
  }

  return OverviewData(
    shipmentsTotal:
        (stats['shipments_total'] as num?)?.toInt() ?? cargos.length,
    atRisk:
        (stats['at_risk'] as num?)?.toInt() ??
        cargos.where((c) => c.displayStatus == CargoStatus.atRisk).length,
    economyRub: fmtRub(savedRub),
    economyCargoHours: fmtCargoHours(savedHours),
    economyCo2Pct: fmtCo2SavedPct(co2Pct),
    waves: waves,
    weatherUpdatedLabel: updated,
    weatherSource: source,
    weatherStale: stale,
    lastAlertTitle: title,
    lastAlertBody: body,
    lastAlertCargoId: cargoId,
    decisionNote: decision,
    lastAlertCard: card,
  );
}

/// Текст решения только из полей API (`options`, `accepted_by`, `status_note`).
String? decisionSummaryFromAlert(Map<String, dynamic> alert) {
  final status = '${alert['status']}';
  final options =
      (alert['options'] as List?)?.cast<Map<String, dynamic>>() ?? const [];

  Map<String, dynamic>? recommendedOption() {
    for (final o in options) {
      if (o['recommended'] == true) return o;
    }
    return options.isEmpty ? null : options.first;
  }

  if (status == 'new') {
    final starts = (alert['starts_in_h'] as num?)?.toDouble();
    final when = starts == null ? '' : ' · через ${starts.round()} ч';
    final opt = recommendedOption();
    final optTitle = opt?['title']?.toString();
    if (optTitle != null && optTitle.isNotEmpty) {
      return 'Ожидает решения · $optTitle$when';
    }
    return 'Ожидает решения логиста$when';
  }

  if (status == 'rejected') {
    for (final o in options) {
      if (o['id']?.toString() == 'wait') {
        final t = o['title']?.toString();
        if (t != null && t.isNotEmpty) return t;
      }
    }
    final note = alert['status_note']?.toString();
    if (note != null && note.isNotEmpty) return note;
    return null;
  }

  if (status == 'superseded') {
    final note = alert['status_note']?.toString();
    if (note != null && note.isNotEmpty) return note;
    return null;
  }

  if (status != 'accepted') return null;

  final opt = recommendedOption();
  final title = opt?['title']?.toString();
  final delay = (opt?['delay_vs_plan_h'] as num?)?.toDouble() ??
      (() {
        final items =
            (alert['items'] as List?)?.cast<Map<String, dynamic>>() ??
            const [];
        if (items.isEmpty) return null;
        return (items.first['delay_vs_plan_h'] as num?)?.toDouble();
      })();

  final parts = <String>[];
  if (title != null && title.isNotEmpty) {
    parts.add(title);
  }
  if (delay != null) {
    parts.add('+${delay.round()} ч к плану');
  }

  final by = alert['accepted_by'];
  if (by is Map && by['name'] != null && '${by['name']}'.isNotEmpty) {
    parts.add('${by['name']}');
  } else {
    final via = switch (alert['accepted_via']?.toString()) {
      'web' => 'сайт',
      'telegram' => 'Телеграм',
      _ => null,
    };
    if (via != null) parts.add(via);
  }

  if (parts.isEmpty) return null;
  return parts.join(' · ');
}

DispatcherDecision decisionForCargo({
  required Cargo cargo,
  required List<Map<String, dynamic>> alerts,
}) {
  for (final a in alerts) {
    final items =
        (a['items'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
    final hit = items.any((i) => i['shipment_id'] == cargo.id);
    if (!hit) continue;
    final status = '${a['status']}';
    if (status == 'new') {
      return DispatcherDecision(
        waiting: true,
        summary: decisionSummaryFromAlert(a) ?? 'Ожидает решения логиста',
        alertId: a['id']?.toString(),
      );
    }
    return DispatcherDecision(
      waiting: false,
      summary: decisionSummaryFromAlert(a),
      alertId: a['id']?.toString(),
    );
  }
  if (cargo.displayStatus == CargoStatus.atRisk) {
    return const DispatcherDecision(
      waiting: true,
      summary: 'Ожидает решения логиста',
    );
  }
  return const DispatcherDecision(waiting: false, summary: null);
}

Map<String, dynamic> invoiceToApiFields(InvoiceFields f) {
  final weightTons = double.tryParse(
    f.weight.replaceAll(' ', '').replaceAll(',', '.'),
  );
  return {
    'seller': f.seller,
    'buyer': f.buyer,
    'goods': f.product,
    'hs_code': f.hsCode,
    'weight_kg': weightTons == null ? null : weightTons * 1000,
    'value': double.tryParse(f.amount.replaceAll(' ', '').replaceAll(',', '.')),
    'currency': f.currency,
    'origin_country': f.origin,
  };
}

InvoiceFields documentFieldsToInvoice(Map<String, dynamic>? fields) {
  if (fields == null) return const InvoiceFields();
  final kg = fields['weight_kg'];
  String weight = '';
  if (kg is num) {
    weight = (kg / 1000).toString().replaceAll('.', ',');
  }
  return InvoiceFields(
    seller: '${fields['seller'] ?? ''}',
    buyer: '${fields['buyer'] ?? ''}',
    product: '${fields['goods'] ?? ''}',
    hsCode: '${fields['hs_code'] ?? ''}',
    weight: weight,
    amount: '${fields['value'] ?? ''}',
    currency: '${fields['currency'] ?? 'USD'}',
    origin: '${fields['origin_country'] ?? ''}',
  );
}

StoredPass storedPassFromApi({
  required Map<String, dynamic> pass,
  required Cargo cargo,
  required Map<String, String> nodes,
}) {
  final until = pass['valid_until']?.toString() ?? '';
  return StoredPass(
    id: '${pass['id']}',
    shipmentId: '${pass['shipment_id'] ?? cargo.id}',
    token: '${pass['token']}',
    docHash: '${pass['doc_hash'] ?? ''}',
    blockHash: '${pass['block_hash'] ?? ''}',
    checkpointNode: '${pass['checkpoint_node'] ?? ''}',
    checkpointLabel: nodeLabel('${pass['checkpoint_node']}', nodes),
    validUntilIso: until,
    validUntilLabel: fmtDt(until),
    status: mapPassApiStatus(pass['status']?.toString()),
    receivedAtIso: DateTime.now().toUtc().toIso8601String(),
    cargoNumber: cargo.number,
    cargoTitle: cargo.title,
  );
}

/// Маппинг ключей `error.fields` → ключи формы документа.
String? invoiceFieldKeyFromApi(String apiKey) => switch (apiKey) {
  'goods' => 'product',
  'hs_code' => 'hsCode',
  'weight_kg' => 'weight',
  'value' => 'amount',
  'origin_country' => 'origin',
  'seller' => 'seller',
  'buyer' => 'buyer',
  'currency' => 'currency',
  _ => null,
};

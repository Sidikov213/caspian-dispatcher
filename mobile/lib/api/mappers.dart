import '../models/cargo.dart';

const nodeRu = <String, String>{
  'moscow': 'Москва',
  'samara': 'Самара',
  'saratov': 'Саратов',
  'volgograd': 'Волгоград',
  'astrakhan': 'Астрахань',
  'olya': 'Оля',
  'makhachkala': 'Махачкала',
  'samur': 'Самур',
  'baku': 'Баку',
  'astara': 'Астара',
  'rasht': 'Решт',
  'anzali': 'Энзели',
  'amirabad': 'Амирабад',
  'aktau': 'Актау',
  'incheh': 'Инче-Бурун',
  'tehran': 'Тегеран',
  'bandar_abbas': 'Бендер-Аббас',
  'mumbai': 'Мумбаи',
};

String nodeLabel(String id, [Map<String, String>? fromGraph]) {
  if (fromGraph != null && fromGraph.containsKey(id)) return fromGraph[id]!;
  return nodeRu[id] ?? id;
}

CargoStatus mapDisplayStatus(String? raw) => switch (raw) {
  'planned' => CargoStatus.planned,
  'in_transit' => CargoStatus.inTransit,
  'at_risk' => CargoStatus.atRisk,
  'rerouted' => CargoStatus.rerouted,
  'delivered' => CargoStatus.delivered,
  _ => CargoStatus.inTransit,
};

PassStatus mapPassState(String? raw) => switch (raw) {
  'active' => PassStatus.active,
  'reissue_pending' => PassStatus.awaitingReissue,
  'reissued' => PassStatus.reissued,
  'revoked' => PassStatus.invalid,
  'none' || null || '' => PassStatus.none,
  _ => PassStatus.none,
};

PassStatus mapPassApiStatus(String? raw) => switch (raw) {
  'active' => PassStatus.active,
  'reissued' => PassStatus.reissued,
  'revoked' => PassStatus.invalid,
  _ => PassStatus.active,
};

String fmtTons(num t) {
  final v = t % 1 == 0
      ? t.toInt().toString()
      : t.toString().replaceAll('.', ',');
  return '$v т';
}

String fmtRub(num n) {
  final s = n.round().toString();
  final buf = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) buf.write(' ');
    buf.write(s[i]);
  }
  return '${buf.toString()} ₽';
}

String fmtCargoHours(num hours) {
  return '${hours.round()} груз-часов';
}

/// `stats.co2_saved_pct` 6.9 → «−6,9% CO₂»; 0/null → null.
String? fmtCo2SavedPct(num? pct) {
  if (pct == null || pct == 0) return null;
  final raw = pct % 1 == 0
      ? pct.toInt().toString()
      : pct.toString().replaceAll('.', ',');
  return '−$raw% CO₂';
}

String fmtDt(String? iso) {
  if (iso == null || iso.isEmpty) return '—';
  final dt = DateTime.tryParse(iso)?.toLocal();
  if (dt == null) return iso;
  const months = [
    'янв',
    'фев',
    'мар',
    'апр',
    'май',
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
  if (h == null || h.isEmpty) return '—';
  if (h.length <= 8) return h;
  return '${h.substring(0, 4)}…${h.substring(h.length - 4)}';
}

String numberFromId(String id) {
  final m = RegExp(r'(\d+)').firstMatch(id);
  if (m == null) return id;
  return '№${m.group(1)!.padLeft(2, '0')}';
}

String _legSubtitle(String mode) => switch (mode) {
  'rail' => 'Ж/д участок',
  'sea' => 'Морской участок',
  'road' => 'Авто участок',
  _ => 'Участок маршрута',
};

List<RouteStage> stagesFromRoute(
  Map<String, dynamic>? route,
  int? currentLeg,
  Map<String, String> nodes,
) {
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  return [
    for (final leg in legs)
      RouteStage(
        title: nodeLabel('${leg['to']}', nodes),
        subtitle: _legSubtitle('${leg['mode'] ?? ''}'),
        planned: fmtDt(leg['planned_end']?.toString()),
        forecast: fmtDt(leg['planned_end']?.toString()),
        done: leg['status'] == 'done' || leg['status'] == 'completed',
        current: currentLeg != null && leg['index'] == currentLeg,
        warning: ((leg['predicted_delay_h'] as num?) ?? 0) > 0,
      ),
  ];
}

String routeLabel(Map<String, dynamic>? route, Map<String, String> nodes) {
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  if (legs.isEmpty) return '—';
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

Cargo shipmentToCargo(
  Map<String, dynamic> sh, {
  Map<String, String> nodes = const {},
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

  return Cargo(
    id: '${sh['id']}',
    number: numberFromId('${sh['id']}'),
    title: '${sh['title'] ?? ''}',
    weight: fmtTons((sh['weight_t'] as num?) ?? 0),
    weightTons: ((sh['weight_t'] as num?) ?? 0).toDouble(),
    route: routeLabel(route, nodes),
    origin: nodeLabel('${sh['origin']}', nodes),
    destination: nodeLabel('${sh['destination']}', nodes),
    status: mapDisplayStatus(sh['display_status']?.toString()),
    nextPoint: next,
    arrival: fmtDt(sh['eta']?.toString()),
    missProbability: miss,
    departureShiftH: (risk['departure_shift_h'] as num?)?.toDouble(),
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
    stages: stagesFromRoute(route, currentLeg, nodes),
    cancellationForecast: (risk['level']?.toString() == 'high') || miss >= 0.7,
  );
}

List<WavePort> wavesFromWeather(
  Map<String, dynamic> weather,
  Map<String, String> nodes,
) {
  const want = ['astrakhan', 'makhachkala', 'anzali'];
  final points =
      (weather['points'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  return [
    for (final id in want)
      () {
        Map<String, dynamic>? point;
        for (final p in points) {
          if (p['node_id'] == id) {
            point = p;
            break;
          }
        }
        final h = (point?['wave_height_m'] as num?)?.toDouble() ?? 0;
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
  final source = '${weather['source'] ?? '—'}';
  final stale = weather['stale'] == true;

  String? title;
  String? body;
  String? cargoId;
  String? decision;

  if (alerts.isNotEmpty) {
    // Сначала new, иначе последний
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
    decision = decisionSummaryFromAlert(a, nodes);
  }

  return OverviewData(
    shipmentsTotal:
        (stats['shipments_total'] as num?)?.toInt() ?? cargos.length,
    atRisk:
        (stats['at_risk'] as num?)?.toInt() ??
        cargos.where((c) => c.displayStatus == CargoStatus.atRisk).length,
    economyRub: fmtRub((stats['saved_rub'] as num?) ?? 0),
    economyCargoHours: fmtCargoHours((stats['saved_hours'] as num?) ?? 0),
    economyCo2Pct: fmtCo2SavedPct(stats['co2_saved_pct'] as num?),
    waves: waves,
    weatherUpdatedLabel: updated,
    weatherSource: source,
    weatherStale: stale,
    lastAlertTitle: title,
    lastAlertBody: body,
    lastAlertCargoId: cargoId,
    decisionNote: decision,
  );
}

bool _routeTouchesNode(Map<String, dynamic>? route, String nodeId) {
  final legs =
      (route?['legs'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  for (final leg in legs) {
    if (leg['from'] == nodeId || leg['to'] == nodeId) return true;
  }
  return false;
}

String? decisionSummaryFromAlert(
  Map<String, dynamic> alert,
  Map<String, String> nodes,
) {
  final status = '${alert['status']}';
  final sourceTag = switch (alert['source']?.toString()) {
    'forecast' => ' · прогноз',
    'scenario' => ' · сценарий',
    _ => '',
  };
  if (status == 'new') {
    final starts = (alert['starts_in_h'] as num?)?.toDouble();
    final when = starts == null ? '' : ' · через ${starts.round()} ч';
    return 'Ожидает решения логиста$when$sourceTag';
  }
  if (status == 'rejected') return 'Решение: ждать следующий рейс';
  if (status == 'superseded') {
    final note = alert['status_note']?.toString();
    if (note == 'угроза снята') return 'Угроза снята — решение не нужно';
    if (note != null && note.isNotEmpty) return note;
    return 'Алерт устарел';
  }
  if (status != 'accepted') return null;

  final items =
      (alert['items'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
  double? delay;
  var viaMkh = false;
  var viaWest = false;
  var waitOnly = false;
  if (items.isNotEmpty) {
    delay = (items.first['delay_vs_plan_h'] as num?)?.toDouble();
    for (final item in items) {
      if (item['action']?.toString() == 'wait' || item['to_route'] == null) {
        waitOnly = true;
      }
      final toRoute = item['to_route'] as Map<String, dynamic>?;
      if (_routeTouchesNode(toRoute, 'makhachkala')) viaMkh = true;
      if (_routeTouchesNode(toRoute, 'samur') ||
          _routeTouchesNode(toRoute, 'baku')) {
        viaWest = true;
      }
    }
  }

  // Fallback: рекомендованный / принятый option (id после accept обновляется).
  if (!viaMkh && !viaWest) {
    final options =
        (alert['options'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
    for (final o in options) {
      if (o['recommended'] != true) continue;
      if (o['id'] == 'mkh') viaMkh = true;
      if (o['id'] == 'west') viaWest = true;
      if (o['id'] == 'wait') waitOnly = true;
    }
  }

  if (waitOnly && !viaMkh && !viaWest) {
    return 'Решение: ждать следующий рейс';
  }

  final via = viaMkh
      ? 'через Махачкалу'
      : viaWest
      ? 'западной веткой'
      : 'принятым маршрутом';
  final delayPart = delay == null ? '' : ', +${delay.round()} ч к плану';
  final acceptedVia = switch (alert['accepted_via']?.toString()) {
    'web' => ' · сайт',
    'telegram' => ' · Telegram',
    _ => '',
  };
  return 'Решение диспетчера: $via$delayPart$acceptedVia';
}

DispatcherDecision decisionForCargo({
  required Cargo cargo,
  required List<Map<String, dynamic>> alerts,
  Map<String, String> nodes = const {},
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
        summary: 'Ожидает решения логиста',
        alertId: a['id']?.toString(),
      );
    }
    final summary = decisionSummaryFromAlert(a, nodes);
    return DispatcherDecision(
      waiting: false,
      summary:
          summary ??
          (cargo.routeChanged
              ? 'Решение диспетчера принято'
              : 'Решение зафиксировано'),
      alertId: a['id']?.toString(),
    );
  }
  if (cargo.displayStatus == CargoStatus.atRisk) {
    return const DispatcherDecision(
      waiting: true,
      summary: 'Ожидает решения логиста',
    );
  }
  if (cargo.routeChanged || cargo.displayStatus == CargoStatus.rerouted) {
    final viaMkh =
        cargo.route.contains('Махачкала') ||
        cargo.passPort == 'Махачкала' ||
        (cargo.nextPoint == 'Махачкала');
    return DispatcherDecision(
      waiting: false,
      summary: viaMkh
          ? 'Решение диспетчера: через Махачкалу'
          : 'Решение диспетчера принято',
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

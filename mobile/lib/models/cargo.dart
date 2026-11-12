import '../theme/app_colors.dart';
import 'alert_card.dart';

enum CargoStatus { planned, inTransit, atRisk, rerouted, delivered, unknown }

enum PassStatus { none, active, reissued, awaitingReissue, invalid, unknown }

enum CargoListFilter {
  all,
  active,
  atRisk,
  inTransit,
  rerouted,
  planned,
  delivered,
}

enum PassListFilter { all, active, history }

extension CargoListFilterX on CargoListFilter {
  String get label => switch (this) {
    CargoListFilter.all => 'Все',
    CargoListFilter.active => 'Активные',
    CargoListFilter.atRisk => 'Под риском',
    CargoListFilter.inTransit => 'В пути',
    CargoListFilter.rerouted => 'Перестроен',
    CargoListFilter.planned => 'Запланирован',
    CargoListFilter.delivered => 'Доставлен',
  };

  bool matches(Cargo cargo) => switch (this) {
    CargoListFilter.all => true,
    CargoListFilter.active => cargo.status != CargoStatus.delivered,
    CargoListFilter.atRisk => cargo.displayStatus == CargoStatus.atRisk,
    CargoListFilter.inTransit => cargo.status == CargoStatus.inTransit,
    CargoListFilter.rerouted => cargo.status == CargoStatus.rerouted,
    CargoListFilter.planned => cargo.status == CargoStatus.planned,
    CargoListFilter.delivered => cargo.status == CargoStatus.delivered,
  };
}

extension PassListFilterX on PassListFilter {
  String get label => switch (this) {
    PassListFilter.all => 'Все',
    PassListFilter.active => 'Действующие',
    PassListFilter.history => 'История',
  };

  bool matchesStored(StoredPass pass) => switch (this) {
    PassListFilter.all => true,
    // Только действующий JWT; переоформленные — в истории.
    PassListFilter.active => pass.status == PassStatus.active,
    PassListFilter.history =>
      pass.status == PassStatus.awaitingReissue ||
          pass.status == PassStatus.reissued ||
          pass.status == PassStatus.invalid ||
          pass.status == PassStatus.none,
  };
}

extension CargoStatusX on CargoStatus {
  String get label => switch (this) {
    CargoStatus.planned => 'Запланирован',
    CargoStatus.inTransit => 'В пути',
    CargoStatus.atRisk => 'Под риском',
    CargoStatus.rerouted => 'Перестроен',
    CargoStatus.delivered => 'Доставлен',
    CargoStatus.unknown => 'Статус неизвестен',
  };

  CargoStatusTone get tone => switch (this) {
    CargoStatus.planned => CargoStatusTone.planned,
    CargoStatus.inTransit => CargoStatusTone.inTransit,
    CargoStatus.atRisk => CargoStatusTone.atRisk,
    CargoStatus.rerouted => CargoStatusTone.rerouted,
    CargoStatus.delivered => CargoStatusTone.delivered,
    CargoStatus.unknown => CargoStatusTone.unknown,
  };
}

extension PassStatusX on PassStatus {
  String get label => switch (this) {
    PassStatus.none => 'Нет пропуска',
    PassStatus.active => 'Действителен',
    PassStatus.reissued => 'Переоформлен',
    PassStatus.awaitingReissue => 'Ожидает переоформления',
    PassStatus.invalid => 'Недействителен',
    PassStatus.unknown => 'Статус неизвестен',
  };
}

class RiskFactor {
  const RiskFactor({
    required this.name,
    required this.label,
    required this.impactHours,
  });

  final String name;
  final String label;
  final double impactHours;
}

/// SHAP-драйверы CatBoost (`Risk.probability_drivers`), вклад в п. п.
class ProbabilityDriver {
  const ProbabilityDriver({
    required this.name,
    required this.label,
    required this.impactPp,
  });

  final String name;
  final String label;
  final double impactPp;
}

class RouteStage {
  const RouteStage({
    required this.title,
    required this.subtitle,
    required this.planned,
    required this.forecast,
    this.done = false,
    this.current = false,
    this.warning = false,
  });

  final String title;
  final String subtitle;
  final String planned;
  final String forecast;
  final bool done;
  final bool current;
  final bool warning;
}

class WavePort {
  const WavePort({
    required this.nodeId,
    required this.name,
    required this.heightM,
    required this.heightLabel,
  });

  final String nodeId;
  final String name;
  final double heightM;
  final String heightLabel;
}

class Cargo {
  const Cargo({
    required this.id,
    required this.number,
    required this.title,
    required this.weight,
    required this.weightTons,
    required this.route,
    required this.origin,
    required this.destination,
    required this.status,
    required this.nextPoint,
    required this.arrival,
    this.missProbability = 0,
    this.departureShiftH,
    this.arrivalDelayH,
    this.riskFactors = const [],
    this.probabilityDrivers = const [],
    this.routeChanged = false,
    this.routeChangedNote,
    this.passStatus = PassStatus.none,
    this.passId,
    this.passPort,
    this.passValidUntil,
    this.passRecord,
    this.passHash,
    this.passToken,
    this.passDocHash,
    this.passBlockHash,
    this.stages = const [],
    this.cancellationForecast = false,
    this.cancellationFact = false,
  });

  final String id;
  final String number;
  final String title;
  final String weight;
  final double weightTons;
  final String route;
  final String origin;
  final String destination;
  final CargoStatus status;
  final String nextPoint;
  final String arrival;
  final double missProbability;
  final double? departureShiftH;
  final double? arrivalDelayH;
  final List<RiskFactor> riskFactors;
  final List<ProbabilityDriver> probabilityDrivers;
  final bool routeChanged;
  final String? routeChangedNote;
  final PassStatus passStatus;
  final String? passId;
  final String? passPort;
  final String? passValidUntil;
  final String? passRecord;
  final String? passHash;
  final String? passToken;
  final String? passDocHash;
  final String? passBlockHash;
  final List<RouteStage> stages;
  final bool cancellationForecast;
  final bool cancellationFact;

  int get riskPercent => (missProbability * 100).round();

  CargoStatus get displayStatus => status;

  bool get showRouteChangedBadge =>
      routeChanged && displayStatus != CargoStatus.rerouted;

  String get displayName => '$number $title';

  Cargo copyWith({
    CargoStatus? status,
    bool? routeChanged,
    String? routeChangedNote,
    PassStatus? passStatus,
    String? passId,
    String? passPort,
    String? passValidUntil,
    String? passRecord,
    String? passHash,
    String? passToken,
    String? passDocHash,
    String? passBlockHash,
    String? nextPoint,
    String? arrival,
    String? route,
    double? missProbability,
    double? departureShiftH,
    double? arrivalDelayH,
    List<RiskFactor>? riskFactors,
    List<ProbabilityDriver>? probabilityDrivers,
    List<RouteStage>? stages,
    bool? cancellationForecast,
    bool? cancellationFact,
  }) {
    return Cargo(
      id: id,
      number: number,
      title: title,
      weight: weight,
      weightTons: weightTons,
      route: route ?? this.route,
      origin: origin,
      destination: destination,
      status: status ?? this.status,
      nextPoint: nextPoint ?? this.nextPoint,
      arrival: arrival ?? this.arrival,
      missProbability: missProbability ?? this.missProbability,
      departureShiftH: departureShiftH ?? this.departureShiftH,
      arrivalDelayH: arrivalDelayH ?? this.arrivalDelayH,
      riskFactors: riskFactors ?? this.riskFactors,
      probabilityDrivers: probabilityDrivers ?? this.probabilityDrivers,
      routeChanged: routeChanged ?? this.routeChanged,
      routeChangedNote: routeChangedNote ?? this.routeChangedNote,
      passStatus: passStatus ?? this.passStatus,
      passId: passId ?? this.passId,
      passPort: passPort ?? this.passPort,
      passValidUntil: passValidUntil ?? this.passValidUntil,
      passRecord: passRecord ?? this.passRecord,
      passHash: passHash ?? this.passHash,
      passToken: passToken ?? this.passToken,
      passDocHash: passDocHash ?? this.passDocHash,
      passBlockHash: passBlockHash ?? this.passBlockHash,
      stages: stages ?? this.stages,
      cancellationForecast: cancellationForecast ?? this.cancellationForecast,
      cancellationFact: cancellationFact ?? this.cancellationFact,
    );
  }
}

class InvoiceFields {
  const InvoiceFields({
    this.seller = '',
    this.buyer = '',
    this.product = '',
    this.hsCode = '',
    this.weight = '',
    this.amount = '',
    this.currency = 'USD',
    this.origin = '',
    this.hsCodeDoubt = false,
  });

  final String seller;
  final String buyer;
  final String product;
  final String hsCode;
  final String weight;
  final String amount;
  final String currency;
  final String origin;
  final bool hsCodeDoubt;

  InvoiceFields copyWith({
    String? seller,
    String? buyer,
    String? product,
    String? hsCode,
    String? weight,
    String? amount,
    String? currency,
    String? origin,
    bool? hsCodeDoubt,
  }) {
    return InvoiceFields(
      seller: seller ?? this.seller,
      buyer: buyer ?? this.buyer,
      product: product ?? this.product,
      hsCode: hsCode ?? this.hsCode,
      weight: weight ?? this.weight,
      amount: amount ?? this.amount,
      currency: currency ?? this.currency,
      origin: origin ?? this.origin,
      hsCodeDoubt: hsCodeDoubt ?? this.hsCodeDoubt,
    );
  }
}

class OverviewData {
  const OverviewData({
    required this.shipmentsTotal,
    required this.atRisk,
    required this.economyRub,
    required this.economyCargoHours,
    this.economyCo2Pct,
    required this.waves,
    required this.weatherUpdatedLabel,
    required this.weatherSource,
    required this.weatherStale,
    this.lastAlertTitle,
    this.lastAlertBody,
    this.lastAlertCargoId,
    this.decisionNote,
    this.lastAlertCard,
  });

  final int shipmentsTotal;
  final int atRisk;
  final String economyRub;
  final String economyCargoHours;

  /// Из `stats.co2_saved_pct`, напр. «−6,9% CO₂»; null если 0.
  final String? economyCo2Pct;
  final List<WavePort> waves;
  final String weatherUpdatedLabel;
  final String weatherSource;
  final bool weatherStale;
  final String? lastAlertTitle;
  final String? lastAlertBody;
  final String? lastAlertCargoId;
  final String? decisionNote;

  /// Структурированный `Alert.card` (или временная заглушка до бэка).
  final AlertCardData? lastAlertCard;
}

/// Локальная копия пропуска (история на устройстве).
class StoredPass {
  const StoredPass({
    required this.id,
    required this.shipmentId,
    required this.token,
    required this.docHash,
    required this.blockHash,
    required this.checkpointNode,
    required this.checkpointLabel,
    required this.validUntilIso,
    required this.validUntilLabel,
    required this.status,
    required this.receivedAtIso,
    this.cargoNumber = '',
    this.cargoTitle = '',
  });

  final String id;
  final String shipmentId;
  final String token;
  final String docHash;
  final String blockHash;
  final String checkpointNode;
  final String checkpointLabel;
  final String validUntilIso;
  final String validUntilLabel;
  final PassStatus status;
  final String receivedAtIso;
  final String cargoNumber;
  final String cargoTitle;

  Map<String, dynamic> toJson() => {
    'id': id,
    'shipment_id': shipmentId,
    'token': token,
    'doc_hash': docHash,
    'block_hash': blockHash,
    'checkpoint_node': checkpointNode,
    'checkpoint_label': checkpointLabel,
    'valid_until': validUntilIso,
    'valid_until_label': validUntilLabel,
    'status': status.name,
    'received_at': receivedAtIso,
    'cargo_number': cargoNumber,
    'cargo_title': cargoTitle,
  };

  factory StoredPass.fromJson(Map<String, dynamic> j) {
    return StoredPass(
      id: '${j['id']}',
      shipmentId: '${j['shipment_id']}',
      token: '${j['token']}',
      docHash: '${j['doc_hash'] ?? ''}',
      blockHash: '${j['block_hash'] ?? ''}',
      checkpointNode: '${j['checkpoint_node'] ?? ''}',
      checkpointLabel: '${j['checkpoint_label'] ?? j['checkpoint_node'] ?? ''}',
      validUntilIso: '${j['valid_until'] ?? ''}',
      validUntilLabel: '${j['valid_until_label'] ?? ''}',
      status: PassStatus.values.firstWhere(
        (e) => e.name == j['status'],
        orElse: () => PassStatus.unknown,
      ),
      receivedAtIso: '${j['received_at'] ?? ''}',
      cargoNumber: '${j['cargo_number'] ?? ''}',
      cargoTitle: '${j['cargo_title'] ?? ''}',
    );
  }

  StoredPass copyWith({PassStatus? status}) {
    return StoredPass(
      id: id,
      shipmentId: shipmentId,
      token: token,
      docHash: docHash,
      blockHash: blockHash,
      checkpointNode: checkpointNode,
      checkpointLabel: checkpointLabel,
      validUntilIso: validUntilIso,
      validUntilLabel: validUntilLabel,
      status: status ?? this.status,
      receivedAtIso: receivedAtIso,
      cargoNumber: cargoNumber,
      cargoTitle: cargoTitle,
    );
  }
}

class DispatcherDecision {
  const DispatcherDecision({required this.waiting, this.summary, this.alertId});

  final bool waiting;
  final String? summary;
  final String? alertId;
}

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import '../api/api_client.dart';
import '../api/mappers.dart';
import '../models/cargo.dart';
import '../services/pass_store.dart';
import '../services/realtime_service.dart';

enum AppLoadState { idle, loading, ready, error }

class AppController extends ChangeNotifier {
  AppController({ApiClient? api, PassStore? passStore, RealtimeService? realtime})
    : _api = api ?? ApiClient(),
      _passStore = passStore ?? PassStore() {
    _realtime =
        realtime ??
        RealtimeService(
          onEvent: (type, payload) {
            unawaited(_onRealtimeEvent(type, payload));
          },
          onConnection: (_) => _syncPolling(),
        );
  }

  final ApiClient _api;
  final PassStore _passStore;
  late final RealtimeService _realtime;

  List<Cargo> _cargos = [];
  List<Map<String, dynamic>> _alerts = [];
  OverviewData? _overview;
  List<StoredPass> _storedPasses = [];
  Map<String, String> _nodes = {};

  InvoiceFields _invoice = const InvoiceFields();
  bool _recognizing = false;
  String? _captureError;
  String? _pendingDocId;
  bool _documentUploaded = false;
  bool _fieldsConfirmed = false;
  bool _passIssuedForDoc = false;
  bool _ledgerRecorded = false;

  int _homeTab = 0;
  CargoListFilter _cargoListFilter = CargoListFilter.all;
  PassListFilter _passListFilter = PassListFilter.all;

  AppLoadState _loadState = AppLoadState.idle;
  String? _errorMessage;
  bool _refreshing = false;
  Timer? _pollTimer;
  bool _pollInFlight = false;

  /// Кэш пропусков, чтобы silent-poll не долбил /passes/* каждые N секунд.
  final Map<String, Map<String, dynamic>> _passById = {};

  /// Fallback, если WebSocket недоступен (контракт: 3 с).
  static const _pollFallback = Duration(seconds: 3);

  List<Cargo> get cargos => _cargos;
  OverviewData? get overview => _overview;
  List<StoredPass> get storedPasses => _storedPasses;
  List<Map<String, dynamic>> get alerts => _alerts;
  Map<String, String> get nodes => _nodes;

  AppLoadState get loadState => _loadState;
  String? get errorMessage => _errorMessage;
  bool get refreshing => _refreshing;
  bool get isReady => _loadState == AppLoadState.ready;
  bool get realtimeConnected => _realtime.isConnected;

  List<Cargo> get filteredCargos =>
      cargos.where(_cargoListFilter.matches).toList(growable: false);

  List<StoredPass> get filteredStoredPasses =>
      storedPasses.where(_passListFilter.matchesStored).toList(growable: false);

  InvoiceFields get invoice => _invoice;
  bool get recognizing => _recognizing;
  String? get captureError => _captureError;
  int get homeTab => _homeTab;
  CargoListFilter get cargoListFilter => _cargoListFilter;
  PassListFilter get passListFilter => _passListFilter;

  bool get corridorDocUploaded => _documentUploaded;
  bool get corridorFieldsChecked => _fieldsConfirmed;
  bool get corridorPassIssued => _passIssuedForDoc;
  bool get corridorLedger => _ledgerRecorded;

  Future<void> bootstrap() async {
    await _passStore.loadAll().then((v) => _storedPasses = v);
    await refresh(forceLoading: true);
    await _realtime.start();
    _syncPolling();
  }

  void _syncPolling() {
    _pollTimer?.cancel();
    if (_realtime.isConnected) {
      _pollTimer = null;
      return;
    }
    _pollTimer = Timer.periodic(_pollFallback, (_) {
      if (_loadState == AppLoadState.ready) {
        refresh(silent: true);
      }
    });
  }

  Future<void> _onRealtimeEvent(String type, Object? payload) async {
    _syncPolling();
    switch (type) {
      case 'demo.reset':
        await _handleDemoReset();
      case 'weather.updated':
        await refresh(silent: true, forceGraph: false);
      case 'shipment.updated':
      case 'alert.created':
      case 'alert.updated':
      case 'stats.updated':
      case 'ledger.appended':
        await refresh(silent: true);
      default:
        await refresh(silent: true);
    }
  }

  Future<void> _handleDemoReset() async {
    _passById.clear();
    _nodes = {};
    _pendingDocId = null;
    _documentUploaded = false;
    _fieldsConfirmed = false;
    _passIssuedForDoc = false;
    _ledgerRecorded = false;
    _invoice = const InvoiceFields();
    await refresh(forceLoading: true, forceGraph: true);
  }

  /// Возобновить realtime / fallback-опрос (lifecycle).
  void startPolling() {
    unawaited(_realtime.start());
    _syncPolling();
  }

  void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
    unawaited(_realtime.stop());
  }

  Future<void> onAppResumed() async {
    await _realtime.start();
    _syncPolling();
    await refresh(silent: true);
  }

  Future<void> refresh({
    bool silent = false,
    bool forceLoading = false,
    bool forceGraph = false,
  }) async {
    if (_pollInFlight) return;
    _pollInFlight = true;
    if (forceLoading || (!silent && _loadState != AppLoadState.ready)) {
      _loadState = AppLoadState.loading;
      _errorMessage = null;
      notifyListeners();
    } else if (!silent) {
      _refreshing = true;
      notifyListeners();
    }

    try {
      if (_nodes.isEmpty || forceGraph) {
        final graph = await _api.fetchGraph();
        _nodes = nodesFromGraph(graph);
      }

      final results = await Future.wait([
        _api.fetchShipments(),
        _api.fetchStats(),
        _api.fetchWeather(),
        _api.fetchAlerts(),
      ]);

      final shipments = results[0] as List<Map<String, dynamic>>;
      final stats = results[1] as Map<String, dynamic>;
      final weather = results[2] as Map<String, dynamic>;
      _alerts = results[3] as List<Map<String, dynamic>>;

      List<Map<String, dynamic>> remotePasses = const [];
      try {
        remotePasses = await _api.fetchPasses();
      } catch (_) {
        // Локальная история остаётся.
      }
      for (final p in remotePasses) {
        final id = p['id']?.toString();
        if (id != null) _passById[id] = p;
      }

      final mapped = <Cargo>[];
      final seenPassIds = <String>{};
      for (final sh in shipments) {
        Map<String, dynamic>? pass;
        final pid = sh['pass_id']?.toString();
        if (pid != null && pid.isNotEmpty) {
          seenPassIds.add(pid);
          pass = _passById[pid];
          if (pass == null || forceLoading) {
            try {
              pass = await _api.fetchPass(pid);
              _passById[pid] = pass;
            } catch (_) {
              pass = _passById[pid];
            }
          }
        }
        final cargo = shipmentToCargo(sh, nodes: _nodes, pass: pass);
        mapped.add(cargo);
        if (pass != null && pass['token'] != null) {
          await _ingestPass(pass, cargo);
        }
        for (final p in remotePasses) {
          if (p['shipment_id']?.toString() != cargo.id) continue;
          final id = p['id']?.toString();
          if (id != null) seenPassIds.add(id);
          if (p['token'] != null) {
            await _ingestPass(p, cargo);
          }
        }
      }
      _passById.removeWhere((id, _) => !seenPassIds.contains(id));

      _cargos = mapped;
      _overview = buildOverview(
        stats: stats,
        weather: weather,
        alerts: _alerts,
        cargos: mapped,
        nodes: _nodes,
      );
      await _syncStoredStatuses(mapped);
      _loadState = AppLoadState.ready;
      _errorMessage = null;
      _syncPolling();
    } catch (e) {
      _errorMessage = e is ApiException ? e.message : e.toString();
      if (_loadState != AppLoadState.ready) {
        _loadState = AppLoadState.error;
        _cargos = [];
        _overview = null;
      }
    } finally {
      _refreshing = false;
      _pollInFlight = false;
      notifyListeners();
    }
  }

  Future<void> _ingestPass(Map<String, dynamic> pass, Cargo cargo) async {
    final stored = storedPassFromApi(pass: pass, cargo: cargo, nodes: _nodes);
    _storedPasses = await _passStore.upsertKeepHistory(stored);
  }

  Future<void> _syncStoredStatuses(List<Cargo> cargos) async {
    final byShipment = {for (final c in cargos) c.id: c};
    var changed = false;
    final next = <StoredPass>[];
    for (final p in _storedPasses) {
      final cargo = byShipment[p.shipmentId];
      if (cargo == null) {
        next.add(p);
        continue;
      }
      if (cargo.passId != null && cargo.passId == p.id) {
        if (p.status != cargo.passStatus &&
            cargo.passStatus != PassStatus.none &&
            cargo.passStatus != PassStatus.unknown) {
          next.add(p.copyWith(status: cargo.passStatus));
          changed = true;
        } else {
          next.add(p);
        }
      } else if (cargo.passId != null &&
          cargo.passId != p.id &&
          p.status == PassStatus.active) {
        next.add(p.copyWith(status: PassStatus.reissued));
        changed = true;
      } else {
        next.add(p);
      }
    }
    if (changed) {
      _storedPasses = next;
      await _passStore.saveAll(next);
    }
  }

  void setHomeTab(int index, {CargoListFilter? cargoFilter}) {
    _homeTab = index.clamp(0, 2);
    if (cargoFilter != null) _cargoListFilter = cargoFilter;
    notifyListeners();
  }

  void setCargoListFilter(CargoListFilter filter) {
    _cargoListFilter = filter;
    notifyListeners();
  }

  void setPassListFilter(PassListFilter filter) {
    _passListFilter = filter;
    notifyListeners();
  }

  int countCargos(CargoListFilter filter) =>
      cargos.where(filter.matches).length;

  int countStoredPasses(PassListFilter filter) =>
      storedPasses.where(filter.matchesStored).length;

  Cargo? byId(String id) {
    for (final c in cargos) {
      if (c.id == id) return c;
    }
    return null;
  }

  StoredPass? storedPassById(String id) {
    for (final p in storedPasses) {
      if (p.id == id) return p;
    }
    return null;
  }

  DispatcherDecision decisionFor(Cargo cargo) =>
      decisionForCargo(cargo: cargo, alerts: _alerts);

  Future<void> startRecognition(
    String cargoId, {
    required Uint8List imageBytes,
    String filename = 'invoice.jpg',
  }) async {
    _recognizing = true;
    _captureError = null;
    _pendingDocId = null;
    notifyListeners();
    try {
      final doc = await _api.uploadDocument(
        shipmentId: cargoId,
        bytes: imageBytes,
        filename: filename,
      );
      _pendingDocId = doc['id']?.toString();
      _documentUploaded = true;
      final fields = doc['fields'] as Map<String, dynamic>?;
      _invoice = documentFieldsToInvoice(fields);
      final checks =
          (doc['checks'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
      final hsDoubt = checks.any(
        (c) => c['ok'] == false && '${c['name']}'.toLowerCase().contains('hs'),
      );
      if (hsDoubt) _invoice = _invoice.copyWith(hsCodeDoubt: true);
    } catch (e) {
      _captureError = e is ApiException ? e.message : e.toString();
    } finally {
      _recognizing = false;
      notifyListeners();
    }
  }

  void updateInvoice(InvoiceFields fields) {
    _invoice = fields;
    notifyListeners();
  }

  String? validateInvoice(Cargo cargo) {
    final f = _invoice;
    if (f.product.trim().isEmpty ||
        f.hsCode.trim().isEmpty ||
        f.weight.trim().isEmpty ||
        f.amount.trim().isEmpty ||
        f.origin.trim().isEmpty) {
      return 'Заполните товар, код ТН ВЭД, вес, стоимость и страну';
    }
    final scanned = double.tryParse(
      f.weight.replaceAll(' ', '').replaceAll(',', '.'),
    );
    if (cargo.weightTons > 0 && scanned != null) {
      final diff =
          ((scanned - cargo.weightTons).abs() / cargo.weightTons) * 100;
      if (diff > 5) {
        return 'Вес расходится с заявкой более чем на 5%';
      }
    }
    return null;
  }

  bool get hasHsCodeWarning => _invoice.hsCodeDoubt;

  /// null = успех; иначе сообщение и опционально поля формы с ошибками.
  Future<({String? message, Map<String, String> fields})> issuePass(
    String cargoId,
  ) async {
    if (_pendingDocId == null) {
      return (
        message: 'Сначала загрузите документ',
        fields: const <String, String>{},
      );
    }
    try {
      final out = await _api.confirmDocument(
        _pendingDocId!,
        invoiceToApiFields(_invoice),
      );
      _fieldsConfirmed = true;
      _passIssuedForDoc = true;
      if (out['block'] != null) _ledgerRecorded = true;
      _pendingDocId = null;
      final pass = out['pass'] as Map<String, dynamic>?;
      if (pass != null) {
        final pid = pass['id']?.toString();
        if (pid != null) _passById[pid] = pass;
      }
      await refresh(silent: true);
      final cargo = byId(cargoId);
      if (pass != null && cargo != null) {
        await _ingestPass(pass, cargo);
        notifyListeners();
      }
      return (message: null, fields: const <String, String>{});
    } on ApiException catch (e) {
      final mapped = <String, String>{};
      final raw = e.fields;
      if (raw != null) {
        for (final entry in raw.entries) {
          final key = invoiceFieldKeyFromApi(entry.key) ?? entry.key;
          mapped[key] = entry.value;
        }
      }
      return (message: e.message, fields: mapped);
    } catch (e) {
      return (message: e.toString(), fields: const <String, String>{});
    }
  }

  Future<String?> retryPass(String cargoId) async {
    try {
      final out = await _api.retryPass(cargoId);
      final pass = out['pass'] as Map<String, dynamic>?;
      if (pass != null) {
        final pid = pass['id']?.toString();
        if (pid != null) _passById[pid] = pass;
      }
      await refresh(silent: true);
      final cargo = byId(cargoId);
      if (pass != null && cargo != null) {
        await _ingestPass(pass, cargo);
      }
      notifyListeners();
      return null;
    } catch (e) {
      return e is ApiException ? e.message : e.toString();
    }
  }

  Future<Map<String, dynamic>> verifyStoredPass(StoredPass pass) {
    return _api.verifyPass(pass.token);
  }

  CorridorProgress corridorProgress(Cargo cargo) {
    final hasPass = cargo.passStatus != PassStatus.none && cargo.passId != null;
    final inHistory = storedPasses.any((p) => p.shipmentId == cargo.id);
    final docDone = _documentUploaded || hasPass || inHistory;
    final fieldsDone = _fieldsConfirmed || hasPass || inHistory;
    final passDone = hasPass || _passIssuedForDoc;
    final ledgerDone =
        _ledgerRecorded ||
        storedPasses.any(
          (p) => p.shipmentId == cargo.id && p.blockHash.isNotEmpty,
        );
    return CorridorProgress(
      documentUploaded: docDone,
      fieldsChecked: fieldsDone,
      passIssued: passDone,
      ledgerRecorded: ledgerDone,
    );
  }

  @override
  void dispose() {
    stopPolling();
    unawaited(_realtime.stop());
    super.dispose();
  }
}

class CorridorProgress {
  const CorridorProgress({
    required this.documentUploaded,
    required this.fieldsChecked,
    required this.passIssued,
    required this.ledgerRecorded,
  });

  final bool documentUploaded;
  final bool fieldsChecked;
  final bool passIssued;
  final bool ledgerRecorded;
}

class AppScope extends InheritedNotifier<AppController> {
  const AppScope({
    super.key,
    required AppController controller,
    required super.child,
  }) : super(notifier: controller);

  static AppController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope not found');
    return scope!.notifier!;
  }
}

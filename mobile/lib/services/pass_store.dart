import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/cargo.dart';

/// Постоянное защищённое хранение копий пропусков на устройстве.
class PassStore {
  PassStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _key = 'caspian_pass_history_v1';

  final FlutterSecureStorage _storage;

  Future<List<StoredPass>> loadAll() async {
    final raw = await _storage.read(key: _key);
    if (raw == null || raw.isEmpty) return const [];
    final list = jsonDecode(raw) as List<dynamic>;
    return list
        .cast<Map<String, dynamic>>()
        .map(StoredPass.fromJson)
        .toList(growable: false);
  }

  Future<void> saveAll(List<StoredPass> passes) async {
    final encoded = jsonEncode(passes.map((e) => e.toJson()).toList());
    await _storage.write(key: _key, value: encoded);
  }

  /// Добавляет новую копию, если такого `id` ещё нет. Старые не перезаписывает.
  Future<List<StoredPass>> upsertKeepHistory(StoredPass pass) async {
    final next = mergeKeepHistory(await loadAll(), pass);
    await saveAll(next);
    return next;
  }

  /// Обновляет только статус у существующей записи; token/хэши не трогает.
  Future<List<StoredPass>> updateStatus(
    String passId,
    PassStatus status,
  ) async {
    final next = applyStatusUpdate(await loadAll(), passId, status);
    await saveAll(next);
    return next;
  }

  static List<StoredPass> mergeKeepHistory(
    List<StoredPass> current,
    StoredPass pass,
  ) {
    if (current.any((p) => p.id == pass.id)) return current;
    return [pass, ...current];
  }

  static List<StoredPass> applyStatusUpdate(
    List<StoredPass> current,
    String passId,
    PassStatus status,
  ) {
    return [
      for (final p in current)
        if (p.id == passId) p.copyWith(status: status) else p,
    ];
  }
}

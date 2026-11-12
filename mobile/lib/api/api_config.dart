import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Конфиг backend из `.env` (см. `.env.example`).
/// Опционально можно переопределить через `--dart-define`.
class ApiConfig {
  const ApiConfig._();

  static const apiPrefix = '/api';

  static const _defineBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const _defineApiKey = String.fromEnvironment('API_KEY');

  static String? _envGet(String key) {
    if (!dotenv.isInitialized) return null;
    return dotenv.maybeGet(key)?.trim();
  }

  static String get baseUrl {
    if (_defineBaseUrl.trim().isNotEmpty) return _defineBaseUrl.trim();
    final fromEnv = _envGet('API_BASE_URL');
    if (fromEnv != null && fromEnv.isNotEmpty) return fromEnv;
    return 'http://127.0.0.1:8000';
  }

  static String get apiKey {
    if (_defineApiKey.trim().isNotEmpty) return _defineApiKey.trim();
    return _envGet('API_KEY') ?? '';
  }

  static bool get hasApiKey => apiKey.isNotEmpty;

  /// Загрузка `.env` из assets. Вызывать до создания [ApiClient].
  static Future<void> load() async {
    try {
      await dotenv.load(fileName: '.env');
    } catch (_) {
      try {
        await dotenv.load(fileName: '.env.example');
      } catch (_) {
        // Пустые значения — ApiClient покажет понятную ошибку.
      }
    }
  }
}

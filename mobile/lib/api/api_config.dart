import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Конфиг backend: достаточно положить `.env` в корень и сделать `flutter run`.
/// Опционально можно переопределить через `--dart-define` / `--dart-define-from-file`.
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

  /// `wss://…/ws?api_key=…` из [baseUrl].
  static Uri wsUri() {
    final root = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final http = Uri.parse(root);
    final scheme = http.scheme == 'https' ? 'wss' : 'ws';
    return Uri(
      scheme: scheme,
      host: http.host,
      port: http.hasPort ? http.port : null,
      path: '/ws',
      queryParameters: {'api_key': apiKey},
    );
  }
}

/// Конфиг backend только через `--dart-define` / `--dart-define-from-file`.
///
/// Пример:
/// `flutter run --dart-define-from-file=.env`
class ApiConfig {
  const ApiConfig._();

  static const apiPrefix = '/api';

  static const _defineBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const _defineApiKey = String.fromEnvironment('API_KEY');

  static String get baseUrl {
    final v = _defineBaseUrl.trim();
    if (v.isNotEmpty) return v;
    return 'http://127.0.0.1:8000';
  }

  static String get apiKey => _defineApiKey.trim();

  static bool get hasApiKey => apiKey.isNotEmpty;

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

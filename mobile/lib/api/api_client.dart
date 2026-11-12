import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../models/auth_user.dart';
import 'api_config.dart';

class ApiException implements Exception {
  ApiException(
    this.message, {
    this.statusCode,
    this.code,
    this.fields,
  });

  final String message;
  final int? statusCode;
  final String? code;

  /// Поля из `error.fields` (например `document_invalid`).
  final Map<String, String>? fields;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? httpClient, String? baseUrl, String? apiKey})
    : _http = httpClient ?? http.Client(),
      baseUrl = baseUrl ?? ApiConfig.baseUrl,
      apiKey = apiKey ?? ApiConfig.apiKey;

  final http.Client _http;
  final String baseUrl;
  final String apiKey;

  Uri _uri(String path, [Map<String, String>? query]) {
    final root = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    return Uri.parse('$root${ApiConfig.apiPrefix}$path')
        .replace(queryParameters: query);
  }

  Map<String, String> get _headers {
    if (apiKey.trim().isEmpty) {
      throw ApiException(
        'Не задан API_KEY. Запустите с '
        '--dart-define-from-file=.env или --dart-define=API_KEY=…',
      );
    }
    return {'X-API-Key': apiKey, 'Accept': 'application/json'};
  }

  void _log(String message) {
    // Видно в терминале `flutter run`.
    // ignore: avoid_print
    print(message);
    developer.log(message, name: 'api');
  }

  String _pretty(Object? raw, {int max = 4000}) {
    try {
      final text = const JsonEncoder.withIndent('  ').convert(raw);
      if (text.length <= max) return text;
      return '${text.substring(0, max)}… (${text.length} chars)';
    } catch (_) {
      final s = '$raw';
      if (s.length <= max) return s;
      return '${s.substring(0, max)}…';
    }
  }

  Object? _redactBody(Object? body) {
    if (body is! Map) return body;
    final copy = Map<String, dynamic>.from(body);
    for (final key in ['token', 'password', 'api_key', 'X-API-Key']) {
      if (copy[key] is String && (copy[key] as String).isNotEmpty) {
        copy[key] = '<redacted>';
      }
    }
    return copy;
  }

  void _logRequest(
    String method,
    Uri uri, {
    Object? body,
    Map<String, String>? fields,
  }) {
    final buf = StringBuffer()
      ..writeln('── API REQUEST ─────────────────────────────')
      ..writeln('$method $uri');
    if (body != null) {
      buf.writeln('body:\n${_pretty(_redactBody(body))}');
    }
    if (fields != null) {
      buf.writeln('fields: $fields');
    }
    buf.writeln('───────────────────────────────────────────');
    _log(buf.toString());
  }

  void _logResponse(
    String method,
    Uri uri,
    http.Response res,
    Object? decoded,
  ) {
    final buf = StringBuffer()
      ..writeln('── API RESPONSE ────────────────────────────')
      ..writeln('$method $uri → ${res.statusCode}')
      ..writeln(_pretty(decoded))
      ..writeln('───────────────────────────────────────────');
    _log(buf.toString());
  }

  Map<String, String> _headersWith({String? bearerToken}) {
    final headers = Map<String, String>.from(_headers);
    if (bearerToken != null && bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    return headers;
  }

  Future<dynamic> getJson(
    String path, {
    Map<String, String>? query,
    String? bearerToken,
  }) async {
    final uri = _uri(path, query);
    _logRequest('GET', uri);
    try {
      final res = await _http
          .get(uri, headers: _headersWith(bearerToken: bearerToken))
          .timeout(const Duration(seconds: 12));
      return _decode(res, method: 'GET', uri: uri);
    } on ApiException {
      rethrow;
    } catch (e) {
      _log('── API ERROR GET $uri → $e');
      throw ApiException(_networkMessage(e));
    }
  }

  Future<dynamic> postJson(
    String path, {
    Object? body,
    String? bearerToken,
  }) async {
    final uri = _uri(path);
    _logRequest('POST', uri, body: body);
    try {
      final res = await _http
          .post(
            uri,
            headers: {
              ..._headersWith(bearerToken: bearerToken),
              'Content-Type': 'application/json',
            },
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
      return _decode(res, method: 'POST', uri: uri);
    } on ApiException {
      rethrow;
    } catch (e) {
      _log('── API ERROR POST $uri → $e');
      throw ApiException(_networkMessage(e));
    }
  }

  Future<dynamic> deleteJson(
    String path, {
    Object? body,
    String? bearerToken,
  }) async {
    final uri = _uri(path);
    _logRequest('DELETE', uri, body: body);
    try {
      final res = await _http
          .delete(
            uri,
            headers: {
              ..._headersWith(bearerToken: bearerToken),
              'Content-Type': 'application/json',
            },
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(const Duration(seconds: 20));
      return _decode(res, method: 'DELETE', uri: uri);
    } on ApiException {
      rethrow;
    } catch (e) {
      _log('── API ERROR DELETE $uri → $e');
      throw ApiException(_networkMessage(e));
    }
  }

  String _networkMessage(Object error) {
    final raw = '$error'.toLowerCase();
    if (raw.contains('timeout') || raw.contains('timed out')) {
      return 'Сервер не ответил вовремя. Попробуйте ещё раз.';
    }
    if (raw.contains('connection refused') ||
        raw.contains('network is unreachable') ||
        raw.contains('failed host lookup') ||
        raw.contains('socketexception') ||
        raw.contains('clientexception')) {
      return 'Нет связи с сервером. Проверьте интернет и попробуйте снова.';
    }
    return 'Нет связи с сервером. Попробуйте позже.';
  }

  Future<dynamic> postMultipart(
    String path, {
    required Map<String, String> fields,
    required Uint8List fileBytes,
    String fileField = 'file',
    String filename = 'invoice.jpg',
  }) async {
    final uri = _uri(path);
    _logRequest(
      'POST multipart',
      uri,
      fields: {...fields, fileField: '<$filename ${fileBytes.length} bytes>'},
    );
    try {
      final req = http.MultipartRequest('POST', uri);
      req.headers.addAll(_headers);
      req.fields.addAll(fields);
      req.files.add(
        http.MultipartFile.fromBytes(fileField, fileBytes, filename: filename),
      );
      final streamed = await _http
          .send(req)
          .timeout(const Duration(seconds: 30));
      final res = await http.Response.fromStream(streamed);
      return _decode(res, method: 'POST multipart', uri: uri);
    } on ApiException {
      rethrow;
    } catch (e) {
      _log('── API ERROR POST multipart $uri → $e');
      throw ApiException(_networkMessage(e));
    }
  }

  dynamic _decode(
    http.Response res, {
    required String method,
    required Uri uri,
  }) {
    final raw = res.body.isEmpty
        ? null
        : jsonDecode(utf8.decode(res.bodyBytes));
    _logResponse(method, uri, res, raw);
    if (res.statusCode < 200 || res.statusCode >= 300) {
      String msg = 'HTTP ${res.statusCode}';
      String? code;
      Map<String, String>? fields;
      if (raw is Map) {
        final err = raw['error'];
        if (err is Map) {
          if (err['message'] != null) msg = '${err['message']}';
          if (err['code'] != null) code = '${err['code']}';
          final rawFields = err['fields'];
          if (rawFields is Map) {
            fields = {
              for (final e in rawFields.entries)
                '${e.key}': '${e.value}',
            };
          }
        } else if (raw['detail'] != null) {
          msg = '${raw['detail']}';
        }
      }
      throw ApiException(
        msg,
        statusCode: res.statusCode,
        code: code,
        fields: fields,
      );
    }
    return raw;
  }

  Future<AuthSession> authRegister({
    required String name,
    required String email,
    required String password,
    required AuthRole role,
  }) async {
    final data = await postJson(
      '/auth/register',
      body: {
        'name': name,
        'email': email,
        'password': password,
        'role': role.apiValue,
      },
    );
    return AuthSession.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<AuthSession> authLogin({
    required String email,
    required String password,
  }) async {
    final data = await postJson(
      '/auth/login',
      body: {'email': email, 'password': password},
    );
    return AuthSession.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<AuthUser> authMe(String token) async {
    final data = await getJson('/auth/me', bearerToken: token);
    return AuthUser.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<List<Map<String, dynamic>>> fetchShipments() async {
    final data = await getJson('/shipments');
    return (data as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> fetchShipment(String id) async {
    final data = await getJson('/shipments/$id');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> fetchStats() async {
    final data = await getJson('/stats');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> fetchWeather() async {
    final data = await getJson('/weather');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<Map<String, dynamic>>> fetchAlerts({String? status}) async {
    final data = await getJson(
      '/alerts',
      query: status == null ? null : {'status': status},
    );
    return (data as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> fetchGraph() async {
    final data = await getJson('/graph');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> fetchPass(String passId) async {
    final data = await getJson('/passes/$passId');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<List<Map<String, dynamic>>> fetchPasses({String? shipmentId}) async {
    final data = await getJson(
      '/passes',
      query: shipmentId == null ? null : {'shipment_id': shipmentId},
    );
    return (data as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> registerDevice({
    required String token,
    required String platform,
    required String bearerToken,
  }) async {
    final data = await postJson(
      '/devices',
      body: {'token': token, 'platform': platform},
      bearerToken: bearerToken,
    );
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> unregisterDevice({
    required String token,
    required String bearerToken,
  }) async {
    final data = await deleteJson(
      '/devices',
      body: {'token': token},
      bearerToken: bearerToken,
    );
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> verifyPass(String token) async {
    final data = await postJson('/passes/verify', body: {'token': token});
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> retryPass(String shipmentId) async {
    final data = await postJson('/shipments/$shipmentId/pass/retry');
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> uploadDocument({
    required String shipmentId,
    required Uint8List bytes,
    String filename = 'invoice.jpg',
  }) async {
    final data = await postMultipart(
      '/documents',
      fields: {'shipment_id': shipmentId},
      fileBytes: bytes,
      filename: filename,
    );
    return Map<String, dynamic>.from(data as Map);
  }

  Future<Map<String, dynamic>> confirmDocument(
    String docId,
    Map<String, dynamic> fields,
  ) async {
    final data = await postJson(
      '/documents/$docId/confirm',
      body: {'fields': fields},
    );
    return Map<String, dynamic>.from(data as Map);
  }
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';
import '../models/auth_user.dart';

/// Сессия как на сайте: token + user, проверка через GET /auth/me.
class AuthController extends ChangeNotifier {
  AuthController({ApiClient? api, FlutterSecureStorage? storage})
    : _api = api ?? ApiClient(),
      _storage = storage ?? const FlutterSecureStorage();

  static const _tokenKey = 'caspian.auth.token';
  static const _userKey = 'caspian.auth.user';

  final ApiClient _api;
  final FlutterSecureStorage _storage;

  String? _token;
  AuthUser? _user;
  bool _ready = false;

  bool get ready => _ready;
  bool get isLoggedIn => _token != null && _token!.isNotEmpty && _user != null;
  String? get token => _token;
  AuthUser? get user => _user;

  Future<void> restoreSession() async {
    final token = await _storage.read(key: _tokenKey);
    final rawUser = await _storage.read(key: _userKey);
    AuthUser? cached;
    if (rawUser != null && rawUser.isNotEmpty) {
      try {
        cached = AuthUser.fromJson(
          Map<String, dynamic>.from(jsonDecode(rawUser) as Map),
        );
      } catch (_) {
        cached = null;
      }
    }

    if (token == null || token.isEmpty) {
      _token = null;
      _user = null;
      _ready = true;
      notifyListeners();
      return;
    }

    _token = token;
    _user = cached;

    try {
      final me = await _api.authMe(token);
      _user = me;
      await _persist(token, me);
    } on ApiException catch (e) {
      if (e.statusCode == 401 || e.code == 'invalid_token') {
        await clearSession();
      }
      // Нет сети — оставляем кэш, как AuthGate на сайте.
    } catch (_) {
      // Нет сети — кэш.
    }

    _ready = true;
    notifyListeners();
  }

  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    final session = await _api.authLogin(email: email, password: password);
    await _apply(session);
    return session;
  }

  Future<AuthSession> register({
    required String name,
    required String email,
    required String password,
    required AuthRole role,
  }) async {
    final session = await _api.authRegister(
      name: name,
      email: email,
      password: password,
      role: role,
    );
    await _apply(session);
    return session;
  }

  Future<void> logout() => clearSession();

  Future<void> clearSession() async {
    _token = null;
    _user = null;
    notifyListeners();
    await Future.wait([
      _storage.delete(key: _tokenKey),
      _storage.delete(key: _userKey),
    ]);
  }

  Future<void> _apply(AuthSession session) async {
    _token = session.token;
    _user = session.user;
    _ready = true;
    notifyListeners();
    await _persist(session.token, session.user);
  }

  Future<void> _persist(String token, AuthUser user) async {
    await Future.wait([
      _storage.write(key: _tokenKey, value: token),
      _storage.write(key: _userKey, value: jsonEncode(user.toJson())),
    ]);
  }
}

class AuthScope extends InheritedNotifier<AuthController> {
  const AuthScope({
    super.key,
    required AuthController controller,
    required super.child,
  }) : super(notifier: controller);

  static AuthController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AuthScope>();
    assert(scope != null, 'AuthScope not found');
    return scope!.notifier!;
  }
}

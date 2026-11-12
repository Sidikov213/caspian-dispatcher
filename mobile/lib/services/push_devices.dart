import 'dart:async';
import 'dart:io';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';

/// Регистрация FCM-токена на `/api/devices` (контракт).
class PushDevices {
  PushDevices({ApiClient? api}) : _api = api ?? ApiClient();

  final ApiClient _api;
  StreamSubscription<String>? _refreshSub;
  String? _lastToken;

  String get _platform {
    if (kIsWeb) return 'android';
    if (Platform.isIOS) return 'ios';
    return 'android';
  }

  Future<void> start({required String bearerToken}) async {
    await stop(bearerToken: null);
    try {
      final messaging = FirebaseMessaging.instance;
      if (Platform.isIOS) {
        await messaging.setForegroundNotificationPresentationOptions(
          alert: true,
          badge: true,
          sound: true,
        );
      }
      if (Platform.isAndroid) {
        await FirebaseMessaging.instance
            .setForegroundNotificationPresentationOptions(
          alert: true,
          badge: true,
          sound: true,
        );
      }
      // Контракт: getToken / onTokenRefresh → POST /devices.
      // ignore: deprecated_member_use
      final token = await messaging.getToken();
      if (token != null && token.isNotEmpty) {
        await _register(token, bearerToken);
      }
      // ignore: deprecated_member_use
      _refreshSub = messaging.onTokenRefresh.listen((t) {
        unawaited(_register(t, bearerToken));
      });
    } catch (e) {
      // Firebase / канал могут быть не готовы до полного rebuild.
      // ignore: avoid_print
      print('PushDevices start skipped: $e');
    }
  }

  Future<void> stop({required String? bearerToken}) async {
    await _refreshSub?.cancel();
    _refreshSub = null;
    final token = _lastToken;
    _lastToken = null;
    if (token == null || bearerToken == null || bearerToken.isEmpty) return;
    try {
      await _api.unregisterDevice(token: token, bearerToken: bearerToken);
    } catch (e) {
      // ignore: avoid_print
      print('PushDevices unregister skipped: $e');
    }
  }

  Future<void> _register(String token, String bearerToken) async {
    _lastToken = token;
    try {
      await _api.registerDevice(
        token: token,
        platform: _platform,
        bearerToken: bearerToken,
      );
    } catch (e) {
      // Сервер может ещё не выкатить /devices.
      // ignore: avoid_print
      print('PushDevices register skipped: $e');
    }
  }
}

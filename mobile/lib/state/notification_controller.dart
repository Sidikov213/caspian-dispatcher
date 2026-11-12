import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:permission_handler/permission_handler.dart';

/// Статус системных уведомлений и флаг онбординга.
class NotificationController extends ChangeNotifier {
  NotificationController({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _promptKey = 'caspian_notifications_prompt_v1';

  final FlutterSecureStorage _storage;
  bool _promptSeen = false;
  bool _enabled = false;
  bool _permanentlyDenied = false;
  bool _pluginReady = true;

  bool get promptSeen => _promptSeen;
  bool get enabled => _enabled;
  bool get permanentlyDenied => _permanentlyDenied;
  bool get pluginReady => _pluginReady;

  Future<void> load() async {
    final raw = await _storage.read(key: _promptKey);
    _promptSeen = raw == '1';
    await refreshStatus();
  }

  Future<void> refreshStatus() async {
    try {
      final status = await Permission.notification.status;
      _enabled = status.isGranted;
      _permanentlyDenied = status.isPermanentlyDenied;
      _pluginReady = true;
    } on MissingPluginException {
      _pluginReady = false;
      _enabled = false;
      _permanentlyDenied = false;
    } catch (_) {
      _pluginReady = false;
    }
    notifyListeners();
  }

  Future<void> markPromptSeen() async {
    if (_promptSeen) return;
    _promptSeen = true;
    notifyListeners();
    await _storage.write(key: _promptKey, value: '1');
  }

  /// После «Продолжить» на онбординге: запрос разрешения ОС.
  Future<bool> requestFromOnboarding() async {
    try {
      final status = await Permission.notification.request();
      _enabled = status.isGranted;
      _permanentlyDenied = status.isPermanentlyDenied;
      _pluginReady = true;
    } on MissingPluginException {
      _pluginReady = false;
      _enabled = false;
    } catch (_) {
      _pluginReady = false;
      _enabled = false;
    }
    await markPromptSeen();
    notifyListeners();
    return _enabled;
  }

  Future<bool> requestOrOpenSettings() async {
    await refreshStatus();
    if (_enabled) return true;
    if (!_pluginReady) return false;
    if (_permanentlyDenied) {
      await openAppSettings();
      await refreshStatus();
      return _enabled;
    }
    try {
      final status = await Permission.notification.request();
      _enabled = status.isGranted;
      _permanentlyDenied = status.isPermanentlyDenied;
      _pluginReady = true;
    } on MissingPluginException {
      _pluginReady = false;
      _enabled = false;
    }
    notifyListeners();
    return _enabled;
  }

  Future<void> openSystemSettings() async {
    try {
      await openAppSettings();
    } on MissingPluginException {
      _pluginReady = false;
    }
    await refreshStatus();
  }
}

class NotificationScope extends InheritedNotifier<NotificationController> {
  const NotificationScope({
    super.key,
    required NotificationController controller,
    required super.child,
  }) : super(notifier: controller);

  static NotificationController of(BuildContext context) {
    final scope =
        context.dependOnInheritedWidgetOfExactType<NotificationScope>();
    assert(scope != null, 'NotificationScope not found');
    return scope!.notifier!;
  }
}

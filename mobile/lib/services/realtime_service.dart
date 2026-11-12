import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/api_config.dart';

typedef RealtimeHandler = void Function(String type, Object? payload);
typedef RealtimeConnectionHandler = void Function(bool connected);

/// WebSocket контракта: `/ws?api_key=…`.
class RealtimeService {
  RealtimeService({this.onEvent, this.onConnection});

  final RealtimeHandler? onEvent;
  final RealtimeConnectionHandler? onConnection;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _reconnectTimer;
  bool _wanted = false;
  bool _connected = false;

  bool get isConnected => _connected;

  Future<void> start() async {
    _wanted = true;
    await _connect();
  }

  Future<void> stop() async {
    _wanted = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _tearDown();
  }

  Future<void> _connect() async {
    if (!_wanted) return;
    await _tearDown(notify: false);
    if (!_wanted) return;
    if (!ApiConfig.hasApiKey) {
      // ignore: avoid_print
      print('WS skip: no API key');
      return;
    }
    try {
      final uri = ApiConfig.wsUri();
      // ignore: avoid_print
      print('WS connect $uri');
      final channel = WebSocketChannel.connect(uri);
      _channel = channel;
      await channel.ready.timeout(const Duration(seconds: 8));
      if (!_wanted) {
        await _tearDown(notify: false);
        return;
      }
      _setConnected(true);
      // ignore: avoid_print
      print('WS connected');
      _sub = channel.stream.listen(
        _onMessage,
        onError: (e) {
          // ignore: avoid_print
          print('WS error: $e');
          _onLost();
        },
        onDone: () {
          // ignore: avoid_print
          print('WS closed');
          _onLost();
        },
        cancelOnError: true,
      );
    } catch (e) {
      // ignore: avoid_print
      print('WS connect failed: $e');
      _setConnected(false);
      _scheduleReconnect();
    }
  }

  void _setConnected(bool value) {
    if (_connected == value) return;
    _connected = value;
    onConnection?.call(value);
  }

  void _onMessage(dynamic raw) {
    try {
      final decoded = raw is String ? jsonDecode(raw) : raw;
      if (decoded is! Map) return;
      final type = '${decoded['type'] ?? ''}';
      if (type.isEmpty) return;
      onEvent?.call(type, decoded['payload']);
    } catch (_) {
      // Игнорируем битые кадры.
    }
  }

  void _onLost() {
    _setConnected(false);
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (!_wanted) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 2), () {
      if (_wanted && !_connected) {
        unawaited(_connect());
      }
    });
  }

  Future<void> _tearDown({bool notify = true}) async {
    await _sub?.cancel();
    _sub = null;
    try {
      await _channel?.sink.close();
    } catch (_) {}
    _channel = null;
    if (notify) {
      _setConnected(false);
    } else {
      _connected = false;
    }
  }
}

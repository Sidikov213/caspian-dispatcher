/// Русские формулировки для кодов/причин API (без snake_case в UI).
String apiReasonRu(String? raw, {String fallback = 'недействителен'}) {
  final key = (raw ?? '').trim().toLowerCase();
  if (key.isEmpty) return fallback;

  final mapped = switch (key) {
    'invalid' || 'not_valid' || 'invalid_token' || 'invalid_pass' =>
      'недействителен',
    'pass_not_found' || 'not_found' => 'пропуск не найден',
    'expired' || 'token_expired' => 'срок истёк',
    'revoked' => 'отозван',
    'reissued' || 'superseded' => 'переоформлен',
    'awaiting_reissue' => 'ожидает переоформления',
    'unknown' => 'статус неизвестен',
    'document_invalid' => 'документ не прошёл проверку',
    'validation_error' => 'ошибка проверки данных',
    'unauthorized' || 'forbidden' => 'нет доступа',
    'weight_mismatch' => 'вес не совпадает с заявкой',
    'required_fields' => 'не заполнены обязательные поля',
    _ => null,
  };
  if (mapped != null) return mapped;

  // Непознанный технический код (snake_case / camelCase) — без сырого английского.
  final looksTechnical = RegExp(r'^[a-z][a-z0-9_]*$').hasMatch(key);
  if (looksTechnical) return fallback;
  return raw!.trim();
}

String apiErrorRu(String? message, {String? code}) {
  final fromCode = code == null || code.isEmpty
      ? null
      : apiReasonRu(code, fallback: '');
  if (fromCode != null && fromCode.isNotEmpty) return fromCode;

  final fromMsg = apiReasonRu(message, fallback: '');
  if (fromMsg.isNotEmpty && fromMsg != (message ?? '').trim()) {
    return fromMsg;
  }
  if (message != null && message.trim().isNotEmpty) {
    final looksTechnical =
        RegExp(r'^[a-z][a-z0-9_]*$').hasMatch(message.trim().toLowerCase());
    if (!looksTechnical) return message.trim();
  }
  return 'Не удалось выполнить запрос';
}

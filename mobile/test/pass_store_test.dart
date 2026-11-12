import 'package:caspian_dispatcher/models/cargo.dart';
import 'package:caspian_dispatcher/services/pass_store.dart';
import 'package:flutter_test/flutter_test.dart';

StoredPass _pass(
  String id, {
  String token = 't',
  PassStatus status = PassStatus.active,
}) {
  return StoredPass(
    id: id,
    shipmentId: 'sh-01',
    token: token,
    docHash: 'd1',
    blockHash: 'b1',
    checkpointNode: 'astrakhan',
    checkpointLabel: 'Астрахань',
    validUntilIso: '2026-11-29T23:00:00Z',
    validUntilLabel: '29 ноя',
    status: status,
    receivedAtIso: '2026-11-12T10:00:00Z',
    cargoNumber: '№01',
    cargoTitle: 'Зерно',
  );
}

void main() {
  test('JSON roundtrip StoredPass', () {
    final p = _pass('pass-01', token: 'jwt-secret-not-logged');
    final back = StoredPass.fromJson(p.toJson());
    expect(back.id, p.id);
    expect(back.token, p.token);
    expect(back.docHash, p.docHash);
    expect(back.status, PassStatus.active);
  });

  test('история не перезаписывает старые id и токены', () {
    final a = _pass('pass-01', token: 'token-a');
    var all = PassStore.mergeKeepHistory(const [], a);
    all = PassStore.mergeKeepHistory(all, a);
    expect(all, hasLength(1));

    final c = _pass('pass-01-r1', token: 'token-b');
    all = PassStore.mergeKeepHistory(all, c);
    expect(all, hasLength(2));
    expect(all.firstWhere((e) => e.id == 'pass-01').token, 'token-a');

    all = PassStore.applyStatusUpdate(all, 'pass-01', PassStatus.reissued);
    expect(
      all.firstWhere((e) => e.id == 'pass-01').status,
      PassStatus.reissued,
    );
    expect(all.firstWhere((e) => e.id == 'pass-01').token, 'token-a');
  });
}

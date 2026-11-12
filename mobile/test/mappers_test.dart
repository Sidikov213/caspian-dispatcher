import 'package:caspian_dispatcher/api/mappers.dart';
import 'package:caspian_dispatcher/models/alert_card.dart';
import 'package:caspian_dispatcher/models/cargo.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('numberFromId и display_status', () {
    expect(numberFromId('sh-01'), '№01');
    expect(numberFromId('sh-05'), '№05');
    expect(mapDisplayStatus('at_risk'), CargoStatus.atRisk);
    expect(mapDisplayStatus('weird'), CargoStatus.unknown);
    expect(mapPassState('reissue_pending'), PassStatus.awaitingReissue);
    expect(mapPassApiStatus('weird'), PassStatus.unknown);
  });

  test('shipmentToCargo берёт риск и факторы с API', () {
    final cargo = shipmentToCargo({
      'id': 'sh-01',
      'title': 'Зерно',
      'weight_t': 60,
      'origin': 'moscow',
      'destination': 'mumbai',
      'display_status': 'at_risk',
      'rerouted': false,
      'current_leg': 0,
      'eta': '2026-11-21T09:00:00Z',
      'pass_id': 'pass-01',
      'pass_state': 'active',
      'route': {
        'legs': [
          {
            'index': 0,
            'from': 'moscow',
            'to': 'astrakhan',
            'mode': 'rail',
            'planned_end': '2026-11-13T19:00:00Z',
            'status': 'active',
            'predicted_delay_h': 0,
          },
        ],
      },
      'risk': {
        'miss_probability': 0.82,
        'level': 'high',
        'departure_shift_h': 18,
        'arrival_delay_h': 48,
        'factors': [
          {'name': 'wave_height', 'label': 'Волна 3,4 м', 'impact_hours': 11},
        ],
        'probability_drivers': [
          {'name': 'wave_height', 'label': 'Высота волны', 'impact_pp': 12.5},
        ],
      },
    }, nodes: {'moscow': 'Москва', 'astrakhan': 'Астрахань', 'mumbai': 'Мумбаи'});

    expect(cargo.displayName, '№01 Зерно');
    expect(cargo.riskPercent, 82);
    expect(cargo.departureShiftH, 18);
    expect(cargo.arrivalDelayH, 48);
    expect(cargo.riskFactors, hasLength(1));
    expect(cargo.probabilityDrivers, hasLength(1));
    expect(cargo.probabilityDrivers.first.impactPp, 12.5);
    expect(cargo.status, CargoStatus.atRisk);
    expect(cargo.origin, 'Москва');
  });

  test('decisionSummaryFromAlert: options + accepted_by, без эвристик маршрута', () {
    expect(
      decisionSummaryFromAlert({
        'status': 'new',
        'starts_in_h': 36,
        'options': [
          {'id': 'ice', 'title': 'Обход по льду канала', 'recommended': true},
        ],
        'items': [],
      }),
      'Ожидает решения · Обход по льду канала · через 36 ч',
    );
    expect(
      decisionSummaryFromAlert({
        'status': 'accepted',
        'accepted_via': 'web',
        'accepted_by': {'name': 'Иван Логист', 'role': 'logist'},
        'options': [
          {
            'id': 'mkh',
            'title': 'Через Махачкалу',
            'recommended': true,
            'delay_vs_plan_h': 6,
          },
        ],
        'items': [],
      }),
      'Через Махачкалу · +6 ч к плану · Иван Логист',
    );
    expect(
      decisionSummaryFromAlert({
        'status': 'superseded',
        'status_note': 'угроза снята',
        'options': [],
        'items': [],
      }),
      'угроза снята',
    );
  });

  test('fmtRub и fmtDt по контракту', () {
    expect(fmtRub(597000), '597 тыс ₽');
    expect(fmtCo2SavedPct(6.9), '−6,9%');
    expect(fmtCo2SavedPct(0), isNull);
    // 2026-05-12 11:30 UTC → 14:30 МСК, месяц «мая»
    expect(fmtDt('2026-05-12T11:30:00Z'), '12 мая, 14:30');
  });

  test('wavesFromWeather берёт все точки', () {
    final waves = wavesFromWeather({
      'points': [
        {'node_id': 'astrakhan', 'wave_height_m': 3.4},
        {'node_id': 'olya', 'wave_height_m': 1.1},
      ],
    }, {'astrakhan': 'Астрахань', 'olya': 'Оля'});
    expect(waves, hasLength(2));
    expect(waves.first.name, 'Астрахань');
    expect(waves.last.name, 'Оля');
  });

  test('фильтр пропусков: reissued только в истории', () {
    const active = StoredPass(
      id: 'p1',
      shipmentId: 'sh-01',
      token: 't',
      docHash: 'd',
      blockHash: 'b',
      checkpointNode: 'astrakhan',
      checkpointLabel: 'Астрахань',
      validUntilIso: '',
      validUntilLabel: '',
      status: PassStatus.active,
      receivedAtIso: '',
    );
    final reissued = active.copyWith(status: PassStatus.reissued);
    expect(PassListFilter.active.matchesStored(active), isTrue);
    expect(PassListFilter.active.matchesStored(reissued), isFalse);
    expect(PassListFilter.history.matchesStored(reissued), isTrue);
  });

  test('validate weight via InvoiceFields mapping', () {
    final fields = invoiceToApiFields(
      const InvoiceFields(
        product: 'Зерно',
        hsCode: '1001',
        weight: '60',
        amount: '1',
        origin: 'RU',
      ),
    );
    expect(fields['weight_kg'], 60000);
  });

  test('AlertCardData stub и fromJson', () {
    final stub = AlertCardData.stub();
    expect(stub.kind, 'ice');
    expect(stub.metrics, isNotEmpty);
    expect(stub.decision?.chips, isNotEmpty);

    final parsed = AlertCardData.fromJson({
      'kind': 'storm',
      'headline': 'Шторм',
      'subtitle': '2 груза',
      'period': '1 ноя – 2 ноя',
      'metrics': [
        {'key': 'wave', 'label': 'Волна', 'value': '3 м'},
      ],
      'decision': null,
    });
    expect(parsed.kind, 'storm');
    expect(parsed.metrics.single.label, 'Волна');
    expect(parsed.decision, isNull);
  });
}

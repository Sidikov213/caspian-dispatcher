import 'package:caspian_dispatcher/api/mappers.dart';
import 'package:caspian_dispatcher/models/cargo.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('numberFromId и display_status', () {
    expect(numberFromId('sh-01'), '№01');
    expect(numberFromId('sh-05'), '№05');
    expect(mapDisplayStatus('at_risk'), CargoStatus.atRisk);
    expect(mapPassState('reissue_pending'), PassStatus.awaitingReissue);
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
    });

    expect(cargo.displayName, '№01 Зерно');
    expect(cargo.riskPercent, 82);
    expect(cargo.departureShiftH, 18);
    expect(cargo.arrivalDelayH, 48);
    expect(cargo.riskFactors, hasLength(1));
    expect(cargo.probabilityDrivers, hasLength(1));
    expect(cargo.probabilityDrivers.first.impactPp, 12.5);
    expect(cargo.status, CargoStatus.atRisk);
  });

  test('decisionSummaryFromAlert: new / accepted / superseded', () {
    expect(
      decisionSummaryFromAlert({
        'status': 'new',
        'starts_in_h': 36,
        'source': 'scenario',
        'options': [],
        'items': [],
      }, {}),
      'Ожидает решения логиста · через 36 ч · сценарий',
    );
    expect(
      decisionSummaryFromAlert({
        'status': 'accepted',
        'accepted_via': 'web',
        'options': [
          {'id': 'mkh', 'recommended': true},
        ],
        'items': [
          {
            'delay_vs_plan_h': 6,
            'to_route': {
              'legs': [
                {'from': 'astrakhan', 'to': 'makhachkala'},
                {'from': 'makhachkala', 'to': 'anzali'},
              ],
            },
          },
        ],
      }, {}),
      'Решение диспетчера: через Махачкалу, +6 ч к плану · сайт',
    );
    expect(
      decisionSummaryFromAlert({
        'status': 'superseded',
        'status_note': 'угроза снята',
        'options': [],
        'items': [],
      }, {}),
      'Угроза снята — решение не нужно',
    );
  });

  test('fmtCo2SavedPct из stats.co2_saved_pct', () {
    expect(fmtCo2SavedPct(6.9), '−6,9% CO₂');
    expect(fmtCo2SavedPct(0), isNull);
    expect(fmtCo2SavedPct(null), isNull);
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
}

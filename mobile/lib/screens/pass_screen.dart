import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/logo_mark.dart';

/// 10 — QR из JWT token.
class PassScreen extends StatelessWidget {
  const PassScreen({super.key, required this.cargoId, this.storedPassId});

  final String cargoId;
  final String? storedPassId;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final cargo = app.byId(cargoId);
    final stored = storedPassId == null
        ? null
        : app.storedPassById(storedPassId!);

    final token = stored?.token ?? cargo?.passToken;
    final status = stored?.status ?? cargo?.passStatus ?? PassStatus.none;
    final port = stored?.checkpointLabel ?? cargo?.passPort ?? '—';
    final until = stored?.validUntilLabel ?? cargo?.passValidUntil ?? '—';
    final record = stored?.id ?? cargo?.passRecord ?? '—';
    final hash = stored != null
        ? (stored.docHash.length > 8
              ? '${stored.docHash.substring(0, 4)}…${stored.docHash.substring(stored.docHash.length - 4)}'
              : stored.docHash)
        : (cargo?.passHash ?? '—');

    if (token == null || token.isEmpty || status == PassStatus.none) {
      return Scaffold(
        appBar: AppBar(title: const Text('Пропуск')),
        body: const EmptyStateView(
          icon: Icons.qr_code_2_outlined,
          title: 'Пропуск ещё не оформлен',
          subtitle: 'Оформите пропуск из карточки груза.',
        ),
      );
    }

    final dimmed =
        status == PassStatus.invalid || status == PassStatus.reissued;

    return Scaffold(
      appBar: AppBar(title: const Text('Цифровой пропуск')),
      body: ListView(
        padding: AppSpacing.page,
        children: [
          if (status == PassStatus.awaitingReissue)
            Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: AppCard(
                borderColor: AppColors.warning,
                child: Text(
                  'Маршрут изменён, пропуск ожидает переоформления',
                  style: TextStyle(
                    color: AppColors.warning,
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
              ),
            ),
          AppCard(
            padding: const EdgeInsets.fromLTRB(18, 20, 18, 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Center(child: LogoMark(size: 36)),
                const SizedBox(height: 8),
                Text(
                  'Демонстрационный пропуск',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(AppSpacing.radius),
                  ),
                  child: Column(
                    children: [
                      Opacity(
                        opacity: dimmed ? 0.35 : 1,
                        child: QrImageView(
                          data: token,
                          version: QrVersions.auto,
                          size: 200,
                          backgroundColor: Colors.white,
                          eyeStyle: const QrEyeStyle(
                            eyeShape: QrEyeShape.square,
                            color: Color(0xFF0B1220),
                          ),
                          dataModuleStyle: const QrDataModuleStyle(
                            dataModuleShape: QrDataModuleShape.square,
                            color: Color(0xFF0B1220),
                          ),
                        ),
                      ),
                      if (status == PassStatus.invalid) ...[
                        const SizedBox(height: 10),
                        SoftBadge(
                          label: 'QR недействителен',
                          background: AppColors.dangerBg,
                          foreground: AppColors.danger,
                        ),
                      ],
                      if (status == PassStatus.reissued) ...[
                        const SizedBox(height: 10),
                        SoftBadge(
                          label: 'Переоформлен — историческая копия',
                          background: AppColors.infoBg,
                          foreground: AppColors.primary,
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                _row(
                  'Груз',
                  cargo?.displayName ?? stored?.cargoTitle ?? cargoId,
                ),
                _row('Пункт пропуска', port),
                _row('Срок действия', until),
                _row('Номер записи', record),
                _row('Хэш документа', hash),
                const SizedBox(height: 4),
                Align(
                  alignment: Alignment.centerRight,
                  child: PassStatusPill(status: status),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Это внутренний демонстрационный пропуск сервиса, не официальный портовый документ. Копия сохранена на устройстве.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 12,
              height: 1.35,
            ),
          ),
          if (status == PassStatus.awaitingReissue && cargo != null) ...[
            const SizedBox(height: 14),
            FilledButton(
              onPressed: () async {
                final err = await app.retryPass(cargo.id);
                if (!context.mounted) return;
                ScaffoldMessenger.of(context)
                    .showSnackBar(SnackBar(content: Text(err ?? 'Готово')));
              },
              child: const Text('Повторить'),
            ),
          ],
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: () async {
              try {
                final res = await app.verifyStoredPass(
                  stored ??
                      StoredPass(
                        id: cargo!.passId!,
                        shipmentId: cargo.id,
                        token: token,
                        docHash: cargo.passDocHash ?? '',
                        blockHash: cargo.passBlockHash ?? '',
                        checkpointNode: '',
                        checkpointLabel: port,
                        validUntilIso: '',
                        validUntilLabel: until,
                        status: status,
                        receivedAtIso: DateTime.now().toIso8601String(),
                      ),
                );
                if (!context.mounted) return;
                final valid = res['valid'] == true;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      valid
                          ? 'Проверка: действителен'
                          : 'Проверка: ${res['reason'] ?? 'недействителен'}',
                    ),
                  ),
                );
              } catch (e) {
                if (!context.mounted) return;
                ScaffoldMessenger.of(context)
                    .showSnackBar(SnackBar(content: Text('$e')));
              }
            },
            child: const Text('Проверить на сервере'),
          ),
        ],
      ),
    );
  }

  Widget _row(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              k,
              style: TextStyle(color: AppColors.muted, fontSize: 13),
            ),
          ),
          Expanded(
            child: Text(
              v,
              style: TextStyle(
                color: AppColors.text,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

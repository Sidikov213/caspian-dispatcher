import 'package:flutter/material.dart';

import '../services/camera_permission.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import 'document_capture_screen.dart';
import 'pass_screen.dart';

/// Цифровой коридор: документ → поля → пропуск → реестр (любой груз).
class CorridorScreen extends StatelessWidget {
  const CorridorScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final cargo = app.byId(cargoId);
    if (cargo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Цифровой коридор')),
        body: const EmptyStateView(
          icon: Icons.search_off_rounded,
          title: 'Груз не найден',
          subtitle: 'Обновите список грузов и откройте карточку снова.',
        ),
      );
    }

    final p = app.corridorProgress(cargo);
    final steps = [
      ('Документ загружен', 'Счёт на сервере', p.documentUploaded),
      ('Поля проверены', 'Подтверждение экспедитором', p.fieldsChecked),
      ('Пропуск выдан', 'Электронный код для пункта пропуска', p.passIssued),
      ('Запись в реестре', 'Отпечаток записи в цепочке', p.ledgerRecorded),
    ];

    return Scaffold(
      appBar: AppBar(title: Text('Коридор · ${cargo.number}')),
      body: ListView(
        padding: AppSpacing.page,
        children: [
          Text(
            cargo.displayName,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 22,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Один документ: счёт. Статусы по фактическим данным.',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
          ),
          const SizedBox(height: 18),
          for (var i = 0; i < steps.length; i++) ...[
            AppCard(
              borderColor: steps[i].$3 ? AppColors.success : AppColors.border,
              child: Row(
                children: [
                  Container(
                    width: 28,
                    height: 28,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: steps[i].$3
                          ? AppColors.successBg
                          : AppColors.neutralBg,
                    ),
                    child: Icon(
                      steps[i].$3 ? Icons.check : Icons.circle_outlined,
                      size: 16,
                      color: steps[i].$3 ? AppColors.success : AppColors.muted,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${i + 1}. ${steps[i].$1}',
                          style: TextStyle(
                            color: AppColors.text,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        Text(
                          steps[i].$2,
                          style: TextStyle(
                            color: AppColors.muted,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (i != steps.length - 1)
              Padding(
                padding: EdgeInsets.only(left: 27),
                child: SizedBox(
                  height: 12,
                  child: VerticalDivider(
                    width: 2,
                    thickness: 2,
                    color: AppColors.cyan,
                  ),
                ),
              ),
          ],
          const SizedBox(height: 20),
          if (!p.passIssued)
            FilledButton(
              onPressed: () async {
                final allowed = await ensureCameraPermission(context);
                if (!allowed || !context.mounted) return;
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => DocumentCaptureScreen(cargoId: cargo.id),
                  ),
                );
              },
              child: const Text('Загрузить счёт'),
            )
          else
            FilledButton(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => PassScreen(cargoId: cargo.id),
                  ),
                );
              },
              child: const Text('Открыть пропуск'),
            ),
        ],
      ),
    );
  }
}

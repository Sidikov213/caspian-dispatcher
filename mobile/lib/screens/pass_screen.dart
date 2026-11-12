import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../api/api_messages.dart';
import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/logo_mark.dart';

/// QR-пропуск из JWT token.
class PassScreen extends StatefulWidget {
  const PassScreen({super.key, required this.cargoId, this.storedPassId});

  final String cargoId;
  final String? storedPassId;

  @override
  State<PassScreen> createState() => _PassScreenState();
}

class _PassScreenState extends State<PassScreen> {
  bool _verifying = false;
  bool? _verifyOk;
  String? _verifyText;

  Future<void> _verify(StoredPass pass) async {
    if (_verifying) return;
    setState(() {
      _verifying = true;
      _verifyOk = null;
      _verifyText = null;
    });
    final app = AppScope.of(context);
    try {
      final res = await app.verifyStoredPass(pass);
      if (!mounted) return;
      final valid = res['valid'] == true;
      setState(() {
        _verifyOk = valid;
        _verifyText = valid
            ? 'Пропуск действителен'
            : apiReasonRu(
                res['reason']?.toString(),
                fallback: 'недействителен',
              );
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _verifyOk = false;
        _verifyText = apiErrorRu('$e');
      });
    } finally {
      if (mounted) setState(() => _verifying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    if (app.showDataPlaceholders) {
      return Scaffold(
        appBar: AppBar(title: const Text('Цифровой пропуск')),
        body: const DetailCardsLoadingSkeleton(cards: 3),
      );
    }
    final cargo = app.byId(widget.cargoId);
    final stored = widget.storedPassId == null
        ? null
        : app.storedPassById(widget.storedPassId!);

    final token = stored?.token ?? cargo?.passToken;
    final status = stored?.status ?? cargo?.passStatus ?? PassStatus.none;
    final port = stored?.checkpointLabel ?? cargo?.passPort ?? '-';
    final until = stored?.validUntilLabel ?? cargo?.passValidUntil ?? '-';
    final record = stored?.id ?? cargo?.passRecord ?? '-';
    final hash = stored != null
        ? (stored.docHash.length > 8
              ? '${stored.docHash.substring(0, 4)}…${stored.docHash.substring(stored.docHash.length - 4)}'
              : stored.docHash)
        : (cargo?.passHash ?? '-');
    final cargoLabel = cargo?.displayName ??
        [
          if ((stored?.cargoNumber ?? '').isNotEmpty) stored!.cargoNumber,
          if ((stored?.cargoTitle ?? '').isNotEmpty) stored!.cargoTitle,
        ].join(' ');

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
    final passForVerify = stored ??
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
        );

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('Цифровой пропуск')),
      body: ListView(
        padding: AppSpacing.pageOf(context),
        children: [
          if (status == PassStatus.awaitingReissue)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: AppCard(
                borderColor: AppColors.warning,
                child: Row(
                  children: [
                    Icon(
                      Icons.warning_amber_rounded,
                      color: AppColors.warning,
                      size: 20,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Маршрут изменён, пропуск ожидает переоформления',
                        style: TextStyle(
                          color: AppColors.warning,
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          height: 1.35,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          AppCard(
            padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    const LogoMark(size: 28),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'Цифровой пропуск',
                        style: TextStyle(
                          color: AppColors.text,
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.2,
                        ),
                      ),
                    ),
                    PassStatusPill(status: status),
                  ],
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                  decoration: BoxDecoration(
                    color: AppColors.isDark
                        ? const Color(0xFF0F172A)
                        : const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(AppSpacing.radius),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius:
                              BorderRadius.circular(AppSpacing.radiusSm),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.06),
                              blurRadius: 16,
                              offset: const Offset(0, 6),
                            ),
                          ],
                        ),
                        child: Opacity(
                          opacity: dimmed ? 0.35 : 1,
                          child: QrImageView(
                            data: token,
                            version: QrVersions.auto,
                            size: 196,
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
                      ),
                      if (status == PassStatus.invalid) ...[
                        const SizedBox(height: 12),
                        SoftBadge(
                          label: 'Код пропуска недействителен',
                          background: AppColors.dangerBg,
                          foreground: AppColors.danger,
                        ),
                      ],
                      if (status == PassStatus.reissued) ...[
                        const SizedBox(height: 12),
                        SoftBadge(
                          label: 'Переоформлен, историческая копия',
                          background: AppColors.infoBg,
                          foreground: AppColors.primary,
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _infoBlock([
                  (
                    'Груз',
                    cargoLabel.isEmpty ? widget.cargoId : cargoLabel,
                  ),
                  ('Пункт пропуска', port),
                  ('Срок действия', until),
                  ('Номер записи', record),
                  ('Отпечаток документа', hash),
                ]),
              ],
            ),
          ),
          if (status == PassStatus.awaitingReissue && cargo != null) ...[
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () async {
                final err = await app.retryPass(cargo.id);
                if (!mounted) return;
                setState(() {
                  _verifyOk = err == null;
                  _verifyText = err ?? 'Пропуск переоформлен';
                });
              },
              child: const Text('Повторить переоформление'),
            ),
          ],
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _verifying ? null : () => _verify(passForVerify),
            icon: _verifying
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.verified_outlined, size: 18),
            label: Text(_verifying ? 'Проверяем…' : 'Проверить на сервере'),
          ),
          if (_verifyText != null) ...[
            const SizedBox(height: 12),
            _VerifyResultBanner(ok: _verifyOk == true, text: _verifyText!),
          ],
        ],
      ),
    );
  }

  Widget _infoBlock(List<(String, String)> rows) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.field,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 118,
                    child: Text(
                      rows[i].$1,
                      style: TextStyle(
                        color: AppColors.muted,
                        fontSize: 13,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      rows[i].$2,
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        height: 1.25,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (i != rows.length - 1)
              Divider(height: 1, thickness: 1, color: AppColors.border),
          ],
        ],
      ),
    );
  }
}

class _VerifyResultBanner extends StatelessWidget {
  const _VerifyResultBanner({required this.ok, required this.text});

  final bool ok;
  final String text;

  @override
  Widget build(BuildContext context) {
    final bg = ok ? AppColors.successBg : AppColors.dangerBg;
    final fg = ok ? AppColors.success : AppColors.danger;
    final border = ok ? AppColors.success : AppColors.danger;
    return AppCard(
      borderColor: border.withValues(alpha: 0.45),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: bg,
              shape: BoxShape.circle,
            ),
            child: Icon(
              ok ? Icons.check_rounded : Icons.error_outline_rounded,
              size: 18,
              color: fg,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ok ? 'Проверка пройдена' : 'Проверка не пройдена',
                  style: TextStyle(
                    color: fg,
                    fontWeight: FontWeight.w800,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  text,
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 13,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

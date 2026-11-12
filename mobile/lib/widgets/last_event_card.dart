import 'package:flutter/material.dart';

import '../models/alert_card.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import 'app_chrome.dart';

/// «Последнее событие»: структурированный `Alert.card` или fallback title + 2 строки.
class LastEventCard extends StatelessWidget {
  const LastEventCard({
    super.key,
    this.card,
    this.fallbackTitle,
    this.fallbackBody,
    this.fallbackDecision,
    this.onTap,
  });

  final AlertCardData? card;
  final String? fallbackTitle;
  final String? fallbackBody;
  final String? fallbackDecision;
  final VoidCallback? onTap;

  static String firstTwoLines(String text) {
    final lines = text
        .split(RegExp(r'\r?\n'))
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (lines.isEmpty) return '';
    return lines.take(2).join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final hasAnything =
        card != null ||
        (fallbackTitle != null && fallbackTitle!.isNotEmpty) ||
        (fallbackBody != null && fallbackBody!.isNotEmpty);

    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionLabel('Последнее событие'),
          const SizedBox(height: 10),
          if (!hasAnything)
            Text(
              'Алертов нет',
              style: TextStyle(color: AppColors.textSecondary),
            )
          else if (card != null)
            _Structured(card: card!)
          else
            _Fallback(
              title: fallbackTitle ?? '',
              body: firstTwoLines(fallbackBody ?? ''),
              decision: fallbackDecision,
            ),
        ],
      ),
    );
  }
}

class _Structured extends StatelessWidget {
  const _Structured({required this.card});

  final AlertCardData card;

  @override
  Widget build(BuildContext context) {
    final impact = card.impact?.line;
    final route = card.route?.line;
    final decision = card.decision;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (card.kind.isNotEmpty) ...[
          SoftBadge(
            label: _kindLabel(card.kind),
            background: AppColors.warningBg,
            foreground: AppColors.warning,
          ),
          const SizedBox(height: 10),
        ],
        Text(
          card.headline,
          style: TextStyle(
            color: AppColors.text,
            fontWeight: FontWeight.w800,
            fontSize: 16,
            letterSpacing: -0.2,
            height: 1.25,
          ),
        ),
        if (card.subtitle.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(
            card.subtitle,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
        if (card.period.isNotEmpty) ...[
          const SizedBox(height: 10),
          Row(
            children: [
              Icon(Icons.schedule_outlined, size: 16, color: AppColors.muted),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  card.period,
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                    height: 1.3,
                  ),
                ),
              ),
            ],
          ),
        ],
        if (card.metrics.isNotEmpty) ...[
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final m in card.metrics)
                _MetricChip(label: m.label, value: m.value),
            ],
          ),
        ],
        if (route != null && route.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            route,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.35,
            ),
          ),
        ],
        if (impact != null && impact.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            impact,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.35,
            ),
          ),
        ],
        if (decision != null && decision.chips.isNotEmpty) ...[
          const SizedBox(height: 14),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.infoBg,
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Решение',
                  style: TextStyle(
                    color: AppColors.primary,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final chip in decision.chips)
                      SoftBadge(
                        label: chip,
                        background: AppColors.card,
                        foreground: AppColors.primary,
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  String _kindLabel(String kind) => switch (kind) {
    'ice' => 'Лёд',
    'storm' => 'Шторм',
    'congestion' => 'Затор',
    'customs' => 'Таможня',
    _ => kind,
  };
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.field,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 13,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _Fallback extends StatelessWidget {
  const _Fallback({
    required this.title,
    required this.body,
    this.decision,
  });

  final String title;
  final String body;
  final String? decision;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title.isNotEmpty)
          Text(
            title,
            style: TextStyle(
              color: AppColors.text,
              fontWeight: FontWeight.w700,
              fontSize: 15,
              height: 1.3,
            ),
          ),
        if (body.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            body,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 13,
              height: 1.4,
            ),
          ),
        ],
        if (decision != null && decision!.isNotEmpty) ...[
          const SizedBox(height: 10),
          SoftBadge(
            label: decision!,
            background: AppColors.infoBg,
            foreground: AppColors.primary,
          ),
        ],
      ],
    );
  }
}

import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.onTap,
    this.borderColor,
  });

  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        border: Border.all(color: borderColor ?? AppColors.border),
      ),
      child: child,
    );
    if (onTap == null) return content;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        child: content,
      ),
    );
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.status, this.compact = false});

  final CargoStatus status;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.statusFg(status.tone);
    final bg = AppColors.statusBg(status.tone);
    final showCheck = status == CargoStatus.delivered;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 10,
        vertical: compact ? 4 : 6,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showCheck) ...[
            Icon(Icons.check_rounded, size: compact ? 12 : 14, color: fg),
            SizedBox(width: compact ? 3 : 4),
          ],
          Text(
            status.label,
            style: TextStyle(
              color: fg,
              fontSize: compact ? 11 : 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class PassStatusPill extends StatelessWidget {
  const PassStatusPill({super.key, required this.status});

  final PassStatus status;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (status) {
      PassStatus.none => (AppColors.neutralBg, AppColors.muted),
      PassStatus.active => (AppColors.successBg, AppColors.success),
      PassStatus.reissued => (AppColors.infoBg, AppColors.primary),
      PassStatus.awaitingReissue => (AppColors.warningBg, AppColors.warning),
      PassStatus.invalid => (AppColors.dangerBg, AppColors.danger),
      PassStatus.unknown => (AppColors.neutralBg, AppColors.muted),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: Text(
        status.label,
        style: TextStyle(color: fg, fontSize: 12, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class SoftBadge extends StatelessWidget {
  const SoftBadge({
    super.key,
    required this.label,
    this.background,
    this.foreground,
  });

  final String label;
  final Color? background;
  final Color? foreground;

  @override
  Widget build(BuildContext context) {
    final bg = background ?? AppColors.infoBg;
    final fg = foreground ?? AppColors.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      ),
      child: Text(
        label,
        style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: AppColors.muted,
        fontSize: 12,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.04,
      ),
    );
  }
}

class MetricBlock extends StatelessWidget {
  const MetricBlock({
    super.key,
    required this.value,
    required this.label,
    this.accent,
  });

  final String value;
  final String label;
  final Color? accent;

  @override
  Widget build(BuildContext context) {
    final valueColor = accent ?? AppColors.primary;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: TextStyle(
            color: valueColor,
            fontSize: 32,
            fontWeight: FontWeight.w800,
            height: 1.05,
            letterSpacing: -0.6,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
        ),
      ],
    );
  }
}

class EmptyStateView extends StatelessWidget {
  const EmptyStateView({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: AppColors.muted),
            const SizedBox(height: 14),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.text,
                fontSize: 17,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.textSecondary,
                fontSize: 14,
                height: 1.4,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: 18),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

class ErrorStateView extends StatelessWidget {
  const ErrorStateView({
    super.key,
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return EmptyStateView(
      icon: Icons.wifi_off_rounded,
      title: 'Нет связи с сервером',
      subtitle: message,
      actionLabel: 'Повторить',
      onAction: onRetry,
    );
  }
}

class SkeletonBlock extends StatelessWidget {
  const SkeletonBlock({
    super.key,
    this.width,
    required this.height,
    this.radius = AppSpacing.radiusSm,
  });

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: AppColors.skeleton,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

class _SkeletonCard extends StatelessWidget {
  const _SkeletonCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

/// Обзор: метрики + экономия + волны + последнее событие.
class OverviewLoadingSkeleton extends StatelessWidget {
  const OverviewLoadingSkeleton({super.key, this.waveCount = 4});

  final int waveCount;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: AppSpacing.page,
      children: [
        const SkeletonBlock(width: 220, height: 14),
        const SizedBox(height: 16),
        const Row(
          children: [
            Expanded(child: _MetricSkeleton()),
            SizedBox(width: 10),
            Expanded(child: _MetricSkeleton()),
          ],
        ),
        const SizedBox(height: 12),
        const _EconomySkeleton(),
        const SizedBox(height: 12),
        _WavesSkeleton(waveCount: waveCount),
        const SizedBox(height: 12),
        const _LastEventSkeleton(),
      ],
    );
  }
}

class _MetricSkeleton extends StatelessWidget {
  const _MetricSkeleton();

  @override
  Widget build(BuildContext context) {
    return const _SkeletonCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // MetricBlock: 32px value + 4 + 13px label
          SkeletonBlock(width: 42, height: 34),
          SizedBox(height: 4),
          SkeletonBlock(width: 88, height: 13),
        ],
      ),
    );
  }
}

class _EconomySkeleton extends StatelessWidget {
  const _EconomySkeleton();

  @override
  Widget build(BuildContext context) {
    return const _SkeletonCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBlock(width: 120, height: 12),
          SizedBox(height: 12),
          SkeletonBlock(height: 64, radius: AppSpacing.radiusSm),
          SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: SkeletonBlock(height: 58, radius: AppSpacing.radiusSm),
              ),
              SizedBox(width: 8),
              Expanded(
                child: SkeletonBlock(height: 58, radius: AppSpacing.radiusSm),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _WavesSkeleton extends StatelessWidget {
  const _WavesSkeleton({required this.waveCount});

  final int waveCount;

  @override
  Widget build(BuildContext context) {
    return _SkeletonCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SkeletonBlock(width: 100, height: 12),
          const SizedBox(height: 10),
          for (var i = 0; i < waveCount; i++) ...[
            const Row(
              children: [
                Expanded(child: SkeletonBlock(height: 14)),
                SizedBox(width: 12),
                SkeletonBlock(width: 56, height: 22, radius: AppSpacing.radiusSm),
              ],
            ),
            if (i != waveCount - 1) const SizedBox(height: 8),
          ],
          const SizedBox(height: 8),
          const SkeletonBlock(width: 180, height: 12),
        ],
      ),
    );
  }
}

class _LastEventSkeleton extends StatelessWidget {
  const _LastEventSkeleton();

  @override
  Widget build(BuildContext context) {
    return const _SkeletonCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBlock(width: 130, height: 12),
          SizedBox(height: 10),
          SkeletonBlock(width: 64, height: 22, radius: AppSpacing.radiusSm),
          SizedBox(height: 10),
          SkeletonBlock(height: 18),
          SizedBox(height: 4),
          SkeletonBlock(width: 200, height: 13),
          SizedBox(height: 10),
          SkeletonBlock(width: 160, height: 13),
          SizedBox(height: 12),
          Row(
            children: [
              SkeletonBlock(width: 88, height: 28, radius: AppSpacing.radiusSm),
              SizedBox(width: 8),
              SkeletonBlock(width: 72, height: 28, radius: AppSpacing.radiusSm),
            ],
          ),
          SizedBox(height: 12),
          SkeletonBlock(height: 13),
          SizedBox(height: 6),
          SkeletonBlock(width: 240, height: 13),
          SizedBox(height: 14),
          SkeletonBlock(height: 56, radius: AppSpacing.radiusSm),
        ],
      ),
    );
  }
}

/// Список грузов: карточка ≈ title + маршрут + риск.
class CargoListLoadingSkeleton extends StatelessWidget {
  const CargoListLoadingSkeleton({super.key, this.itemCount = 5});

  final int itemCount;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: AppSpacing.page,
      itemCount: itemCount,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (_, _) => const _SkeletonCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: SkeletonBlock(height: 16)),
                SizedBox(width: 10),
                SkeletonBlock(width: 78, height: 22, radius: AppSpacing.radiusSm),
              ],
            ),
            SizedBox(height: 6),
            SkeletonBlock(height: 13),
            SizedBox(height: 8),
            SkeletonBlock(width: 170, height: 12),
          ],
        ),
      ),
    );
  }
}

/// Список пропусков: title + пункт/срок + id.
class PassesListLoadingSkeleton extends StatelessWidget {
  const PassesListLoadingSkeleton({super.key, this.itemCount = 5});

  final int itemCount;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: AppSpacing.page,
      itemCount: itemCount,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (_, _) => const _SkeletonCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: SkeletonBlock(height: 15)),
                SizedBox(width: 10),
                SkeletonBlock(width: 92, height: 24, radius: AppSpacing.radiusSm),
              ],
            ),
            SizedBox(height: 6),
            SkeletonBlock(height: 13),
            SizedBox(height: 4),
            SkeletonBlock(width: 120, height: 11),
          ],
        ),
      ),
    );
  }
}

class LoadingListSkeleton extends StatelessWidget {
  const LoadingListSkeleton({super.key});

  @override
  Widget build(BuildContext context) => const CargoListLoadingSkeleton();
}

/// Карточка груза (цифровой двойник).
class TwinLoadingSkeleton extends StatelessWidget {
  const TwinLoadingSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: AppSpacing.pageOf(context),
      children: const [
        SkeletonBlock(width: 120, height: 11),
        SizedBox(height: 8),
        SkeletonBlock(width: 180, height: 26),
        SizedBox(height: 8),
        Row(
          children: [
            Expanded(child: SkeletonBlock(height: 13)),
            SizedBox(width: 10),
            SkeletonBlock(width: 78, height: 22, radius: AppSpacing.radiusSm),
          ],
        ),
        SizedBox(height: 16),
        SkeletonBlock(height: 168, radius: AppSpacing.radius),
        SizedBox(height: 18),
        Row(
          children: [
            Expanded(child: SkeletonBlock(height: 18)),
            SkeletonBlock(width: 90, height: 12),
          ],
        ),
        SizedBox(height: 12),
        _TwinStageSkeleton(),
        SizedBox(height: 10),
        _TwinStageSkeleton(),
        SizedBox(height: 10),
        _TwinStageSkeleton(),
        SizedBox(height: 10),
        _TwinStageSkeleton(),
        SizedBox(height: 16),
        _SkeletonCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  SkeletonBlock(width: 18, height: 18, radius: 4),
                  SizedBox(width: 8),
                  Expanded(child: SkeletonBlock(height: 14)),
                  SkeletonBlock(width: 72, height: 18),
                ],
              ),
              SizedBox(height: 10),
              SkeletonBlock(height: 5, radius: 99),
              SizedBox(height: 10),
              SkeletonBlock(width: 220, height: 12),
            ],
          ),
        ),
        SizedBox(height: 12),
        SkeletonBlock(height: 74, radius: AppSpacing.radius),
        SizedBox(height: 18),
        SkeletonBlock(height: 48, radius: AppSpacing.radiusSm),
        SizedBox(height: 10),
        SkeletonBlock(height: 48, radius: AppSpacing.radiusSm),
      ],
    );
  }
}

class _TwinStageSkeleton extends StatelessWidget {
  const _TwinStageSkeleton();

  @override
  Widget build(BuildContext context) {
    return const Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SkeletonBlock(width: 30, height: 30, radius: 7),
        SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: SkeletonBlock(height: 14)),
                  SizedBox(width: 8),
                  SkeletonBlock(width: 110, height: 12),
                ],
              ),
              SizedBox(height: 6),
              SkeletonBlock(width: 140, height: 12),
            ],
          ),
        ),
      ],
    );
  }
}

/// Экран прогноза.
class ForecastLoadingSkeleton extends StatelessWidget {
  const ForecastLoadingSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: AppSpacing.pageOf(context),
      children: const [
        SkeletonBlock(width: 130, height: 11),
        SizedBox(height: 8),
        SkeletonBlock(width: 200, height: 22),
        SizedBox(height: 6),
        SkeletonBlock(width: 240, height: 13),
        SizedBox(height: 16),
        SkeletonBlock(height: 150, radius: AppSpacing.radius),
        SizedBox(height: 12),
        _SkeletonCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonBlock(width: 70, height: 12),
              SizedBox(height: 10),
              SkeletonBlock(height: 13),
              SizedBox(height: 6),
              SkeletonBlock(height: 5, radius: 99),
              SizedBox(height: 12),
              SkeletonBlock(height: 13),
              SizedBox(height: 6),
              SkeletonBlock(height: 5, radius: 99),
              SizedBox(height: 12),
              SkeletonBlock(height: 13),
              SizedBox(height: 6),
              SkeletonBlock(height: 5, radius: 99),
            ],
          ),
        ),
        SizedBox(height: 12),
        _SkeletonCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonBlock(width: 120, height: 12),
              SizedBox(height: 10),
              SkeletonBlock(height: 13),
              SizedBox(height: 6),
              SkeletonBlock(height: 5, radius: 99),
              SizedBox(height: 12),
              SkeletonBlock(height: 13),
              SizedBox(height: 6),
              SkeletonBlock(height: 5, radius: 99),
            ],
          ),
        ),
        SizedBox(height: 12),
        _SkeletonCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonBlock(width: 90, height: 12),
              SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: SkeletonBlock(
                      height: 58,
                      radius: AppSpacing.radiusSm,
                    ),
                  ),
                  SizedBox(width: 8),
                  Expanded(
                    child: SkeletonBlock(
                      height: 58,
                      radius: AppSpacing.radiusSm,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        SizedBox(height: 12),
        SkeletonBlock(height: 96, radius: AppSpacing.radius),
      ],
    );
  }
}

/// Пропуск / коридор — универсальный набор карточек.
class DetailCardsLoadingSkeleton extends StatelessWidget {
  const DetailCardsLoadingSkeleton({super.key, this.cards = 4});

  final int cards;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: AppSpacing.pageOf(context),
      itemCount: cards,
      separatorBuilder: (_, _) => const SizedBox(height: 12),
      itemBuilder: (_, i) => SkeletonBlock(
        height: i == 0 ? 120 : 88,
        radius: AppSpacing.radius,
      ),
    );
  }
}

class AppBottomNav extends StatelessWidget {
  const AppBottomNav({super.key, required this.index, required this.onChanged});

  final int index;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      padding: EdgeInsets.fromLTRB(
        12,
        8,
        12,
        8 + MediaQuery.viewPaddingOf(context).bottom,
      ),
      child: Row(
        children: [
          _NavItem(
            label: 'Обзор',
            icon: Icons.grid_view_rounded,
            selected: index == 0,
            onTap: () => onChanged(0),
          ),
          _NavItem(
            label: 'Грузы',
            icon: Icons.inventory_2_outlined,
            selected: index == 1,
            onTap: () => onChanged(1),
          ),
          _NavItem(
            label: 'Пропуска',
            icon: Icons.badge_outlined,
            selected: index == 2,
            onTap: () => onChanged(2),
          ),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected ? AppColors.infoBg : null,
            borderRadius: BorderRadius.circular(AppSpacing.radius),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 20,
                color: selected ? AppColors.primary : AppColors.muted,
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: selected ? AppColors.primary : AppColors.muted,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

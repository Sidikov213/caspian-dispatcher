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

class LoadingListSkeleton extends StatelessWidget {
  const LoadingListSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: AppSpacing.page,
      itemCount: 4,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (_, _) => Container(
        height: 96,
        decoration: BoxDecoration(
          color: AppColors.skeleton,
          borderRadius: BorderRadius.circular(AppSpacing.radius),
        ),
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
        8 + MediaQuery.paddingOf(context).bottom,
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

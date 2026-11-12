import 'package:flutter/material.dart';

import '../state/auth_controller.dart';
import '../state/notification_controller.dart';
import '../theme/app_colors.dart';
import 'home_shell.dart';

/// Сначала объяснение, по «Продолжить» — системный запрос уведомлений.
class NotificationsOnboardingScreen extends StatefulWidget {
  const NotificationsOnboardingScreen({super.key});

  @override
  State<NotificationsOnboardingScreen> createState() =>
      _NotificationsOnboardingScreenState();
}

class _NotificationsOnboardingScreenState
    extends State<NotificationsOnboardingScreen> {
  bool _busy = false;

  Future<void> _continue() async {
    if (_busy) return;
    setState(() => _busy = true);
    final notifications = NotificationScope.of(context);
    final auth = AuthScope.of(context);
    await notifications.requestFromOnboarding();
    await auth.syncPushDevices();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 280),
        pageBuilder: (context, animation, secondaryAnimation) =>
            const HomeShell(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(opacity: animation, child: child);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(
                Icons.notifications_active_outlined,
                size: 64,
                color: AppColors.primary,
              ),
              const SizedBox(height: 20),
              Text(
                'Включите уведомления',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Так вы сразу узнаете о рисках по маршруту, статусах грузов и сроках пропуска.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.textSecondary,
                  fontSize: 15,
                  height: 1.45,
                ),
              ),
              const SizedBox(height: 28),
              FilledButton(
                onPressed: _busy ? null : _continue,
                child: _busy
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Продолжить'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

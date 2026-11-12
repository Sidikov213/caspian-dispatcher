import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../state/auth_controller.dart';
import '../state/notification_controller.dart';
import '../theme/app_colors.dart';
import '../widgets/logo_mark.dart';
import 'auth_screen.dart';
import 'home_shell.dart';
import 'notifications_onboarding_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim;

  @override
  void initState() {
    super.initState();
    _anim = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..forward();
    WidgetsBinding.instance.addPostFrameCallback((_) => _boot());
  }

  Future<void> _boot() async {
    final auth = AuthScope.of(context);
    final app = AppScope.of(context);
    final notifications = NotificationScope.of(context);
    final minDelay = Future<void>.delayed(const Duration(milliseconds: 900));

    await Future.wait([auth.restoreSession(), minDelay]);
    if (!mounted) return;

    if (!auth.isLoggedIn) {
      _go(const AuthScreen());
      return;
    }

    await app.bootstrap();
    if (!mounted) return;

    final next = notifications.promptSeen
        ? const HomeShell()
        : const NotificationsOnboardingScreen();
    _go(next);
  }

  void _go(Widget page) {
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 320),
        pageBuilder: (context, animation, secondaryAnimation) => page,
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(opacity: animation, child: child);
        },
      ),
    );
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Center(
        child: FadeTransition(
          opacity: CurvedAnimation(parent: _anim, curve: Curves.easeOut),
          child: ScaleTransition(
            scale: Tween(begin: 0.92, end: 1.0).animate(
              CurvedAnimation(parent: _anim, curve: Curves.easeOutCubic),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const LogoMark(size: 88),
                const SizedBox(height: 18),
                Text(
                  'Каспийский диспетчер',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.3,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

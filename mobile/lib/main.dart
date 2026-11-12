import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api/api_config.dart';
import 'firebase_options.dart';
import 'screens/splash_screen.dart';
import 'state/app_controller.dart';
import 'state/auth_controller.dart';
import 'state/notification_controller.dart';
import 'state/theme_controller.dart';
import 'theme/app_colors.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } on PlatformException catch (e) {
    // Hot restart после добавления плагина — нужен полный flutter run.
    // ignore: avoid_print
    print('Firebase init skipped: $e');
  } catch (e) {
    // ignore: avoid_print
    print('Firebase init skipped: $e');
  }
  // ignore: avoid_print
  print(
    'API config: baseUrl=${ApiConfig.baseUrl}, '
    'apiKey=${ApiConfig.hasApiKey ? "set" : "MISSING"} '
    '(нужен --dart-define-from-file=.env)',
  );
  final themeController = ThemeController();
  final notificationController = NotificationController();
  final authController = AuthController();
  await Future.wait([themeController.load(), notificationController.load()]);
  runApp(
    CaspianDispatcherApp(
      controller: AppController(),
      themeController: themeController,
      notificationController: notificationController,
      authController: authController,
    ),
  );
}

class CaspianDispatcherApp extends StatelessWidget {
  const CaspianDispatcherApp({
    super.key,
    required this.controller,
    required this.themeController,
    required this.notificationController,
    required this.authController,
  });

  final AppController controller;
  final ThemeController themeController;
  final NotificationController notificationController;
  final AuthController authController;

  @override
  Widget build(BuildContext context) {
    return ThemeScope(
      controller: themeController,
      child: NotificationScope(
        controller: notificationController,
        child: AuthScope(
          controller: authController,
          child: AppScope(
            controller: controller,
            child: ListenableBuilder(
              listenable: Listenable.merge([
                themeController,
                notificationController,
                authController,
              ]),
              builder: (context, _) {
                return MaterialApp(
                  title: 'Диспетчер',
                  debugShowCheckedModeBanner: false,
                  theme: buildAppTheme(Brightness.light),
                  darkTheme: buildAppTheme(Brightness.dark),
                  themeMode: themeController.mode,
                  builder: (context, child) {
                    final brightness = Theme.of(context).brightness;
                    AppColors.bind(brightness);
                    final overlay = brightness == Brightness.dark
                        ? SystemUiOverlayStyle.light
                        : SystemUiOverlayStyle.dark;
                    return AnnotatedRegion<SystemUiOverlayStyle>(
                      value: overlay.copyWith(
                        statusBarColor: Colors.transparent,
                      ),
                      child: KeyedSubtree(
                        key: ValueKey(brightness),
                        child: child ?? const SizedBox.shrink(),
                      ),
                    );
                  },
                  home: const SplashScreen(),
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

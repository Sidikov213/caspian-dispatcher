import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../widgets/app_chrome.dart';
import 'my_cargos_screen.dart';
import 'overview_screen.dart';
import 'passes_list_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final app = AppScope.of(context);
    // Не гасим WS на inactive — на iOS это мигание (шторка, фокус IDE),
    // из‑за него сокет рвётся и включается HTTP-опрос каждые 3 с.
    if (state == AppLifecycleState.resumed) {
      app.startPolling();
      unawaited(app.onAppResumed());
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      app.stopPolling();
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final index = app.homeTab;
    final overlay = Theme.of(context).brightness == Brightness.dark
        ? SystemUiOverlayStyle.light
        : SystemUiOverlayStyle.dark;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: overlay,
      child: Scaffold(
        backgroundColor: AppColors.background,
        body: SafeArea(
          bottom: false,
          child: IndexedStack(
            index: index,
            children: const [
              OverviewScreen(),
              MyCargosScreen(),
              PassesListScreen(),
            ],
          ),
        ),
        bottomNavigationBar: AppBottomNav(
          index: index,
          onChanged: app.setHomeTab,
        ),
      ),
    );
  }
}

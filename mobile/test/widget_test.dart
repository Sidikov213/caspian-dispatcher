import 'package:caspian_dispatcher/models/cargo.dart';
import 'package:caspian_dispatcher/screens/home_shell.dart';
import 'package:caspian_dispatcher/state/app_controller.dart';
import 'package:caspian_dispatcher/state/theme_controller.dart';
import 'package:caspian_dispatcher/theme/app_colors.dart';
import 'package:caspian_dispatcher/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Нижнее меню: три вкладки', (tester) async {
    final controller = AppController();
    final theme = ThemeController();
    await tester.pumpWidget(
      ThemeScope(
        controller: theme,
        child: AppScope(
          controller: controller,
          child: MaterialApp(
            theme: buildAppTheme(Brightness.light),
            darkTheme: buildAppTheme(Brightness.dark),
            themeMode: ThemeMode.dark,
            home: const HomeShell(),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('Обзор'), findsWidgets);
    expect(find.text('Грузы'), findsOneWidget);
    expect(find.text('Пропуска'), findsWidgets);
  });

  test('Тема: палитра переключается', () {
    AppColors.bind(Brightness.dark);
    expect(AppColors.background, const Color(0xFF0B1220));
    AppColors.bind(Brightness.light);
    expect(AppColors.background, const Color(0xFFFFFFFF));
    AppColors.bind(Brightness.dark);
  });

  test('Валидация веса >5%', () {
    final controller = AppController();
    final cargo = Cargo(
      id: 'sh-05',
      number: '№05',
      title: 'Удобрения',
      weight: '20 т',
      weightTons: 20,
      route: 'Астрахань → Энзели',
      origin: 'Астрахань',
      destination: 'Энзели',
      status: CargoStatus.planned,
      nextPoint: 'Энзели',
      arrival: '-',
    );
    controller.updateInvoice(
      const InvoiceFields(
        product: 'Удобрения',
        hsCode: '3102',
        weight: '30',
        amount: '100',
        origin: 'RU',
      ),
    );
    expect(controller.validateInvoice(cargo), contains('5%'));
  });

  test('Статусы груза', () {
    expect(CargoStatus.planned.label, 'Запланирован');
    expect(CargoStatus.inTransit.label, 'В пути');
    expect(CargoStatus.atRisk.label, 'Под риском');
    expect(CargoStatus.rerouted.label, 'Перестроен');
    expect(CargoStatus.delivered.label, 'Доставлен');
  });
}

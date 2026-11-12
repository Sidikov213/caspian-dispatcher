import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import 'pass_screen.dart';

/// Проверка полей → confirm.
class FieldsCheckScreen extends StatefulWidget {
  const FieldsCheckScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  State<FieldsCheckScreen> createState() => _FieldsCheckScreenState();
}

class _FieldsCheckScreenState extends State<FieldsCheckScreen> {
  final _seller = TextEditingController();
  final _buyer = TextEditingController();
  final _product = TextEditingController();
  final _hs = TextEditingController();
  final _weight = TextEditingController();
  final _amount = TextEditingController();
  final _origin = TextEditingController();
  String? _blockError;
  Map<String, String> _fieldErrors = {};
  bool _submitting = false;
  bool _filled = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_filled) return;
    final f = AppScope.of(context).invoice;
    _seller.text = f.seller;
    _buyer.text = f.buyer;
    _product.text = f.product;
    _hs.text = f.hsCode;
    _weight.text = f.weight;
    _amount.text = f.amount;
    _origin.text = f.origin;
    _filled = true;
  }

  @override
  void dispose() {
    _seller.dispose();
    _buyer.dispose();
    _product.dispose();
    _hs.dispose();
    _weight.dispose();
    _amount.dispose();
    _origin.dispose();
    super.dispose();
  }

  void _sync(AppController app) {
    app.updateInvoice(
      InvoiceFields(
        seller: _seller.text,
        buyer: _buyer.text,
        product: _product.text,
        hsCode: _hs.text,
        weight: _weight.text,
        amount: _amount.text,
        origin: _origin.text,
        currency: app.invoice.currency,
        hsCodeDoubt: app.invoice.hsCodeDoubt,
      ),
    );
  }

  void _clearFieldError(String key) {
    if (!_fieldErrors.containsKey(key)) return;
    setState(() {
      _fieldErrors = Map<String, String>.from(_fieldErrors)..remove(key);
    });
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final cargo = app.byId(widget.cargoId);
    if (cargo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Поля документа')),
        body: const EmptyStateView(
          icon: Icons.search_off_rounded,
          title: 'Груз не найден',
          subtitle: 'Вернитесь к списку.',
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Проверка полей')),
      body: ListView(
        padding: AppSpacing.pageOf(context),
        children: [
          Text(
            'Проверьте поля перед выдачей пропуска. Обязательны: товар, ТН ВЭД, вес, стоимость, страна.',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
          ),
          const SizedBox(height: 14),
          _field('Продавец', _seller, keyName: 'seller'),
          _field('Покупатель', _buyer, keyName: 'buyer'),
          _field('Товар', _product, keyName: 'product'),
          _field(
            'Код ТН ВЭД',
            _hs,
            keyName: 'hsCode',
            warning: app.hasHsCodeWarning
                ? 'Сомнение в коде: предупреждение, без блокировки'
                : null,
          ),
          _field('Вес, т', _weight, keyName: 'weight'),
          _field('Стоимость', _amount, keyName: 'amount'),
          _field('Страна происхождения', _origin, keyName: 'origin'),
          if (_blockError != null) ...[
            const SizedBox(height: 8),
            Text(
              _blockError!,
              style: TextStyle(
                color: AppColors.danger,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
          const SizedBox(height: 18),
          FilledButton(
            onPressed: _submitting
                ? null
                : () async {
                    _sync(app);
                    final err = app.validateInvoice(cargo);
                    setState(() {
                      _blockError = err;
                      _fieldErrors = {};
                    });
                    if (err != null) return;
                    final navigator = Navigator.of(context);
                    setState(() => _submitting = true);
                    final result = await app.issuePass(cargo.id);
                    if (!mounted) return;
                    setState(() {
                      _submitting = false;
                      _blockError = result.message;
                      _fieldErrors = result.fields;
                    });
                    if (result.message != null) return;
                    navigator.pushAndRemoveUntil(
                      MaterialPageRoute(
                        builder: (_) => PassScreen(cargoId: cargo.id),
                      ),
                      (route) => route.isFirst,
                    );
                  },
            child: Text(
              _submitting
                  ? 'Выдаём пропуск…'
                  : 'Подтвердить и получить пропуск',
            ),
          ),
        ],
      ),
    );
  }

  Widget _field(
    String label,
    TextEditingController c, {
    required String keyName,
    String? warning,
  }) {
    final error = _fieldErrors[keyName];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: c,
            onChanged: (_) => _clearFieldError(keyName),
            decoration: InputDecoration(
              labelText: label,
              errorText: error,
              enabledBorder: error == null
                  ? null
                  : OutlineInputBorder(
                      borderSide: BorderSide(color: AppColors.danger),
                    ),
              focusedBorder: error == null
                  ? null
                  : OutlineInputBorder(
                      borderSide: BorderSide(color: AppColors.danger, width: 2),
                    ),
            ),
            style: TextStyle(color: AppColors.text),
          ),
          if (warning != null && error == null) ...[
            const SizedBox(height: 4),
            Text(
              warning,
              style: TextStyle(color: AppColors.warning, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

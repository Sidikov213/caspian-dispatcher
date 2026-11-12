import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import 'fields_check_screen.dart';

/// 08 — Съёмка / выбор фото → POST /documents.
class DocumentCaptureScreen extends StatefulWidget {
  const DocumentCaptureScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  State<DocumentCaptureScreen> createState() => _DocumentCaptureScreenState();
}

class _DocumentCaptureScreenState extends State<DocumentCaptureScreen> {
  final _picker = ImagePicker();
  Uint8List? _preview;

  Future<void> _pick(ImageSource source) async {
    final app = AppScope.of(context);
    final file = await _picker.pickImage(
      source: source,
      imageQuality: 85,
      maxWidth: 2000,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    setState(() => _preview = bytes);
    await app.startRecognition(
      widget.cargoId,
      imageBytes: bytes,
      filename: file.name,
    );
    if (!mounted) return;
    if (app.captureError != null) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(app.captureError!)));
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => FieldsCheckScreen(cargoId: widget.cargoId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Документ')),
      body: Padding(
        padding: AppSpacing.page,
        child: Column(
          children: [
            Expanded(
              child: AppCard(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Expanded(
                      child: Container(
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: AppColors.field,
                          borderRadius: BorderRadius.circular(
                            AppSpacing.radius,
                          ),
                          border: Border.all(color: AppColors.border),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            if (_preview != null)
                              Positioned.fill(
                                child: Image.memory(
                                  _preview!,
                                  fit: BoxFit.cover,
                                ),
                              ),
                            if (app.recognizing)
                              Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  CircularProgressIndicator(),
                                  SizedBox(height: 14),
                                  Text(
                                    'Отправляем на сервер…',
                                    style: TextStyle(
                                      color: AppColors.text,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  SizedBox(height: 6),
                                  Text(
                                    'Для демо сервер может вернуть кэш инвойса',
                                    style: TextStyle(
                                      color: AppColors.muted,
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              )
                            else if (_preview == null)
                              Padding(
                                padding: EdgeInsets.symmetric(horizontal: 24),
                                child: Text(
                                  'Сфотографируйте или выберите инвойс',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: AppColors.textSecondary,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Распознавание на стенде может быть кэшированным демо-результатом, не production OCR.',
                      style: TextStyle(
                        color: AppColors.muted,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: app.recognizing
                  ? null
                  : () => _pick(ImageSource.camera),
              child: const Text('Снять'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: app.recognizing
                  ? null
                  : () => _pick(ImageSource.gallery),
              child: const Text('Выбрать из галереи'),
            ),
          ],
        ),
      ),
    );
  }
}

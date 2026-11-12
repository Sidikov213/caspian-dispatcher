import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

/// Запрос доступа к камере перед съёмкой документа.
Future<bool> ensureCameraPermission(BuildContext context) async {
  var status = await Permission.camera.status;
  if (status.isGranted) return true;

  if (status.isDenied) {
    status = await Permission.camera.request();
    if (status.isGranted) return true;
  }

  if (!context.mounted) return false;

  if (status.isPermanentlyDenied || status.isRestricted || status.isDenied) {
    final open = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Нужен доступ к камере'),
        content: const Text(
          'Чтобы сфотографировать счёт, разрешите камеру в настройках телефона.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Настройки'),
          ),
        ],
      ),
    );
    if (open == true) {
      await openAppSettings();
    }
  }
  return false;
}

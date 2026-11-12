import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';

import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import 'fields_check_screen.dart';

/// Съёмка счёта: сразу камера + галерея и кнопка снимка.
class DocumentCaptureScreen extends StatefulWidget {
  const DocumentCaptureScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  State<DocumentCaptureScreen> createState() => _DocumentCaptureScreenState();
}

class _DocumentCaptureScreenState extends State<DocumentCaptureScreen>
    with WidgetsBindingObserver {
  final _picker = ImagePicker();
  CameraController? _camera;
  String? _cameraError;
  bool _busy = false;
  bool _taking = false;
  bool _needSettings = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _openCamera();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _camera?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final cam = _camera;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      cam?.dispose();
      _camera = null;
    } else if (state == AppLifecycleState.resumed) {
      if (_camera == null || !_camera!.value.isInitialized) {
        _openCamera();
      }
    }
  }

  Future<void> _openCamera() async {
    setState(() {
      _cameraError = null;
      _needSettings = false;
    });

    final status = await Permission.camera.status;
    if (!status.isGranted) {
      final asked = await Permission.camera.request();
      if (!asked.isGranted) {
        if (!mounted) return;
        setState(() {
          _needSettings = asked.isPermanentlyDenied || asked.isRestricted;
          _cameraError = _needSettings
              ? 'Нет доступа к камере. Разрешите его в настройках телефона.'
              : 'Без доступа к камере снимок сделать нельзя.';
          _camera = null;
        });
        return;
      }
    }

    try {
      final cams = await availableCameras();
      if (cams.isEmpty) {
        if (!mounted) return;
        setState(() => _cameraError = 'Камера на устройстве не найдена');
        return;
      }
      final back = cams.where(
        (c) => c.lensDirection == CameraLensDirection.back,
      );
      final chosen = back.isNotEmpty ? back.first : cams.first;
      final controller = CameraController(
        chosen,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      await _camera?.dispose();
      setState(() => _camera = controller);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _cameraError =
            'Не удалось открыть камеру. Можно выбрать фото из галереи.';
        _camera = null;
      });
    }
  }

  Future<void> _shoot() async {
    final cam = _camera;
    if (_busy || _taking || cam == null || !cam.value.isInitialized) return;
    setState(() => _taking = true);
    try {
      final shot = await cam.takePicture();
      final bytes = await shot.readAsBytes();
      await _submit(bytes, filename: 'invoice.jpg');
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Не удалось сделать снимок')),
      );
    } finally {
      if (mounted) setState(() => _taking = false);
    }
  }

  Future<void> _fromGallery() async {
    if (_busy) return;
    final file = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 85,
      maxWidth: 2000,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    await _submit(bytes, filename: file.name);
  }

  Future<void> _submit(Uint8List bytes, {required String filename}) async {
    if (_busy) return;
    setState(() => _busy = true);
    final app = AppScope.of(context);
    await app.startRecognition(
      widget.cargoId,
      imageBytes: bytes,
      filename: filename,
    );
    if (!mounted) return;
    if (app.captureError != null) {
      setState(() => _busy = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(app.captureError!)),
      );
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => FieldsCheckScreen(cargoId: widget.cargoId),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cam = _camera;
    final ready = cam != null && cam.value.isInitialized;

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          if (ready)
            FittedBox(
              fit: BoxFit.cover,
              child: SizedBox(
                width: cam.value.previewSize!.height,
                height: cam.value.previewSize!.width,
                child: CameraPreview(cam),
              ),
            )
          else
            ColoredBox(
              color: Colors.black,
              child: Center(
                child: _cameraError == null
                    ? const CircularProgressIndicator(color: Colors.white)
                    : Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 28),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _cameraError!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 15,
                                height: 1.35,
                              ),
                            ),
                            if (_needSettings) ...[
                              const SizedBox(height: 16),
                              FilledButton(
                                onPressed: openAppSettings,
                                child: const Text('Открыть настройки'),
                              ),
                            ],
                          ],
                        ),
                      ),
              ),
            ),
          SafeArea(
            child: Align(
              alignment: Alignment.topLeft,
              child: IconButton(
                onPressed: () => Navigator.of(context).maybePop(),
                icon: const Icon(Icons.close_rounded, color: Colors.white),
                style: IconButton.styleFrom(
                  backgroundColor: Colors.black45,
                ),
              ),
            ),
          ),
          if (_busy)
            ColoredBox(
              color: Colors.black54,
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const CircularProgressIndicator(color: Colors.white),
                    const SizedBox(height: 14),
                    Text(
                      'Отправляем на сервер…',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (!_busy)
            SafeArea(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Наведите на счёт и сделайте снимок',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.9),
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          _RoundAction(
                            icon: Icons.photo_library_outlined,
                            label: 'Галерея',
                            onTap: _fromGallery,
                          ),
                          const Spacer(),
                          GestureDetector(
                            onTap: ready && !_taking ? _shoot : null,
                            child: Container(
                              width: 76,
                              height: 76,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: Colors.white,
                                  width: 4,
                                ),
                              ),
                              padding: const EdgeInsets.all(5),
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: ready
                                      ? AppColors.primary
                                      : Colors.white24,
                                ),
                                child: _taking
                                    ? const Padding(
                                        padding: EdgeInsets.all(18),
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: Colors.white,
                                        ),
                                      )
                                    : null,
                              ),
                            ),
                          ),
                          const Spacer(),
                          const SizedBox(width: 76),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _RoundAction extends StatelessWidget {
  const _RoundAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return SizedBox(
      width: 76,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            onPressed: onTap,
            icon: Icon(icon, color: enabled ? Colors.white : Colors.white38),
            style: IconButton.styleFrom(
              backgroundColor: Colors.black45,
              fixedSize: const Size(52, 52),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: enabled ? Colors.white70 : Colors.white30,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../models/auth_user.dart';
import '../state/app_controller.dart';
import '../state/auth_controller.dart';
import '../state/notification_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import 'home_shell.dart';
import 'notifications_onboarding_screen.dart';

/// Вход / регистрация на одном экране — меняются только поля.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _register = false;
  bool _busy = false;
  bool _obscurePassword = true;
  String? _error;

  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  AuthRole _role = AuthRole.logist;

  @override
  void initState() {
    super.initState();
    _name.addListener(_clearError);
    _email.addListener(_clearError);
    _password.addListener(_clearError);
  }

  void _clearError() {
    if (_error == null || !mounted) return;
    setState(() => _error = null);
  }

  void _switchMode() {
    _dismissKeyboard();
    setState(() {
      _register = !_register;
      _error = null;
      _obscurePassword = true;
    });
  }

  @override
  void dispose() {
    _name.removeListener(_clearError);
    _email.removeListener(_clearError);
    _password.removeListener(_clearError);
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  String _mapError(Object err) {
    if (err is! ApiException) return 'Не удалось выполнить запрос';
    return switch (err.code) {
      'email_taken' => 'Эта почта уже зарегистрирована',
      'invalid_credentials' => 'Неверная почта или пароль',
      'weak_password' => 'Пароль должен быть не короче 6 символов',
      'invalid_email' => 'Проверьте формат почты',
      'validation_error' || 'invalid_name' =>
        err.message.isNotEmpty ? err.message : 'Проверьте заполненные поля',
      _ => err.message.isNotEmpty ? err.message : 'Ошибка авторизации',
    };
  }

  Future<void> _submit() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = AuthScope.of(context);
    try {
      if (_register) {
        await auth.register(
          name: _name.text.trim(),
          email: _email.text.trim(),
          password: _password.text,
          role: _role,
        );
      } else {
        await auth.login(
          email: _email.text.trim(),
          password: _password.text,
        );
      }
      if (!mounted) return;
      await AppScope.of(context).bootstrap();
      if (!mounted) return;
      final next = NotificationScope.of(context).promptSeen
          ? const HomeShell()
          : const NotificationsOnboardingScreen();
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          transitionDuration: const Duration(milliseconds: 280),
          pageBuilder: (context, animation, secondaryAnimation) => next,
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            return FadeTransition(opacity: animation, child: child);
          },
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = _mapError(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _dismissKeyboard() {
    FocusManager.instance.primaryFocus?.unfocus();
  }

  @override
  Widget build(BuildContext context) {
    final keyboardOpen = MediaQuery.viewInsetsOf(context).bottom > 0;

    return Scaffold(
      backgroundColor: AppColors.background,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return GestureDetector(
              onTap: _dismissKeyboard,
              behavior: HitTestBehavior.deferToChild,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: EdgeInsets.fromLTRB(
                  24,
                  keyboardOpen ? 12 : 28,
                  24,
                  keyboardOpen ? 12 : 28,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    minHeight: constraints.maxHeight -
                        (keyboardOpen ? 24 : 56),
                  ),
                  child: GestureDetector(
                    onTap: _dismissKeyboard,
                    behavior: HitTestBehavior.translucent,
                    // Без клавиатуры — по центру; с клавиатурой — у нижнего края
                    // (над клавой), чтобы форма не улетала вверх.
                    child: Align(
                      alignment: keyboardOpen
                          ? Alignment.bottomCenter
                          : Alignment.center,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 400),
                        child: Stack(
                          clipBehavior: Clip.none,
                          alignment: Alignment.topCenter,
                          children: [
                            Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                if (_register) ...[
                                  _Field(
                                    label: 'ФИО',
                                    child: TextField(
                                      controller: _name,
                                      textInputAction: TextInputAction.next,
                                      textCapitalization:
                                          TextCapitalization.words,
                                      style: TextStyle(
                                        color: AppColors.text,
                                        fontSize: 15,
                                        height: 1.25,
                                      ),
                                      decoration: const InputDecoration(
                                        hintText: 'Иванов Иван Иванович',
                                      ),
                                    ),
                                  ),
                                  const SizedBox(height: 14),
                                  Text(
                                    'Роль',
                                    style: TextStyle(
                                      color: AppColors.muted,
                                      fontSize: 12,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  const SizedBox(height: 8),
                                  _RoleTabs(
                                    role: _role,
                                    onChanged: (r) =>
                                        setState(() => _role = r),
                                  ),
                                  const SizedBox(height: 14),
                                ],
                                _Field(
                                  label: 'Эл. почта',
                                  child: TextField(
                                    controller: _email,
                                    keyboardType: TextInputType.emailAddress,
                                    autocorrect: false,
                                    textInputAction: TextInputAction.next,
                                    style: TextStyle(
                                      color: AppColors.text,
                                      fontSize: 15,
                                      height: 1.25,
                                    ),
                                    decoration: const InputDecoration(
                                      hintText: 'name@company.ru',
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 14),
                                _Field(
                                  label: 'Пароль',
                                  child: TextField(
                                    controller: _password,
                                    obscureText: _obscurePassword,
                                    textInputAction: TextInputAction.done,
                                    onSubmitted: (_) => _submit(),
                                    style: TextStyle(
                                      color: AppColors.text,
                                      fontSize: 15,
                                      height: 1.25,
                                    ),
                                    decoration: InputDecoration(
                                      hintText: _register
                                          ? 'Не меньше 6 символов'
                                          : '••••••••',
                                      suffixIcon: IconButton(
                                        tooltip: _obscurePassword
                                            ? 'Показать пароль'
                                            : 'Скрыть пароль',
                                        padding: EdgeInsets.zero,
                                        visualDensity: VisualDensity.compact,
                                        constraints: const BoxConstraints(
                                          minWidth: 44,
                                          minHeight: 44,
                                        ),
                                        onPressed: () {
                                          setState(
                                            () => _obscurePassword =
                                                !_obscurePassword,
                                          );
                                        },
                                        icon: Icon(
                                          _obscurePassword
                                              ? Icons.visibility_outlined
                                              : Icons.visibility_off_outlined,
                                          color: AppColors.muted,
                                          size: 22,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                if (_error != null) ...[
                                  const SizedBox(height: 14),
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 12,
                                      vertical: 10,
                                    ),
                                    decoration: BoxDecoration(
                                      color: AppColors.dangerBg,
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.radiusSm,
                                      ),
                                      border: Border.all(
                                        color: AppColors.danger.withValues(
                                          alpha: 0.35,
                                        ),
                                      ),
                                    ),
                                    child: Text(
                                      _error!,
                                      style: TextStyle(
                                        color: AppColors.danger,
                                        fontSize: 13,
                                        fontWeight: FontWeight.w700,
                                      ),
                                    ),
                                  ),
                                ],
                                const SizedBox(height: 18),
                                FilledButton(
                                  onPressed: _busy ? null : _submit,
                                  child: _busy
                                      ? const SizedBox(
                                          width: 22,
                                          height: 22,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : Text(
                                          _register
                                              ? 'Зарегистрироваться'
                                              : 'Войти',
                                        ),
                                ),
                                const SizedBox(height: 18),
                                Wrap(
                                  alignment: WrapAlignment.center,
                                  crossAxisAlignment: WrapCrossAlignment.center,
                                  children: [
                                    Text(
                                      _register
                                          ? 'Уже есть аккаунт? '
                                          : 'Нет аккаунта? ',
                                      style: TextStyle(
                                        color: AppColors.textSecondary,
                                        fontSize: 14,
                                      ),
                                    ),
                                    TextButton(
                                      onPressed: _switchMode,
                                      style: TextButton.styleFrom(
                                        padding: EdgeInsets.zero,
                                        minimumSize: Size.zero,
                                        tapTargetSize:
                                            MaterialTapTargetSize.shrinkWrap,
                                        visualDensity: VisualDensity.compact,
                                      ),
                                      child: Text(
                                        _register
                                            ? 'Войти'
                                            : 'Зарегистрироваться',
                                        style: TextStyle(
                                          color: AppColors.primary,
                                          fontSize: 14,
                                          fontWeight: FontWeight.w700,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                            Positioned(
                              left: 0,
                              right: 0,
                              top: -56,
                              child: Text(
                                _register ? 'Регистрация' : 'Вход',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: AppColors.text,
                                  fontSize: 28,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.3,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _RoleTabs extends StatelessWidget {
  const _RoleTabs({required this.role, required this.onChanged});

  final AuthRole role;
  final ValueChanged<AuthRole> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 42,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppColors.field,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          for (final r in AuthRole.values)
            Expanded(
              child: Material(
                color: role == r ? AppColors.primary : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                child: InkWell(
                  onTap: () => onChanged(r),
                  borderRadius: BorderRadius.circular(8),
                  child: Center(
                    child: Text(
                      r.label,
                      style: TextStyle(
                        color: role == r ? Colors.white : AppColors.muted,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: AppColors.muted,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        child,
      ],
    );
  }
}

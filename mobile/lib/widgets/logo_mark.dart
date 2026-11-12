import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../theme/app_colors.dart';

class LogoMark extends StatelessWidget {
  const LogoMark({super.key, this.size = 32});

  final double size;

  static const assetPath = 'assets/brand/caspian-dispatcher-app.svg';

  @override
  Widget build(BuildContext context) {
    return SvgPicture.asset(
      assetPath,
      width: size,
      height: size,
      semanticsLabel: 'Диспетчер',
    );
  }
}

class BrandHeader extends StatelessWidget {
  const BrandHeader({super.key, required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(18, 6, 18, 4),
      child: Row(
        children: [
          const LogoMark(size: 32),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              title,
              style: TextStyle(
                color: AppColors.text,
                fontSize: 20,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.3,
              ),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

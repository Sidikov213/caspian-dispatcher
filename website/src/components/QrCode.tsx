"use client";

import QRCode from "qrcode";
import { useMemo } from "react";

/** QR пропуска: внутри подписанный JWT (CLAUDE.md, раздел 3). */
export function QrCode({ value, size }: { value: string; size: number }) {
  const path = useMemo(() => {
    const qr = QRCode.create(value, { errorCorrectionLevel: "L" });
    const n = qr.modules.size;
    let d = "";
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        if (qr.modules.get(x, y)) d += `M${x} ${y}h1v1h-1z`;
      }
    }
    return { d, n };
  }, [value]);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${path.n} ${path.n}`} shapeRendering="crispEdges" aria-label="QR-код пропуска">
      <path d={path.d} fill="#12304A" />
    </svg>
  );
}

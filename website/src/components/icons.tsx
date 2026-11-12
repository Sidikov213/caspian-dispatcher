import type { SVGProps } from "react";
import type { CargoIcon } from "@/lib/derive";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, strokeWidth = 1.65, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

// Транспорт — docs/design/transport-*.svg
export const RailIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="6" y="3" width="12" height="14" rx="3" />
    <path d="M6 10h12M8 21l2-4m6 4-2-4M9 14h.01M15 14h.01" />
  </Icon>
);

export const SeaIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m3 13 9-3 9 3-3 5H6l-3-5Zm4-2V6h10v5m-5-1V3M3 21c2 0 3-1 4.5-1s3 1 4.5 1 3-1 4.5-1 2.5 1 4.5 1" />
  </Icon>
);

export const RoadIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h12v11H3V6Zm12 4h4l3 4v3h-7" />
    <circle cx="7" cy="18" r="2" />
    <circle cx="18" cy="18" r="2" />
  </Icon>
);

export const BoxIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z" />
    <path d="M12 22V12M3.3 7l7.7 4.73a2 2 0 0 0 2 0L20.7 7M7.5 4.27l9 5.15" />
  </Icon>
);

export function TransportIcon({ kind, ...p }: IconProps & { kind: CargoIcon }) {
  switch (kind) {
    case "rail":
      return <RailIcon {...p} />;
    case "ship":
      return <SeaIcon {...p} />;
    case "truck":
      return <RoadIcon {...p} />;
    default:
      return <BoxIcon {...p} />;
  }
}

export const ClockIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
);

export const RouteIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="6" cy="19" r="2.5" />
    <circle cx="18" cy="5" r="2.5" />
    <path d="M8.5 19H17a3.5 3.5 0 0 0 0-7H7a3.5 3.5 0 0 1 0-7h8.5" />
  </Icon>
);

export const LeafIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
  </Icon>
);

export const WavesIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2 9c.6.5 1.2 1 2.5 1C7 10 7 8 9.5 8c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
    <path d="M2 15c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
  </Icon>
);

export const IceIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 2v20M4.2 6.5l15.6 9M4.2 17.5l15.6-9" />
    <path d="m9.5 3.8 2.5 2 2.5-2M9.5 20.2l2.5-2 2.5 2M3.6 9.6l3.1-.5-1-3M20.4 14.4l-3.1.5 1 3M3.6 14.4l3.1.5-1 3M20.4 9.6l-3.1-.5 1-3" />
  </Icon>
);

/** Значок угрозы по Alert.hazard / Scenario.hazard. */
export function HazardIcon({ hazard, ...p }: IconProps & { hazard?: string | null }) {
  if (hazard === "ice") return <IceIcon {...p} />;
  if (hazard === "congestion" || hazard === "customs") return <TriangleAlertIcon {...p} />;
  return <StormIcon {...p} />;
}

export const StormIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 16.33A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.97" />
    <path d="m13 12-3 5h4l-3 5" />
  </Icon>
);

export const ChevronDownIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m6 9 6 6 6-6" />
  </Icon>
);

export const FilterIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M7 12h10M10 17h4" />
  </Icon>
);

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
);

export const MapIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14.1 5.55a2 2 0 0 0 1.8 0l3.65-1.83A1 1 0 0 1 21 4.62v12.76a1 1 0 0 1-.55.9l-4.55 2.27a2 2 0 0 1-1.8 0l-4.2-2.1a2 2 0 0 0-1.8 0l-3.65 1.83A1 1 0 0 1 3 19.38V6.62a1 1 0 0 1 .55-.9L8.1 3.45a2 2 0 0 1 1.8 0z" />
    <path d="M15 5.76v15M9 3.24v15" />
  </Icon>
);

export const FileIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8" />
  </Icon>
);

export const LayersIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z" />
    <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65" />
  </Icon>
);

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14M12 5v14" />
  </Icon>
);

export const MinusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14" />
  </Icon>
);

export const LocateIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2 12h3M19 12h3M12 2v3M12 19v3" />
    <circle cx="12" cy="12" r="7" />
    <circle cx="12" cy="12" r="2.5" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Icon>
);

export const ShieldCheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <path d="m9 12 2 2 4-4" />
  </Icon>
);

export const ShieldAlertIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <path d="M12 8v4M12 16h.01" />
  </Icon>
);

export const TriangleAlertIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4M12 17h.01" />
  </Icon>
);

export const ResetIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Icon>
);

/** Знак без текста — для иконок и компактных мест. */
export function LogoMark({ size = 50 }: { size?: number }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/logo-mark.png" alt="" width={size} height={size} className="block object-contain" draggable={false} />
  );
}

/** Знак с названием — шапка сайта. */
export function LogoWordmark({ height = 44 }: { height?: number }) {
  // Знак — картинкой, название — текстом: читается в обеих темах (у PNG-логотипа тёмные буквы).
  const font = Math.round(height * 0.36);
  return (
    <span className="flex items-center gap-[10px]" style={{ height }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/logo-mark.png" alt="" width={height} height={height} className="block object-contain" draggable={false} />
      <span className="font-bold text-text" style={{ fontSize: font, lineHeight: 1.1 }}>
        Каспийский
        <br />
        диспетчер
      </span>
    </span>
  );
}

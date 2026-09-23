// Minimal inline SVG icon set (no icon library) — 16x16, currentColor, aria-hidden.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

function Icon(props: P & { children: React.ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {props.children}
    </svg>
  );
}

export const UploadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 11V3M5 6l3-3 3 3" />
    <path d="M2 11v1.5A1.5 1.5 0 0 0 3.5 14h9a1.5 1.5 0 0 0 1.5-1.5V11" />
  </Icon>
);

export const PlayIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4.5 3l8 5-8 5V3z" fill="currentColor" stroke="none" />
  </Icon>
);

export const DownloadIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 3v8M5 8l3 3 3-3" />
    <path d="M2 11v1.5A1.5 1.5 0 0 0 3.5 14h9a1.5 1.5 0 0 0 1.5-1.5V11" />
  </Icon>
);

export const RefreshIcon = (p: P) => (
  <Icon {...p}>
    <path d="M13 8a5 5 0 1 1-1.5-3.5M13 2v3h-3" />
  </Icon>
);

export const PlusIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 3v10M3 8h10" />
  </Icon>
);

export const XIcon = (p: P) => (
  <Icon {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Icon>
);

export const CheckIcon = (p: P) => (
  <Icon {...p}>
    <path d="M3 8.5l3.5 3.5L13 5" />
  </Icon>
);

export const AlertIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 2L1.5 13.5h13L8 2z" />
    <path d="M8 6.5v3.5M8 12v.5" />
  </Icon>
);

export const ClockIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 5v3l2.5 1.5" />
  </Icon>
);

export const ChartIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2 14h12" />
    <path d="M4 14V9M8 14V4M12 14V7" />
  </Icon>
);

export const FilmIcon = (p: P) => (
  <Icon {...p}>
    <rect x="2" y="3" width="12" height="10" rx="1" />
    <path d="M5 3v10M11 3v10M2 8h12" />
  </Icon>
);

export const ScissorsIcon = (p: P) => (
  <Icon {...p}>
    <circle cx="4" cy="4" r="1.8" />
    <circle cx="4" cy="12" r="1.8" />
    <path d="M5.5 5.5L13 12M5.5 10.5L13 4" />
  </Icon>
);

export const SendIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2 8l12-5-4 10-2.5-3.5L2 8z" />
  </Icon>
);

export const MenuIcon = (p: P) => (
  <Icon {...p}>
    <path d="M2 4h12M2 8h12M2 12h12" />
  </Icon>
);

export const SparkIcon = (p: P) => (
  <Icon {...p}>
    <path d="M8 2l1.2 3.3L12.5 6.5 9.2 7.7 8 11l-1.2-3.3L3.5 6.5l3.3-1.2L8 2z" />
    <path d="M12.5 11l.5 1.4 1.4.5-1.4.5-.5 1.4-.5-1.4-1.4-.5 1.4-.5.5-1.4z" />
  </Icon>
);

export const DatabaseIcon = (p: P) => (
  <Icon {...p}>
    <ellipse cx="8" cy="4" rx="5.5" ry="2" />
    <path d="M2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4" />
    <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" />
  </Icon>
);

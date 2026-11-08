import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 24, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const HomeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 11l8-7 8 7" />
    <path d="M6 9.5V20h12V9.5" />
    <path d="M10 20v-5.5h4V20" />
  </Icon>
);

export const BagIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 8.5h14l1 12H4z" />
    <path d="M8.5 11V7a3.5 3.5 0 017 0v4" />
  </Icon>
);

export const GiftIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="8.5" width="17" height="4" rx="0.8" />
    <path d="M5.5 12.5V21h13v-8.5M12 8.5V21" />
    <path d="M12 8.5C10 8.5 7.5 7.6 7.5 5.6 7.5 4.4 8.4 3.5 9.5 3.5c1.8 0 2.5 2.7 2.5 5zM12 8.5c2 0 4.5-.9 4.5-2.9 0-1.2-.9-2.1-2-2.1-1.8 0-2.5 2.7-2.5 5z" />
  </Icon>
);

export const GridIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4" y="4" width="6.5" height="6.5" rx="0.8" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="0.8" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="0.8" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="0.8" />
  </Icon>
);

export const PersonIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="10" r="3" />
    <path d="M6.5 18.500c1-2.7 3-4 5.5-4s4.5 1.3 5.5 4" />
  </Icon>
);

export const BellIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 17V11a6 6 0 0112 0v6l1.5 1.500h-15z" />
    <path d="M10 21h4" />
  </Icon>
);

export const ChatIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 5h16v12H10l-4 3.500V17H4z" />
  </Icon>
);

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M16 16l4.5 4.5" />
  </Icon>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 5l7 7-7 7" />
  </Icon>
);

export const BackIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15 4l-8 8 8 8" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const WarningIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.500l9.5 16.500h-19z" />
    <path d="M12 10v4.500M12 17.200v.1" />
  </Icon>
);

export const CartIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 4h2.500l2.2 11.500h10.800L20.5 7H6.2" />
    <circle cx="9" cy="19.5" r="1.2" />
    <circle cx="17" cy="19.5" r="1.2" />
  </Icon>
);

export const GearIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M10.5 3h3l.5 2.4 1.8.8 2.1-1.3 2.1 2.1-1.3 2.1.8 1.8 2.4.5v3l-2.4.5-.8 1.8 1.3 2.1-2.1 2.1-2.1-1.3-1.8.8-.5 2.400h-3l-.5-2.4-1.8-.8-2.1 1.3-2.1-2.1 1.3-2.1-.8-1.800L2.2 13.500v-3l2.4-.5.8-1.8-1.3-2.1 2.1-2.1 2.1 1.3 1.8-.8z" />
  </Icon>
);

export const BookmarkIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 4h10v16.500l-5-3.5-5 3.500z" />
  </Icon>
);

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const DeviceIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="7" y="3" width="10" height="18" rx="2" />
    <path d="M10.5 18h3" />
  </Icon>
);

export const AddPersonIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="10" cy="8.5" r="3.5" />
    <path d="M3.5 20c.8-3.5 3.2-5.5 6.5-5.5 1.3 0 2.5.3 3.5.9" />
    <path d="M18 14v6M15 17h6" />
  </Icon>
);

export const ClipboardIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="5" y="4.5" width="14" height="16.5" rx="1.5" />
    <path d="M9.5 3h5v3.500h-5zM8.5 11h7M8.5 14.500h7M8.5 18h4" />
  </Icon>
);

export const PeopleIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8.5" r="3.5" />
    <path d="M3 20c.8-3.5 3-5.5 6-5.500s5.2 2 6 5.5" />
    <path d="M15.5 5.500a3.5 3.5 0 010 6.500M17.5 14.800c1.8.8 3 2.5 3.5 5.2" />
  </Icon>
);

export const PhoneHandsetIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6.5 3.500l3 .5 1.2 4-2 1.500c1 2.5 3.3 4.8 5.8 5.800l1.5-2 4 1.2.5 3c.1 1.3-1 2.5-2.3 2.500C10 20 4 14 4 5.800c0-1.3 1.2-2.4 2.5-2.300z" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12.500l4.5 4.500L19 7.5" />
  </Icon>
);

/** Neutral Safe Signal placeholder mark: a shield with a small pulse. */
export function SafeSignalMark({ size = 36, tone = "dark" }: { size?: number; tone?: "dark" | "light" }) {
  const background = tone === "dark" ? "#222222" : "#ffffff";
  const foreground = tone === "dark" ? "#ffffff" : "#222222";
  return (
    <svg width={size} height={size} viewBox="0 0 36 36" className="shrink-0" aria-hidden="true">
      <rect width="36" height="36" rx="9" fill={background} />
      <path
        d="M18 7l9 3.300v7.200c0 5.8-3.8 9.4-9 11.2-5.2-1.8-9-5.4-9-11.200v-7.200z"
        fill="none"
        stroke={foreground}
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M12.5 18.500h3.400l1.7-3.8 2.4 6.6 1.5-2.800h2"
        fill="none"
        stroke={foreground}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

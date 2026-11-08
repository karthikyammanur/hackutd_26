/** Hand-drawn perk and device art. No photos or downloaded assets. */
export function CupArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d="M34 42h52l-6 62a6 6 0 01-6 5H46a6 6 0 01-6-5z" fill="#fff" />
      <path d="M38 62h44l-2.500 26h-39z" fill="#e20074" />
      <rect x="28" y="30" width="64" height="13" rx="4" fill="#222" />
      <path d="M42 30l4-12h28l4 12z" fill="#fff" opacity="0.9" />
    </svg>
  );
}

export function SliceArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d="M22 34c24-14 52-14 76 0L60 108z" fill="#ffc34d" />
      <path d="M22 34c24-14 52-14 76 0l-6 11c-20-11-44-11-64 0z" fill="#b5651d" />
      <circle cx="50" cy="56" r="8" fill="#c62828" />
      <circle cx="72" cy="58" r="8" fill="#c62828" />
      <circle cx="60" cy="80" r="7" fill="#c62828" />
    </svg>
  );
}

export function SuitcaseArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <rect x="28" y="40" width="64" height="62" rx="8" fill="#fff" />
      <path d="M46 40V26a4 4 0 014-4h20a4 4 0 014 4v14" fill="none" stroke="#fff" strokeWidth="6" />
      <path d="M44 40v62M76 40v62" stroke="#e20074" strokeWidth="6" />
    </svg>
  );
}

export function TicketArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path
        d="M18 38h84v14a9 9 0 000 18v14H18V70a9 9 0 000-18z"
        fill="#fff"
        transform="rotate(-10 60 60)"
      />
      <path d="M78 34l6 54" stroke="#e20074" strokeWidth="3" strokeDasharray="5 5" />
    </svg>
  );
}

export function PhoneArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 80 110" className={className} aria-hidden="true">
      <rect x="16" y="4" width="50" height="102" rx="9" fill="#6b7ec9" />
      <rect x="21" y="9" width="40" height="92" rx="5" fill="#27365f" />
      <path d="M21 58c14-20 28-20 40-30v68a5 5 0 01-5 5H26a5 5 0 01-5-5z" fill="#8fa3e8" />
      <rect x="35" y="13" width="12" height="3" rx="1.500" fill="#0f1730" />
    </svg>
  );
}

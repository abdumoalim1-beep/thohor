// Minimal hand-rolled line-icon set (no external icon library dependency).
// Consistent 1.75 stroke, 20x20 viewBox, currentColor — matches the calm,
// premium tone of the rest of the design system.
type IconProps = { className?: string };

const base = {
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function IconOverview({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="3" width="6" height="7" rx="1.5" />
      <rect x="11" y="3" width="6" height="4" rx="1.5" />
      <rect x="11" y="9" width="6" height="8" rx="1.5" />
      <rect x="3" y="12" width="6" height="5" rx="1.5" />
    </svg>
  );
}

export function IconEye({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2 10s2.8-5.5 8-5.5S18 10 18 10s-2.8 5.5-8 5.5S2 10 2 10Z" />
      <circle cx="10" cy="10" r="2.25" />
    </svg>
  );
}

export function IconMarket({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M2.5 17.5h15" />
      <path d="M4 17.5V10l3-5.5h6l3 5.5v7.5" />
      <path d="M4 10h12" />
      <path d="M8 17.5v-4h4v4" />
    </svg>
  );
}

export function IconCompetitors({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="7" cy="6.5" r="2.5" />
      <circle cx="14.5" cy="7.5" r="2" />
      <path d="M2.5 17v-1.2c0-2.1 2-3.8 4.5-3.8s4.5 1.7 4.5 3.8V17" />
      <path d="M12.5 12.3c1.9.3 3.4 1.7 3.4 3.5V17" />
    </svg>
  );
}

export function IconOpportunity({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M10 2.5c-2.9 0-5 2.1-5 4.9 0 1.9 1 3 1.8 3.8.6.6.9 1 .9 1.6v.7h4.6v-.7c0-.6.3-1 .9-1.6.8-.8 1.8-1.9 1.8-3.8 0-2.8-2.1-4.9-5-4.9Z" />
      <path d="M8.2 17.2h3.6" />
      <path d="M8.7 15h2.6" />
    </svg>
  );
}

export function IconRecommendations({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 3.5h9.5L16 6v10.5H4Z" />
      <path d="M6.5 8h7M6.5 10.5h7M6.5 13h4.5" />
    </svg>
  );
}

export function IconReports({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3.5" y="3" width="13" height="14" rx="1.5" />
      <path d="M7 8h6M7 11h6M7 14h3.5" />
    </svg>
  );
}

export function IconSettings({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="10" cy="10" r="2.4" />
      <path d="M10 3v1.6M10 15.4V17M17 10h-1.6M4.6 10H3M15.1 4.9l-1.1 1.1M6 13l-1.1 1.1M15.1 15.1 14 14M6 7 4.9 5.9" />
    </svg>
  );
}

export function IconBell({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M5 8.5a5 5 0 0 1 10 0c0 3.2 1 4.3 1.5 5H3.5c.5-.7 1.5-1.8 1.5-5Z" />
      <path d="M8.2 16a1.9 1.9 0 0 0 3.6 0" />
    </svg>
  );
}

export function IconChevronLeft({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 4.5 7 10l5 5.5" />
    </svg>
  );
}

export function IconChevronDown({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4.5 7.5 10 13l5.5-5.5" />
    </svg>
  );
}

export function IconExternal({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M8.5 4.5H15.5V11.5" />
      <path d="M15.5 4.5 9 11" />
      <path d="M13 10.5V15a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h4.5" />
    </svg>
  );
}

export function IconTrendUp({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 13.5 8 8l3.5 3.5L17 5.5" />
      <path d="M12.5 5.5H17V10" />
    </svg>
  );
}

export function IconTrendDown({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 6.5 8 12l3.5-3.5L17 14.5" />
      <path d="M12.5 14.5H17V10" />
    </svg>
  );
}

export function IconAlertTriangle({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M10 3.2 2.5 16h15L10 3.2Z" />
      <path d="M10 8.3v3.4" />
      <circle cx="10" cy="14" r="0.15" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconCheckCircle({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="10" cy="10" r="7" />
      <path d="M7 10.2 9 12.2 13.2 7.8" />
    </svg>
  );
}

export function IconInfoCircle({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 9.2v4" />
      <circle cx="10" cy="6.8" r="0.15" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconSearch({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="8.5" cy="8.5" r="5.2" />
      <path d="M16 16l-3.8-3.8" />
    </svg>
  );
}

export function IconStore({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 8.5 4 3.5h12l1 5" />
      <path d="M3.5 8.5h13V16h-13Z" />
      <path d="M8 16v-4h4v4" />
    </svg>
  );
}

export function IconSpark({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M10 2.5 11.4 8 17 9.5 11.4 11 10 16.5 8.6 11 3 9.5 8.6 8Z" />
    </svg>
  );
}

export function IconArrowLeft({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M16 10H4M4 10l4.5-4.5M4 10l4.5 4.5" />
    </svg>
  );
}

export function IconPrint({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M6 7.5V3h8v4.5" />
      <rect x="3.5" y="7.5" width="13" height="6" rx="1" />
      <path d="M6 12.5h8V17H6Z" />
    </svg>
  );
}

export function IconLoader({ className }: IconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className}>
      <circle
        cx="10"
        cy="10"
        r="7.5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeDasharray="30 100"
      />
    </svg>
  );
}

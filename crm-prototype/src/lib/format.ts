export function money(n: number, compact = false): string {
  if (compact) {
    if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
    if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1_000)}K`;
    return `$${n}`;
  }
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function num(n: number): string {
  return n.toLocaleString("en-US");
}

export function pct(n: number, digits = 0): string {
  return `${n.toFixed(digits)}%`;
}

export function rate(n: number): string {
  return `${n.toFixed(2)}%`;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = new Date("2026-08-22T12:00:00Z").getTime();
  const diff = now - then;
  const day = 86_400_000;
  if (diff < 0) {
    const d = Math.round(-diff / day);
    if (d === 0) return "today";
    if (d === 1) return "tomorrow";
    return `in ${d}d`;
  }
  const d = Math.floor(diff / day);
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  if (d < 30) return `${d}d ago`;
  const m = Math.floor(d / 30);
  return `${m}mo ago`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function dayMonth(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

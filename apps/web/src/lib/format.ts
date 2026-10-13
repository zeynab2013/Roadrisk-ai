export function formatProbability(value: number): string {
  const decimal = new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(value);
  const percent = new Intl.NumberFormat("en-GB", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
  return `${decimal} (${percent})`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-GB").format(value);
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const formatted = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
  return `${formatted} UTC`;
}

export function classLabel(label: string): string {
  if (label === "fatal_or_serious") {
    return "Fatal or serious";
  }
  if (label === "slight") {
    return "Slight";
  }
  return label;
}

export function shortVersion(value: string): string {
  return value.length > 16 ? `${value.slice(0, 12)}…` : value;
}

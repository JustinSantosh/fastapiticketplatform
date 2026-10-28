// Display helpers + a UI copy of the transition map.
// The copy only decides which buttons to show; the backend (rules.py) is the
// authority and rejects anything else regardless of what the UI sends.

export const STATUS_LABEL = { open: "Open", in_progress: "In progress", resolved: "Resolved" };
export const PRIORITY_LABEL = { low: "Low", medium: "Medium", high: "High" };

export const NEXT_STATUSES = {
  open: ["in_progress"],
  in_progress: ["resolved"],
  resolved: ["in_progress"],
};

export function actionLabel(from, to) {
  if (from === "open" && to === "in_progress") return "Start progress";
  if (to === "resolved") return "Resolve";
  if (from === "resolved") return "Reopen";
  return STATUS_LABEL[to];
}

// Mirrors the Pydantic limits in backend/app/schemas.py
export const LIMITS = {
  title: { min: 3, max: 200 },
  description: { min: 1, max: 5000 },
  comment: { min: 1, max: 2000 },
  reason: { min: 1, max: 1000 },
};

const dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
export const formatDate = (iso) => dateFmt.format(new Date(iso));

export function timeAgo(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  const units = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(-Math.floor(seconds / size), unit);
    }
  }
  return "just now";
}

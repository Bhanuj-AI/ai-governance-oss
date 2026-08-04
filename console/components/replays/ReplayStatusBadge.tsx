import { Badge } from "@/components/ui/badge";
import type { ReplayStatus } from "@/types/replay";

const tones: Record<ReplayStatus, string> = {
  DRAFT: "border-slate-300 bg-slate-50 text-slate-700",
  READY: "border-sky-300 bg-sky-50 text-sky-800",
  QUEUED: "border-amber-300 bg-amber-50 text-amber-800",
  RUNNING: "border-amber-300 bg-amber-50 text-amber-800",
  EXECUTION_COMPLETED: "border-indigo-300 bg-indigo-50 text-indigo-800",
  EVALUATING: "border-amber-300 bg-amber-50 text-amber-800",
  COMPARING: "border-amber-300 bg-amber-50 text-amber-800",
  COMPLETED: "border-emerald-300 bg-emerald-50 text-emerald-800",
  FAILED: "border-red-300 bg-red-50 text-red-800",
  CANCELLED: "border-slate-300 bg-slate-100 text-slate-700",
  ARCHIVED: "border-slate-300 bg-slate-100 text-slate-600",
};

export function ReplayStatusBadge({ status }: { status: ReplayStatus }) {
  return <Badge variant="outline" className={tones[status]}>{status.replaceAll("_", " ")}</Badge>;
}

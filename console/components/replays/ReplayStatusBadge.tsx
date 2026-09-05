import { Badge } from "@/components/ui/badge";
import type { ReplayStatus } from "@/types/replay";

const tones: Record<ReplayStatus, string> = {
  DRAFT: "border-yellow-200 bg-[#ffd60a] text-[#1f2328]",
  READY: "border-sky-200 bg-sky-300 text-slate-950",
  QUEUED: "border-amber-200 bg-amber-300 text-slate-950",
  RUNNING: "border-amber-200 bg-amber-300 text-slate-950",
  EXECUTION_COMPLETED: "border-violet-200 bg-violet-300 text-slate-950",
  EVALUATING: "border-amber-200 bg-amber-300 text-slate-950",
  COMPARING: "border-amber-200 bg-amber-300 text-slate-950",
  COMPLETED: "border-transparent bg-[#32d74b] text-[#1f2328]",
  FAILED: "border-transparent bg-[#ff453a] text-[#1f2328]",
  CANCELLED: "border-transparent bg-[#ff9f0a] text-[#1f2328]",
  ARCHIVED: "border-slate-300 bg-slate-300 text-slate-950",
};

export function ReplayStatusBadge({ status }: { status: ReplayStatus }) {
  return <Badge variant="outline" className={tones[status]}>{status.replaceAll("_", " ")}</Badge>;
}

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils/cn";

export function ExperimentStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("border-transparent font-semibold", statusClassName(status))}
    >
      {status}
    </Badge>
  );
}

function statusClassName(status: string) {
  if (status === "COMPLETED") return "bg-[#32d74b] text-[#1f2328]";
  if (status === "FAILED") return "bg-[#ff453a] text-[#1f2328]";
  if (status === "RUNNING") return "bg-primary text-primary-foreground";
  if (status === "DRAFT" || status === "PENDING") return "bg-[#ffd60a] text-[#1f2328]";
  if (status === "ARCHIVED") return "bg-secondary text-secondary-foreground";
  return "bg-secondary text-secondary-foreground";
}

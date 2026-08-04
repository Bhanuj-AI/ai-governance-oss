import { Badge } from "@/components/ui/badge";

/** Uses the same high-contrast semantic palette as Jobs and MCP Audit. */
export function DecisionStatusBadge({ value }: { value: string }) {
  return (
    <Badge
      variant="outline"
      className={`max-w-[160px] truncate border-transparent font-semibold ${decisionStatusClassName(value)}`}
    >
      {value}
    </Badge>
  );
}

function decisionStatusClassName(value: string) {
  const normalized = value.toLowerCase();
  if (["approved", "approve", "active", "matched", "pass", "passed", "success", "succeeded", "completed"].includes(normalized)) {
    return "bg-[#32d74b] text-[#1f2328]";
  }
  if (["pending", "proposed", "review", "investigate", "recommend", "warning", "queued", "running"].includes(normalized)) {
    return "bg-[#ffd60a] text-[#1f2328]";
  }
  if (["rejected", "reject", "blocked", "block", "denied", "deny", "failed", "cancelled"].includes(normalized)) {
    return "bg-[#ff453a] text-[#1f2328]";
  }
  return "bg-secondary text-secondary-foreground";
}

import * as React from "react";
import { cn } from "@/lib/utils/cn";

export function JourneyPanel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("journey-panel rounded-lg border", className)} {...props} />;
}

export function JourneyLabel({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("journey-label font-mono text-xs font-semibold uppercase", className)} {...props} />;
}

export function JourneyStage({ tone = 0, className, children, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: number }) {
  return <span className={cn("journey-stage font-mono text-xs", `journey-stage-${tone % 4}`, className)} {...props}>{children}</span>;
}

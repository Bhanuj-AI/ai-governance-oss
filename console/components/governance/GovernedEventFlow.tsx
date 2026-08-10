import type { ReactNode } from "react";

export type GovernedFlowTone =
  | "info"
  | "progress"
  | "success"
  | "warning"
  | "danger"
  | "muted";

export type GovernedFlowStep = {
  id: string;
  label: string;
  detail: string;
  tone?: GovernedFlowTone;
};

const TONE_CLASSES: Record<GovernedFlowTone, { number: string; dot: string }> = {
  info: {
    number: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-200",
    dot: "bg-cyan-500",
  },
  progress: {
    number: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-200",
    dot: "bg-violet-500",
  },
  success: {
    number: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200",
    dot: "bg-emerald-500",
  },
  warning: {
    number: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-200",
    dot: "bg-amber-500",
  },
  danger: {
    number: "border-destructive/30 bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  muted: {
    number: "border-border bg-muted text-muted-foreground",
    dot: "bg-muted-foreground/50",
  },
};

const OUTCOME_CLASSES: Record<Exclude<GovernedFlowTone, "muted">, string> = {
  info: "border-cyan-500/35 bg-cyan-500/5",
  progress: "border-violet-500/35 bg-violet-500/5",
  success: "border-emerald-500/35 bg-emerald-500/5",
  warning: "border-amber-500/35 bg-amber-500/5",
  danger: "border-destructive/35 bg-destructive/5",
};

const OUTCOME_TEXT_CLASSES: Record<Exclude<GovernedFlowTone, "muted">, string> = {
  info: "text-cyan-700 dark:text-cyan-300",
  progress: "text-violet-700 dark:text-violet-300",
  success: "text-emerald-700 dark:text-emerald-300",
  warning: "text-amber-700 dark:text-amber-300",
  danger: "text-destructive",
};

/** A theme-aware, data-driven counterpart to the documentation event-flow template. */
export function GovernedEventFlow({
  stream,
  steps,
  outcomeLabel,
  outcome,
  outcomeDetail,
  outcomeTone,
  activeStep,
  activeAdornment,
  footer,
}: {
  stream: string;
  steps: GovernedFlowStep[];
  outcomeLabel: string;
  outcome: string;
  outcomeDetail: string;
  outcomeTone: Exclude<GovernedFlowTone, "muted">;
  activeStep?: number;
  activeAdornment?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section aria-label={`${stream} lifecycle`} className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/25 px-4 py-3 font-mono text-[0.65rem] uppercase tracking-[0.16em] text-muted-foreground sm:px-5">
        <span className="flex items-center gap-2">
          <span className={`size-1.5 rounded-full ${TONE_CLASSES[outcomeTone].dot}`} />
          AI Governance Control Plane / governed event stream
        </span>
        <span className="hidden text-emerald-700 dark:text-emerald-300 sm:block">
          ordered · durable · explainable
        </span>
      </div>

      <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(230px,0.85fr)] lg:items-center">
        <div className="min-w-0 rounded-lg border bg-muted/20 p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-4 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-primary">
            <span>{stream}</span>
            <span className="text-muted-foreground">event order</span>
          </div>
          <ol className="space-y-2">
            {steps.map((step, index) => {
              const tone = TONE_CLASSES[step.tone ?? "info"];
              return (
                <li key={step.id} className="relative flex items-start gap-3">
                  <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border font-mono text-[0.65rem] ${tone.number}`}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0 pb-1">
                    <div className="flex items-center gap-2">
                      <span className={`size-1.5 shrink-0 rounded-full ${tone.dot}`} />
                      <span className="font-mono text-xs font-medium text-foreground">{step.label}</span>
                      {index === activeStep ? activeAdornment : null}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{step.detail}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>

        <div className={`rounded-xl border p-5 ${OUTCOME_CLASSES[outcomeTone]}`}>
          <p className="font-mono text-[0.67rem] uppercase tracking-[0.16em] text-muted-foreground">
            {outcomeLabel}
          </p>
          <p className={`mt-3 font-mono text-2xl font-semibold tracking-tight ${OUTCOME_TEXT_CLASSES[outcomeTone]}`}>
            {outcome}
          </p>
          <div className="my-4 h-px bg-border" />
          <p className="font-mono text-xs leading-relaxed text-muted-foreground">{outcomeDetail}</p>
        </div>
      </div>
      {footer ? <div className="border-t bg-muted/15 px-4 py-3 sm:px-5">{footer}</div> : null}
    </section>
  );
}

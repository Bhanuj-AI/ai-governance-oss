import { Check, CircleAlert, Clock3, LoaderCircle, X } from "lucide-react";
import {
  GovernedEventFlow,
  type GovernedFlowStep,
  type GovernedFlowTone,
} from "@/components/governance/GovernedEventFlow";
import type { OntologySyncEvent, OntologySyncEventStatus } from "@/types/ontology-sync";

type LifecyclePresentation = {
  outcome: string;
  outcomeDetail: string;
  tone: Exclude<GovernedFlowTone, "muted">;
  activeStep: number;
};

/**
 * A live, parameterized version of the governed-event flow used in the
 * documentation site. It explains the current event without exposing its
 * technical payload unless an operator chooses to open it.
 */
export function SyncEventLifecycle({ event }: { event: OntologySyncEvent }) {
  const presentation = presentationFor(event);
  const steps = stepsFor(event, presentation);

  return (
    <GovernedEventFlow
      stream="Ontology / synchronization"
      steps={steps}
      outcomeLabel="Current outcome"
      outcome={presentation.outcome}
      outcomeDetail={presentation.outcomeDetail}
      outcomeTone={presentation.tone}
      activeStep={presentation.activeStep}
      activeAdornment={<StepState status={event.status} />}
    />
  );
}

function stepsFor(event: OntologySyncEvent, presentation: LifecyclePresentation): GovernedFlowStep[] {
  const base: GovernedFlowStep[] = [
    {
      id: "received",
      label: "receive durable event",
      detail: `${event.eventType} was recorded for ${event.entityType}.`,
      tone: "info",
    },
    {
      id: "expected-projection",
      label: "build expected projection",
      detail: "Domain records define the authoritative graph shape.",
      tone: "progress",
    },
    {
      id: "reconcile",
      label: "reconcile graph state",
      detail: "The synchronizer compares semantic state and repairs detected drift.",
      tone: "info",
    },
    {
      id: "outcome",
      label: "record outcome",
      detail: "The durable event retains its status, retry history, and reconciliation evidence.",
      tone: "success",
    },
  ];

  return base.map((step, index) => ({
    ...step,
    tone: index === presentation.activeStep ? presentation.tone : index > presentation.activeStep ? "muted" : step.tone,
  }));
}

function presentationFor(event: OntologySyncEvent): LifecyclePresentation {
  switch (event.status) {
    case "PENDING":
      return {
        activeStep: 0,
        outcome: "QUEUED",
        outcomeDetail: "Waiting for a synchronizer worker to pick up this durable event.",
        tone: "info",
      };
    case "PROCESSING":
      return {
        activeStep: 2,
        outcome: "SYNCHRONIZING",
        outcomeDetail: "The current graph is being compared with the authoritative projection.",
        tone: "progress",
      };
    case "COMPLETED":
      return {
        activeStep: 3,
        outcome: "IN SYNC",
        outcomeDetail: "The graph projection was reconciled and its durable event evidence was retained.",
        tone: "success",
      };
    case "FAILED":
      return {
        activeStep: 2,
        outcome: "RETRYING",
        outcomeDetail: event.nextRetryAt
          ? "A retry is scheduled after the current backoff period."
          : "This event can be requeued after the underlying issue is resolved.",
        tone: "warning",
      };
    case "DEAD_LETTER":
      return {
        activeStep: 2,
        outcome: "HELD FOR REVIEW",
        outcomeDetail: "Automatic retries are exhausted. Review the failure, then requeue this same durable event.",
        tone: "danger",
      };
    case "CANCELLED":
      return {
        activeStep: 3,
        outcome: "CANCELLED",
        outcomeDetail: "This event was retained for audit history but was not projected into the live graph.",
        tone: "warning",
      };
  }
}

function StepState({ status }: { status: OntologySyncEventStatus }) {
  if (status === "COMPLETED") {
    return <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-label="Completed" />;
  }
  if (status === "DEAD_LETTER") {
    return <CircleAlert className="h-3.5 w-3.5 text-destructive" aria-label="Needs review" />;
  }
  if (status === "FAILED" || status === "CANCELLED") {
    return <X className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" aria-label="Not completed" />;
  }
  if (status === "PROCESSING") {
    return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-violet-600 dark:text-violet-400" aria-label="Synchronizing" />;
  }
  return <Clock3 className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" aria-label="Queued" />;
}

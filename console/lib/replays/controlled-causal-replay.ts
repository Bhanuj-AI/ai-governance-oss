import type { Replay } from "@/types/replay";

/**
 * A controlled Replay is created exclusively by Causal Audit. The backend
 * persists this linkage in safe Replay metadata; Studio uses it only to select
 * the appropriate operational surface, never to authorize an action.
 */
export function controlledCausalAuditId(replay: Replay): string | null {
  const auditId = replay.metadata.causal_audit_id;
  return replay.metadata.controlled_replay === true
    && typeof auditId === "string"
    && auditId.trim()
    ? auditId
    : null;
}

export function isControlledCausalReplay(replay: Replay): boolean {
  return controlledCausalAuditId(replay) !== null;
}

import { McpAuditPage } from "@/components/audit/McpAuditPage";
import { StudioShell } from "@/components/layout/ConsoleShell";

export default function AuditRoute() {
  return (
    <StudioShell>
      <McpAuditPage />
    </StudioShell>
  );
}

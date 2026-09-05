import { CausalAuditDetailPage } from "@/components/agent-runtime/CausalAuditDetailPage";
import { StudioShell } from "@/components/layout/ConsoleShell";

export default async function CausalAuditDetailRoute({ params }: { params: Promise<{ auditId: string }> }) {
  const { auditId } = await params;
  return <StudioShell><CausalAuditDetailPage auditId={auditId} /></StudioShell>;
}

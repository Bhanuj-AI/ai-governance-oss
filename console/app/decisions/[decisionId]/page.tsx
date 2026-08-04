import { DecisionDetailPage } from "@/components/decisions/DecisionDetailPage";
import { StudioShell } from "@/components/layout/ConsoleShell";

export default async function DecisionPage({
  params,
}: {
  params: Promise<{ decisionId: string }>;
}) {
  const { decisionId } = await params;

  return (
    <StudioShell>
      <DecisionDetailPage decisionId={decodeURIComponent(decisionId)} />
    </StudioShell>
  );
}

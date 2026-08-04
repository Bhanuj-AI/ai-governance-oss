import { StudioShell } from "@/components/layout/ConsoleShell";
import { ReplayExecutionDetailPage } from "@/components/replays/ReplayExecutionDetailPage";

export default async function ReplayExecutionRoute({
  params,
}: {
  params: Promise<{ executionId: string }>;
}) {
  const { executionId } = await params;
  return (
    <StudioShell>
      <ReplayExecutionDetailPage executionId={executionId} />
    </StudioShell>
  );
}

import { StudioShell } from "@/components/layout/ConsoleShell";
import { PolicyDetailPage } from "@/components/policies/PolicyEnginePages";

export default async function PolicyPage({
  params,
}: {
  params: Promise<{ policyId: string }>;
}) {
  const { policyId } = await params;
  return (
    <StudioShell>
      <PolicyDetailPage policyId={decodeURIComponent(policyId)} />
    </StudioShell>
  );
}

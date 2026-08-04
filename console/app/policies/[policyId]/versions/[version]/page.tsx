import { StudioShell } from "@/components/layout/ConsoleShell";
import { PolicyVersionPage } from "@/components/policies/PolicyEnginePages";

export default async function PolicyVersionRoute({
  params,
}: {
  params: Promise<{ policyId: string; version: string }>;
}) {
  const { policyId, version } = await params;
  return (
    <StudioShell>
      <PolicyVersionPage
        policyId={decodeURIComponent(policyId)}
        version={decodeURIComponent(version)}
        mode="view"
      />
    </StudioShell>
  );
}

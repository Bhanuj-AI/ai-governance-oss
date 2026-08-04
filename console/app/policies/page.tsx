import { StudioShell } from "@/components/layout/ConsoleShell";
import { PolicyListPage } from "@/components/policies/PolicyEnginePages";

export default function PoliciesPage() {
  return (
    <StudioShell>
      <PolicyListPage />
    </StudioShell>
  );
}

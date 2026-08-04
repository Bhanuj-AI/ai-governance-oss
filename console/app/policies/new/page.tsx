import { StudioShell } from "@/components/layout/ConsoleShell";
import { PolicyCreatePage } from "@/components/policies/PolicyEnginePages";

export default function NewPolicyPage() {
  return (
    <StudioShell>
      <PolicyCreatePage />
    </StudioShell>
  );
}

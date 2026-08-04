import { DecisionListPage } from "@/components/decisions/DecisionListPage";
import { StudioShell } from "@/components/layout/ConsoleShell";

export default function DecisionsPage() {
  return (
    <StudioShell>
      <DecisionListPage />
    </StudioShell>
  );
}

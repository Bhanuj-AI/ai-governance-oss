import { StudioShell } from "@/components/layout/ConsoleShell";
import { OntologySyncEventsPage } from "@/components/ontology-sync/OntologySyncEventsPage";

export default function OntologySynchronizationPage() {
  return (
    <StudioShell>
      <OntologySyncEventsPage />
    </StudioShell>
  );
}

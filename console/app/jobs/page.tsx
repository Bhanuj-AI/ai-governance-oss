import { JobsPage } from "@/components/jobs/JobsPage";
import { StudioShell } from "@/components/layout/ConsoleShell";

export default function JobsRoute() {
  return (
    <StudioShell>
      <JobsPage />
    </StudioShell>
  );
}

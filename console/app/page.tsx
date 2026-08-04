import { StudioShell } from "@/components/layout/ConsoleShell";
import { StudioLaunch } from "@/components/onboarding/StudioLaunch";

export default function Home() {
  return (
    <StudioShell>
      <StudioLaunch />
    </StudioShell>
  );
}

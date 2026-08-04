import { StudioShell } from "@/components/layout/ConsoleShell";
import { GraphWorkspace } from "@/components/graph/GraphWorkspace";

export default function GraphPage() {
  return (
    <StudioShell>
      <GraphWorkspace />
    </StudioShell>
  );
}

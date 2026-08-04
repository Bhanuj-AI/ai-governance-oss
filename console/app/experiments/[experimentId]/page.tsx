import { StudioShell } from "@/components/layout/ConsoleShell";
import { ExperimentDetailPage } from "@/components/experiments/ExperimentDetailPage";
export default async function ExperimentRoute({ params }: { params: Promise<{ experimentId: string }> }) { const { experimentId } = await params; return <StudioShell><ExperimentDetailPage experimentId={experimentId} /></StudioShell>; }

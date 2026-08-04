import { StudioShell } from "@/components/layout/ConsoleShell";
import { ReplayDetailPage } from "@/components/replays/ReplayDetailPage";

export default async function ReplayDetailRoute({ params }: { params: Promise<{ replayId: string }> }) { const { replayId } = await params; return <StudioShell><ReplayDetailPage replayId={replayId} /></StudioShell>; }

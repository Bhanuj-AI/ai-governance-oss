import { StudioShell } from "@/components/layout/ConsoleShell";
import { AssetDetailPage } from "@/components/assets/AssetDetailPage";

export default async function AssetDetailRoute({
  params,
}: {
  params: Promise<{ kind: string; assetId: string }>;
}) {
  const { kind, assetId } = await params;
  return <StudioShell><AssetDetailPage kind={kind} assetId={assetId} /></StudioShell>;
}

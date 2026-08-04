import { StudioShell } from "@/components/layout/ConsoleShell";
import { AssetRegistryPage } from "@/components/assets/AssetRegistryPage";

export default async function AssetRegistryRoute({
  params,
}: {
  params: Promise<{ kind: string }>;
}) {
  const { kind } = await params;
  return <StudioShell><AssetRegistryPage kind={kind} /></StudioShell>;
}

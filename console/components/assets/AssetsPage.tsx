"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Boxes, Database, MessageSquareText, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  listDatasetAssets,
  listModelAssets,
  listPromptAssets,
  listProviderAssets,
} from "@/lib/api/registries";

export type AssetKind = "prompts" | "models" | "datasets" | "providers";

const REGISTRIES: { kind: AssetKind; title: string; description: string; icon: typeof MessageSquareText }[] = [
  { kind: "prompts", title: "Prompt Catalog", description: "Observed prompt identities and configurations used by governed work.", icon: MessageSquareText },
  { kind: "models", title: "Model Catalog", description: "Observed provider, model, revision, and runtime configuration.", icon: Sparkles },
  { kind: "datasets", title: "Datasets", description: "Immutable evaluation dataset records and schemas.", icon: Database },
  { kind: "providers", title: "Evaluation Providers", description: "AI Governance Control Plane-managed evaluator integrations and capabilities.", icon: ShieldCheck },
];

export function AssetsPage() {
  const searchParams = useSearchParams();
  const prompts = useQuery({ queryKey: ["asset-registry", "prompts"], queryFn: listPromptAssets });
  const models = useQuery({ queryKey: ["asset-registry", "models"], queryFn: listModelAssets });
  const datasets = useQuery({ queryKey: ["asset-registry", "datasets"], queryFn: listDatasetAssets });
  const providers = useQuery({ queryKey: ["asset-registry", "providers"], queryFn: listProviderAssets });
  const counts: Record<AssetKind, number> = {
    prompts: selectLogicalAssets(prompts.data ?? [], (item) => item.name).length,
    models: selectLogicalAssets(models.data ?? [], (item) => `${item.provider}:${item.model_name}`).length,
    datasets: selectLogicalAssets(datasets.data ?? [], (item) => item.name).length,
    providers: providers.data?.length ?? 0,
  };
  const loading = prompts.isLoading || models.isLoading || datasets.isLoading || providers.isLoading;
  const failed = prompts.isError || models.isError || datasets.isError || providers.isError;

  return <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-6 py-5">
    <div className="flex items-start gap-3"><div className="rounded-md bg-primary/10 p-2 text-primary"><Boxes className="h-5 w-5" /></div><div><h1 className="text-2xl font-semibold">Assets</h1><p className="mt-1 text-sm text-muted-foreground">Versioned, governed records for the AI assets used across AI Governance Control Plane.</p></div></div>
    {searchParams.get("onboarding") === "observe" ? <div className="rounded-md border border-primary/30 bg-primary/5 p-4 text-sm"><p className="font-medium">Observe runtime evidence</p><p className="mt-1 leading-6 text-muted-foreground">Prompt and model assets are created when your application sends instrumented runtime evidence to AI Governance Control Plane. Run an instrumented request, then return here to verify the observed prompt and model records.</p><a href="https://ai_governance.bhanuj.app/docs/tutorials/observed-assets" target="_blank" rel="noreferrer" className="mt-3 inline-block font-medium text-primary hover:underline">Open observation guide →</a></div> : null}
    {failed ? <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">Unable to load one or more asset registries.</div> : null}
    <div className="grid gap-4 lg:grid-cols-2">{REGISTRIES.map(({ kind, title, description, icon: Icon }) => <Link key={kind} href={`/assets/${kind}`} className="group"><Card className="h-full transition-colors group-hover:border-primary/60 group-hover:bg-accent/30"><CardContent className="flex h-full min-h-40 flex-col justify-between p-5"><div className="flex items-start justify-between gap-3"><div className="flex items-start gap-3"><div className="rounded-md bg-muted p-2"><Icon className="h-4 w-4" /></div><div><h2 className="font-semibold">{title}</h2><p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p></div></div><Badge variant="secondary">{loading ? "…" : counts[kind]}</Badge></div><div className="mt-5 flex items-center gap-2 text-sm font-medium text-primary">Open Catalog <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" /></div></CardContent></Card></Link>)}</div>
  </div>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "ACTIVE" || status === "FROZEN"
    ? "border-emerald-300 bg-emerald-50 text-emerald-800"
    : status === "DEPRECATED"
      ? "border-amber-300 bg-amber-50 text-amber-800"
      : status === "ARCHIVED"
        ? "border-red-300 bg-red-50 text-red-800"
        : "border-amber-300 bg-amber-50 text-amber-800";
  return <Badge variant="outline" className={tone}>{status.charAt(0) + status.slice(1).toLowerCase()}</Badge>;
}

export function AssetProvenanceBadge({ kind, provenance }: { kind: AssetKind; provenance?: "MANAGED" | "OBSERVED" | "IMPORTED" }) {
  const resolved = provenance ?? (kind === "prompts" || kind === "models" ? "OBSERVED" : "MANAGED");
  const tone = resolved === "OBSERVED" ? "border-sky-300 bg-sky-50 text-sky-800" : resolved === "IMPORTED" ? "border-amber-300 bg-amber-50 text-amber-800" : "border-violet-300 bg-violet-50 text-violet-800";
  return <Badge variant="outline" className={tone}>{resolved.charAt(0) + resolved.slice(1).toLowerCase()}</Badge>;
}

export function selectLogicalAssets<T extends { status: string; created_at: string; version: string }>(items: T[], key: (item: T) => string): T[] {
  const groups = new Map<string, T[]>();
  items.forEach((item) => groups.set(key(item), [...(groups.get(key(item)) ?? []), item]));
  return [...groups.values()].map((versions) => [...versions].sort(compareVersions)[0]);
}

export function isAssetKind(value: string): value is AssetKind { return ["prompts", "models", "datasets", "providers"].includes(value); }

function compareVersions<T extends { status: string; created_at: string; version: string }>(left: T, right: T) {
  const statusRank = (status: string) => status === "ACTIVE" ? 0 : status === "FROZEN" ? 1 : status === "DRAFT" ? 2 : status === "DEPRECATED" ? 3 : 4;
  return statusRank(left.status) - statusRank(right.status) || new Date(right.created_at).getTime() - new Date(left.created_at).getTime() || right.version.localeCompare(left.version, undefined, { numeric: true });
}

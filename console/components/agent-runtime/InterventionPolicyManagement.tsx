"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Eye, Plus, RotateCcw, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  activateEvidenceInterventionPolicy,
  createEvidenceInterventionPolicy,
  createEvidenceInterventionPolicyVersion,
  getAgentExecutionDetail,
  listEvidenceInterventionPolicies,
  previewEvidenceInterventionPolicy,
  retireEvidenceInterventionPolicy,
  validateEvidenceInterventionPolicy,
} from "@/lib/api/agent-runtime";
import type {
  AgentExecutionDetailDto,
  EvidenceInterventionPolicyCreateInput,
  EvidenceInterventionPolicyDto,
  EvidenceInterventionPolicyPreviewDto,
} from "@/types/agent-runtime";

const DEFAULT_CONFIGURATION = JSON.stringify({ json_schema: { type: "object" } }, null, 2);
const DEFAULT_JSON_SCHEMA: Record<string, unknown> = { type: "object" };
const STRATEGIES = ["NULLIFY", "REPLACE", "PERTURB"] as const;
const SELECT_CLASS = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
const TEXTAREA_CLASS = "min-h-40 w-full rounded-md border border-input bg-background p-3 font-mono text-xs shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring";

type LifecycleOperation = "validate" | "activate" | "retire" | "version";
type PolicyTarget = Pick<EvidenceInterventionPolicyCreateInput, "tool_name" | "schema_id" | "schema_version">;
type ObservedToolEvidence = PolicyTarget & {
  eventId: string;
  evidenceReference: string;
  replayAdapterId: string;
  jsonSchema: Record<string, unknown>;
  schemaFields: SchemaField[];
};
type SchemaField = { path: string; label: string; type: string };
type PerturbOperation = {
  path: string;
  operation: "SET" | "NUMERIC_DELTA" | "NUMERIC_SCALE" | "REMOVE_OPTIONAL";
  value: string;
  minimum: string;
  maximum: string;
};

export function InterventionPolicyManagement({ onOpenHelp, selectedExecutionId }: { onOpenHelp: () => void; selectedExecutionId?: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["evidence-intervention-policies"], queryFn: listEvidenceInterventionPolicies });
  const [createOpen, setCreateOpen] = useState(false);
  const [previewPolicy, setPreviewPolicy] = useState<EvidenceInterventionPolicyDto | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    // A selected execution is a route-driven user command to open the form.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (selectedExecutionId) setCreateOpen(true);
  }, [selectedExecutionId]);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["evidence-intervention-policies"] });

  const create = useMutation({
    mutationFn: createEvidenceInterventionPolicy,
    onSuccess: async (policy) => {
      await refresh();
      setCreateOpen(false);
      setError(null);
      setMessage(`Created ${policy.policy_id} v${policy.version} as a draft.`);
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "The policy could not be created."),
  });
  const lifecycle = useMutation({
    mutationFn: async ({ operation, policy, configuration }: { operation: LifecycleOperation; policy: EvidenceInterventionPolicyDto; configuration?: Record<string, unknown> }) => {
      if (operation === "validate") return validateEvidenceInterventionPolicy(policy.policy_id, policy.version);
      if (operation === "activate") return activateEvidenceInterventionPolicy(policy.policy_id, policy.version);
      if (operation === "retire") return retireEvidenceInterventionPolicy(policy.policy_id, policy.version);
      return createEvidenceInterventionPolicyVersion(policy.policy_id, policy.version, configuration ?? policy.strategy_configuration);
    },
    onSuccess: async (policy, variables) => {
      await refresh();
      setError(null);
      setMessage(variables.operation === "version" ? `Created ${policy.policy_id} v${policy.version} as a draft.` : `${variables.operation[0].toUpperCase()}${variables.operation.slice(1)}d ${policy.policy_id} v${policy.version}.`);
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "The policy action could not be completed."),
  });
  const preview = useMutation({
    mutationFn: ({ policy, executionId, toolCallId, strategy, seed }: { policy: EvidenceInterventionPolicyDto; executionId: string; toolCallId: string; strategy: string; seed: number }) => previewEvidenceInterventionPolicy(policy.policy_id, policy.version, { execution_id: executionId, tool_call_id: toolCallId, strategy, seed }),
    onError: (reason) => setError(reason instanceof Error ? reason.message : "The preview could not be generated."),
  });

  if (query.isLoading) return <LoadingState label="Loading intervention policies…" />;
  if (query.isError) return <ErrorState>Intervention policies could not be loaded.</ErrorState>;
  const policies = query.data?.items ?? [];

  return <section className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/10 p-4">
      <div><h3 className="font-medium">Intervention Policies</h3><p className="mt-1 text-sm text-muted-foreground">Define, validate, preview, activate, retire, and version the counterfactual evidence permitted for a tool.</p></div>
      <div className="flex gap-2"><Button variant="outline" size="sm" onClick={onOpenHelp}>How policies work</Button><Button size="sm" onClick={() => { setCreateOpen((open) => !open); setError(null); }}><Plus className="h-4 w-4" />Create Policy</Button></div>
    </div>
    {message ? <p aria-live="polite" className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-800 dark:text-emerald-300">{message}</p> : null}
    {error ? <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p> : null}
    {createOpen ? <CreatePolicyForm selectedExecutionId={selectedExecutionId} pending={create.isPending} onCancel={() => setCreateOpen(false)} onSubmit={(input) => { setError(null); create.mutate(input); }} /> : null}
    {previewPolicy ? <PreviewPolicyForm policy={previewPolicy} pending={preview.isPending} result={preview.data} onClose={() => { setPreviewPolicy(null); preview.reset(); }} onSubmit={(input) => { setError(null); preview.mutate(input); }} /> : null}
    {policies.length === 0 ? <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground"><p className="font-medium text-foreground">No intervention policies yet</p><p className="mt-1">Create and activate a policy before running a governed counterfactual audit.</p></div> : <PolicyTable policies={policies} pending={lifecycle.isPending} onPreview={(policy) => { setPreviewPolicy(policy); preview.reset(); }} onAction={(operation, policy, configuration) => { setError(null); lifecycle.mutate({ operation, policy, configuration }); }} />}
  </section>;
}

function CreatePolicyForm({ selectedExecutionId, pending, onCancel, onSubmit }: { selectedExecutionId?: string; pending: boolean; onCancel: () => void; onSubmit: (input: EvidenceInterventionPolicyCreateInput) => void }) {
  const router = useRouter();
  const [executionId, setExecutionId] = useState("");
  const [toolCallId, setToolCallId] = useState("");
  const [manualTarget, setManualTarget] = useState(false);
  const [target, setTarget] = useState<PolicyTarget>({ tool_name: "", schema_id: "", schema_version: "" });
  const [selectedStrategy, setSelectedStrategy] = useState<(typeof STRATEGIES)[number]>("REPLACE");
  const [neutralValue, setNeutralValue] = useState("{}");
  const [replacementReferences, setReplacementReferences] = useState([""]);
  const [operations, setOperations] = useState<PerturbOperation[]>([]);
  const [advancedConfiguration, setAdvancedConfiguration] = useState(DEFAULT_CONFIGURATION);
  const [advancedConfigurationOpen, setAdvancedConfigurationOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const executionDetail = useQuery({ queryKey: ["agent-execution", executionId, "policy-source"], queryFn: () => getAgentExecutionDetail(executionId), enabled: Boolean(executionId) });
  const evidence = extractObservedToolEvidence(executionDetail.data);
  const selectedEvidence = evidence.find((item) => item.eventId === toolCallId);

  useEffect(() => {
    if (selectedExecutionId && selectedExecutionId !== executionId) {
      // The route selection deliberately resets this dependent form state.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExecutionId(selectedExecutionId);
      setToolCallId("");
      setManualTarget(false);
      setTarget({ tool_name: "", schema_id: "", schema_version: "" });
    }
  }, [executionId, selectedExecutionId]);

  function chooseEvidence(nextToolCallId: string) {
    setToolCallId(nextToolCallId);
    const selected = evidence.find((item) => item.eventId === nextToolCallId);
    if (selected) {
      setTarget({ tool_name: selected.tool_name, schema_id: selected.schema_id, schema_version: selected.schema_version });
      setManualTarget(false);
    }
  }
  function chooseStrategy(strategy: (typeof STRATEGIES)[number]) {
    setSelectedStrategy(strategy);
    if (strategy === "PERTURB" && operations.length === 0) {
      setOperations([{ path: "", operation: "SET", value: "", minimum: "", maximum: "" }]);
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!manualTarget && !selectedEvidence) {
      setFormError("Select an observed tool result so Studio can use its published evidence schema.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const parsedConfiguration = parseObject(
      String(form.get("configuration")),
      "Strategy configuration",
    );
    if (!parsedConfiguration) return;
    const strategies = [selectedStrategy];
    onSubmit({ ...target, provider_id: String(form.get("provider_id")).trim() || "structured-json", provider_version: String(form.get("provider_version")).trim() || "v1", allowed_strategies: [...strategies], strategy_configuration: parsedConfiguration });
  }

  return <form onSubmit={submit} className="overflow-hidden rounded-lg border bg-card shadow-sm">
    <div className="border-b bg-muted/30 px-5 py-4"><h3 className="font-semibold">Create Intervention Policy</h3><p className="mt-1 text-sm text-muted-foreground">Start from observed evidence. Studio copies the tool and schema identity from the selected runtime event, then the server validates the governed configuration before activation.</p></div>
    <div className="grid gap-5 p-5">
      <section className="rounded-md border bg-muted/10 p-4">
        <div className="mb-5"><p className="text-lg font-semibold tracking-tight text-foreground">Step 1</p><h4 className="mt-1 text-xl font-semibold tracking-tight">Select Observed Tool Evidence</h4><p className="mt-1 text-sm text-muted-foreground">This is the source of truth for the tool name and Evidence Schema ID</p></div>
        <div className="grid gap-4 md:grid-cols-2">
          <FormField label="Observed execution" description="Choose any completed execution in the current tenant."><Button type="button" variant="outline" className="h-10 w-full justify-between px-3 text-left font-normal" onClick={() => router.push("/agents-runtime/executions/select")}>{executionDetail.data ? <span className="truncate">{executionDetail.data.execution.agent_name || executionDetail.data.execution.agent_id} · {executionDetail.data.execution.external_execution_id}</span> : <span className="text-muted-foreground">Browse executions</span>}<span className="ml-3 inline-flex shrink-0 items-center gap-1 text-primary">Choose <ChevronRight className="h-4 w-4" /></span></Button></FormField>
          <FormField label="Auditable tool result" description="Only tool calls that publish a causal evidence descriptor appear here."><select value={toolCallId} onChange={(event) => chooseEvidence(event.target.value)} className={SELECT_CLASS} disabled={!executionId || executionDetail.isLoading || evidence.length === 0}><option value="">{!executionId ? "Select an execution first" : executionDetail.isLoading ? "Loading tool evidence…" : evidence.length === 0 ? "No auditable tool evidence found" : "Select a tool result"}</option>{evidence.map((item) => <option key={item.eventId} value={item.eventId}>{item.tool_name} · {item.schema_id} v{item.schema_version}</option>)}</select></FormField>
        </div>
        {executionDetail.isError ? <p className="mt-3 text-sm text-destructive">The execution timeline could not be loaded. Select another execution or try again.</p> : null}
        {executionId && executionDetail.isSuccess && evidence.length === 0 ? <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">This execution contains no schema-described tool result. Configure the runtime adapter to publish a causal evidence descriptor before creating a governed policy from it.</p> : null}
      </section>
      <section>
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3"><div><p className="text-lg font-semibold tracking-tight text-foreground">Step 2</p><h4 className="mt-1 text-xl font-semibold tracking-tight">Policy Target</h4><p className="mt-1 text-sm text-muted-foreground">The target must exactly match the evidence identity presented by the runtime.</p></div><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={manualTarget} onChange={(event) => setManualTarget(event.target.checked)} className="h-4 w-4 rounded border-input accent-primary" />Enter identifiers manually</label></div>
        <div className="grid gap-4 md:grid-cols-3">
          <FormField label="Tool name" description={manualTarget ? "Exact tool identifier emitted by your runtime." : "Derived from the selected tool result."}><Input name="tool_name" value={target.tool_name} onChange={(event) => setTarget((current) => ({ ...current, tool_name: event.target.value }))} placeholder="credit_history.lookup" readOnly={!manualTarget} required className="h-10 read-only:bg-muted/40" /></FormField>
          <FormField label="Evidence Schema ID" description={manualTarget ? "Use the schema ID published by the runtime integration." : "Derived from the selected tool result."}><Input name="schema_id" value={target.schema_id} onChange={(event) => setTarget((current) => ({ ...current, schema_id: event.target.value }))} placeholder="CreditHistoryResponse" readOnly={!manualTarget} required className="h-10 read-only:bg-muted/40" /></FormField>
          <FormField label="Schema version" description="Schema version emitted by the runtime."><Input name="schema_version" value={target.schema_version} onChange={(event) => setTarget((current) => ({ ...current, schema_version: event.target.value }))} placeholder="v1" readOnly={!manualTarget} required className="h-10 read-only:bg-muted/40" /></FormField>
        </div>
        {selectedEvidence ? <div className="mt-4 grid gap-2 rounded-md border bg-muted/10 p-3 text-xs text-muted-foreground sm:grid-cols-3"><span>Tool call <strong className="font-mono text-foreground">{selectedEvidence.eventId}</strong></span><span>Evidence <strong className="font-mono text-foreground">{selectedEvidence.evidenceReference}</strong></span><span>Replay adapter <strong className="font-mono text-foreground">{selectedEvidence.replayAdapterId}</strong></span></div> : null}
      </section>
      <section className="border-t pt-5">
        <p className="text-lg font-semibold tracking-tight text-foreground">Step 3</p><h4 className="mt-1 text-xl font-semibold tracking-tight">Counterfactual Controls</h4>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <FormField label="Intervention provider" description="Provider that generates schema-valid controlled evidence."><Input name="provider_id" defaultValue="structured-json" className="h-10" /></FormField>
          <FormField label="Provider version" description="Version of the intervention provider contract."><Input name="provider_version" defaultValue="v1" className="h-10" /></FormField>
          <fieldset className="rounded-md border p-4 text-sm md:col-span-2"><legend className="px-1 font-medium">Intervention strategy</legend><p className="mb-3 text-xs text-muted-foreground">Choose one controlled intervention for this policy version. Create a new version to govern a different strategy.</p><div className="grid gap-3 md:grid-cols-3">{STRATEGIES.map((strategy) => <label key={strategy} className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${selectedStrategy === strategy ? "border-primary bg-primary/5" : "bg-background hover:bg-muted/30"}`}><input name="strategy" type="radio" checked={selectedStrategy === strategy} onChange={() => chooseStrategy(strategy)} className="mt-0.5 h-4 w-4 border-input accent-primary" /><span><span className="block font-medium">{strategy}</span><span className="mt-1 block text-xs text-muted-foreground">{strategy === "NULLIFY" ? "Use a neutral, schema-valid value." : strategy === "REPLACE" ? "Use an authorized alternate evidence reference." : "Apply bounded changes to a schema field."}</span></span></label>)}</div></fieldset>
          <StrategyConfigurationForm selectedStrategy={selectedStrategy} schema={selectedEvidence?.jsonSchema ?? DEFAULT_JSON_SCHEMA} schemaFields={selectedEvidence?.schemaFields ?? []} neutralValue={neutralValue} onNeutralValueChange={setNeutralValue} replacementReferences={replacementReferences} onReplacementReferencesChange={setReplacementReferences} operations={operations} onOperationsChange={setOperations} advancedOpen={advancedConfigurationOpen} onAdvancedOpenChange={(open, configuration) => { setAdvancedConfigurationOpen(open); if (open && configuration) setAdvancedConfiguration(configuration); }} advancedConfiguration={advancedConfiguration} onAdvancedConfigurationChange={setAdvancedConfiguration} />
        </div>
      </section>
      {formError ? <p role="alert" className="text-sm text-destructive">{formError}</p> : null}
    </div>
    <div className="flex flex-wrap items-center justify-between gap-4 border-t bg-muted/10 px-5 py-4"><div><p className="text-lg font-semibold tracking-tight text-foreground">Step 4</p><p className="mt-0.5 text-sm text-muted-foreground">Review the governed controls, then create an immutable draft.</p></div><div className="flex flex-wrap gap-2"><Button type="submit" disabled={pending || (!manualTarget && !selectedEvidence)}>{pending ? "Creating…" : "Create draft"}</Button><Button type="button" variant="outline" onClick={onCancel} disabled={pending}>Cancel</Button></div></div>
  </form>;
}

function PolicyTable({ policies, pending, onPreview, onAction }: { policies: EvidenceInterventionPolicyDto[]; pending: boolean; onPreview: (policy: EvidenceInterventionPolicyDto) => void; onAction: (operation: LifecycleOperation, policy: EvidenceInterventionPolicyDto, configuration?: Record<string, unknown>) => void }) {
  return <div className="overflow-x-auto rounded-lg border"><table className="w-full text-sm"><thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th className="px-4 py-3">Policy</th><th className="px-4 py-3">Tool</th><th className="px-4 py-3">Evidence schema</th><th className="px-4 py-3">Strategies</th><th className="px-4 py-3">Counterfactual controls</th><th className="px-4 py-3">Version</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Actions</th></tr></thead><tbody className="divide-y">{policies.map((policy) => <PolicyRow key={`${policy.policy_id}:${policy.version}`} policy={policy} pending={pending} onPreview={() => onPreview(policy)} onAction={(operation, configuration) => onAction(operation, policy, configuration)} />)}</tbody></table></div>;
}

function PolicyRow({ policy, pending, onPreview, onAction }: { policy: EvidenceInterventionPolicyDto; pending: boolean; onPreview: () => void; onAction: (operation: LifecycleOperation, configuration?: Record<string, unknown>) => void }) {
  const [versionOpen, setVersionOpen] = useState(false);
  const [configuration, setConfiguration] = useState(JSON.stringify(policy.strategy_configuration, null, 2));
  const statusClassName = policy.status === "ACTIVE"
    ? "border-emerald-200 bg-emerald-300 text-slate-950"
    : policy.status === "DRAFT"
      ? "border-amber-200 bg-amber-300 text-slate-950"
      : "border-slate-300 bg-slate-300 text-slate-950";
  return <><tr><td className="px-4 py-3 font-mono text-xs">{policy.policy_id}</td><td className="px-4 py-3">{policy.tool_name}</td><td className="px-4 py-3">{policy.schema_id} <span className="text-muted-foreground">v{policy.schema_version}</span></td><td className="px-4 py-3">{policy.allowed_strategies.join(", ")}</td><td className="px-4 py-3"><PerturbationSummary policy={policy} /></td><td className="px-4 py-3">{policy.version}</td><td className="px-4 py-3"><Badge variant="outline" className={statusClassName}>{policy.status}</Badge></td><td className="px-4 py-3"><div className="flex flex-wrap gap-2">{policy.status === "DRAFT" ? <><Button size="sm" variant="outline" onClick={onPreview} disabled={pending}><Eye className="h-3.5 w-3.5" />Preview</Button><Button size="sm" variant="outline" onClick={() => onAction("validate")} disabled={pending}><Check className="h-3.5 w-3.5" />Validate</Button><Button size="sm" onClick={() => onAction("activate")} disabled={pending}><ShieldCheck className="h-3.5 w-3.5" />Activate</Button></> : null}{policy.status === "ACTIVE" ? <><Button size="sm" onClick={() => setVersionOpen((open) => !open)} disabled={pending} className="border border-cyan-200 bg-cyan-300 text-slate-950 hover:bg-cyan-200"><Plus className="h-3.5 w-3.5" />New version</Button><Button size="sm" onClick={() => onAction("retire")} disabled={pending} className="border border-rose-200 bg-rose-300 text-slate-950 hover:bg-rose-200"><RotateCcw className="h-3.5 w-3.5" />Retire</Button></> : null}</div></td></tr>{versionOpen ? <tr><td colSpan={8} className="bg-muted/10 p-4"><FormField label="New Strategy Configuration (JSON)"><JsonEditor value={configuration} onChange={setConfiguration} rows="compact" /></FormField><div className="mt-3 flex gap-2"><Button size="sm" onClick={() => { const parsed = parseObject(configuration, "Strategy configuration"); if (parsed) { onAction("version", parsed); setVersionOpen(false); } }} disabled={pending}>Create draft version</Button><Button size="sm" variant="outline" onClick={() => setVersionOpen(false)} disabled={pending}>Cancel</Button></div></td></tr> : null}</>;
}

function PerturbationSummary({ policy }: { policy: EvidenceInterventionPolicyDto }) {
  if (!policy.allowed_strategies.includes("PERTURB")) return <span className="text-xs text-muted-foreground">Not applicable</span>;
  if (policy.provider_id === "opaque-reference") return <span className="text-xs text-muted-foreground">Runtime-owned transformation</span>;
  const operations = policy.strategy_configuration.operations;
  if (!Array.isArray(operations) || operations.length === 0) return <span className="text-xs text-muted-foreground">No field operations declared</span>;
  return <ul className="space-y-2 text-xs">{operations.map((operation, index) => <li key={index}><PerturbationOperation operation={operation} /></li>)}</ul>;
}

function PerturbationOperation({ operation: value }: { operation: unknown }) {
  if (!isRecord(value)) return <span className="text-muted-foreground">Invalid operation</span>;
  const path = readString(value.path) ?? "Unknown field";
  const operation = readString(value.operation) ?? "Unknown operation";
  const description = operation === "NUMERIC_DELTA" ? "Numeric delta" : operation === "NUMERIC_SCALE" ? "Numeric scale" : operation === "SET" ? "Set value" : operation === "REMOVE_OPTIONAL" ? "Remove optional value" : operation;
  const valueSummary = operation === "NUMERIC_DELTA" ? formatSignedNumber(value.delta) : operation === "NUMERIC_SCALE" ? formatNumber(value.scale) : operation === "SET" ? formatValue(value.value) : null;
  const bounds = formatBounds(value.minimum, value.maximum);
  return <div className="grid gap-0.5"><div className="font-mono text-foreground">{path} · {description}</div>{valueSummary || bounds ? <div className="font-mono text-muted-foreground">{[valueSummary, bounds].filter(Boolean).join(" · ")}</div> : null}</div>;
}

function formatSignedNumber(value: unknown): string { const number = readFiniteNumber(value); return number === undefined ? "not configured" : `${number > 0 ? "+" : ""}${number}`; }
function formatNumber(value: unknown): string { const number = readFiniteNumber(value); return number === undefined ? "not configured" : String(number); }
function formatValue(value: unknown): string { return typeof value === "string" ? JSON.stringify(value) : value === undefined ? "not configured" : JSON.stringify(value); }
function formatBounds(minimum: unknown, maximum: unknown): string | null { const min = readFiniteNumber(minimum); const max = readFiniteNumber(maximum); if (min !== undefined && max !== undefined) return `range ${min}–${max}`; if (min !== undefined) return `minimum ${min}`; return max !== undefined ? `maximum ${max}` : null; }
function readFiniteNumber(value: unknown): number | undefined { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }

function PreviewPolicyForm({ policy, pending, result, onClose, onSubmit }: { policy: EvidenceInterventionPolicyDto; pending: boolean; result?: EvidenceInterventionPolicyPreviewDto; onClose: () => void; onSubmit: (input: { policy: EvidenceInterventionPolicyDto; executionId: string; toolCallId: string; strategy: string; seed: number }) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); onSubmit({ policy, executionId: String(form.get("execution_id")).trim(), toolCallId: String(form.get("tool_call_id")).trim(), strategy: String(form.get("strategy")), seed: Number(form.get("seed") || 0) }); }
  return <form onSubmit={submit} className="overflow-hidden rounded-lg border bg-card shadow-sm"><div className="border-b bg-muted/30 px-5 py-4"><h3 className="font-semibold">Preview {policy.policy_id} v{policy.version}</h3><p className="mt-1 text-sm text-muted-foreground">Preview resolves and validates a counterfactual but never runs Replay.</p></div><div className="grid gap-4 p-5 md:grid-cols-2"><FormField label="Execution ID" description="Execution containing the tool evidence to preview."><Input name="execution_id" required className="h-10" /></FormField><FormField label="Tool call ID" description="Tool-call event ID from that execution."><Input name="tool_call_id" required className="h-10" /></FormField><FormField label="Strategy"><select name="strategy" defaultValue={policy.allowed_strategies[0]} className={SELECT_CLASS}>{policy.allowed_strategies.map((strategy) => <option key={strategy}>{strategy}</option>)}</select></FormField><FormField label="Seed" description="Makes a stochastic strategy reproducible."><Input name="seed" type="number" defaultValue="0" className="h-10" /></FormField>{result ? <div className="rounded-md border bg-muted/10 p-3 text-sm md:col-span-2"><p className="font-medium text-emerald-700 dark:text-emerald-300">Schema valid · semantic valid · materially different</p><dl className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2"><div><dt>Counterfactual digest</dt><dd className="break-all font-mono text-foreground">{result.counterfactual_evidence_digest}</dd></div><div><dt>Reference</dt><dd className="break-all font-mono text-foreground">{result.counterfactual_evidence_ref}</dd></div></dl></div> : null}</div><div className="flex gap-2 border-t bg-muted/10 px-5 py-4"><Button type="submit" disabled={pending}>{pending ? "Generating…" : "Generate preview"}</Button><Button type="button" variant="outline" onClick={onClose} disabled={pending}>Close</Button></div></form>;
}

function StrategyConfigurationForm({ selectedStrategy, schema, schemaFields, neutralValue, onNeutralValueChange, replacementReferences, onReplacementReferencesChange, operations, onOperationsChange, advancedOpen, onAdvancedOpenChange, advancedConfiguration, onAdvancedConfigurationChange }: { selectedStrategy: (typeof STRATEGIES)[number]; schema: Record<string, unknown>; schemaFields: SchemaField[]; neutralValue: string; onNeutralValueChange: (value: string) => void; replacementReferences: string[]; onReplacementReferencesChange: (value: string[]) => void; operations: PerturbOperation[]; onOperationsChange: (value: PerturbOperation[]) => void; advancedOpen: boolean; onAdvancedOpenChange: (open: boolean, configuration?: string) => void; advancedConfiguration: string; onAdvancedConfigurationChange: (value: string) => void }) {
  const primaryConfiguration = buildPrimaryConfiguration(selectedStrategy, schema, neutralValue, replacementReferences, operations);
  const updateOperation = (index: number, key: keyof PerturbOperation, value: string) => onOperationsChange(operations.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  const removeOperation = (index: number) => onOperationsChange(operations.filter((_, itemIndex) => itemIndex !== index));
  const addOperation = () => onOperationsChange([...operations, { path: "", operation: "SET", value: "", minimum: "", maximum: "" }]);
  return <section className="space-y-4 md:col-span-2">
    <input type="hidden" name="configuration" value={advancedOpen ? advancedConfiguration : JSON.stringify(primaryConfiguration)} />
    {selectedStrategy === "NULLIFY" ? <section className="rounded-md border bg-muted/10 p-4"><h5 className="font-medium">NULLIFY — neutral value</h5><p className="mt-1 text-sm text-muted-foreground">Define the schema-valid value used when this evidence is unavailable.</p><div className="mt-3"><JsonEditor value={neutralValue} onChange={onNeutralValueChange} rows="compact" /></div></section> : null}
    {selectedStrategy === "REPLACE" ? <section className="rounded-md border bg-muted/10 p-4"><h5 className="font-medium">REPLACE — authorized evidence references</h5><p className="mt-1 text-sm text-muted-foreground">Add only references your runtime resolver is authorized to resolve. One is selected deterministically for each replay seed.</p><div className="mt-3 space-y-2">{replacementReferences.map((reference, index) => <div key={index} className="flex gap-2"><Input value={reference} required={index === 0} onChange={(event) => onReplacementReferencesChange(replacementReferences.map((item, itemIndex) => itemIndex === index ? event.target.value : item))} placeholder="artifact://approved-replacements/…" className="h-10 font-mono text-xs" />{replacementReferences.length > 1 ? <Button type="button" size="sm" variant="outline" onClick={() => onReplacementReferencesChange(replacementReferences.filter((_, itemIndex) => itemIndex !== index))}>Remove</Button> : null}</div>)}</div><Button type="button" size="sm" variant="outline" className="mt-3" onClick={() => onReplacementReferencesChange([...replacementReferences, ""])}><Plus className="h-3.5 w-3.5" />Add reference</Button></section> : null}
    {selectedStrategy === "PERTURB" ? <section className="rounded-md border bg-muted/10 p-4"><h5 className="font-medium">PERTURB — bounded field operations</h5><p className="mt-1 text-sm text-muted-foreground">Each operation is applied to an isolated counterfactual only.</p>{schemaFields.length === 0 ? <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">This runtime published a schema identifier but no field map. Enter a JSON Pointer manually or use Advanced configuration.</p> : null}<div className="mt-3 space-y-3">{operations.map((item, index) => <div key={index} className="grid gap-3 rounded-md border bg-background p-3 md:grid-cols-[minmax(0,1.1fr)_190px_minmax(0,1fr)_110px_110px_auto]"><FormField label="Field path">{schemaFields.length > 0 ? <select value={item.path} onChange={(event) => updateOperation(index, "path", event.target.value)} className={SELECT_CLASS} required><option value="">Select a schema field</option>{schemaFields.map((field) => <option key={field.path} value={field.path}>{field.label} · {field.path} ({field.type})</option>)}</select> : <Input value={item.path} onChange={(event) => updateOperation(index, "path", event.target.value)} placeholder="/risk_score" required className="h-10 font-mono text-xs" />}</FormField><FormField label="Operation"><select value={item.operation} onChange={(event) => updateOperation(index, "operation", event.target.value)} className={SELECT_CLASS}><option value="SET">Set value</option><option value="NUMERIC_DELTA">Numeric delta</option><option value="NUMERIC_SCALE">Numeric scale</option><option value="REMOVE_OPTIONAL">Remove optional</option></select></FormField>{item.operation === "REMOVE_OPTIONAL" ? <div className="hidden md:block" /> : <FormField label={item.operation === "SET" ? "Value" : item.operation === "NUMERIC_DELTA" ? "Delta" : "Scale"}><Input value={item.value} onChange={(event) => updateOperation(index, "value", event.target.value)} type={item.operation === "SET" ? "text" : "number"} step="any" placeholder={item.operation === "SET" ? "JSON value" : "0"} required className="h-10" /></FormField>}<FormField label="Minimum"><Input value={item.minimum} onChange={(event) => updateOperation(index, "minimum", event.target.value)} type="number" step="any" disabled={item.operation === "SET" || item.operation === "REMOVE_OPTIONAL"} className="h-10" /></FormField><FormField label="Maximum"><Input value={item.maximum} onChange={(event) => updateOperation(index, "maximum", event.target.value)} type="number" step="any" disabled={item.operation === "SET" || item.operation === "REMOVE_OPTIONAL"} className="h-10" /></FormField><Button type="button" size="sm" variant="outline" className="self-end" onClick={() => removeOperation(index)}>Remove</Button></div>)}</div><Button type="button" size="sm" variant="outline" className="mt-3" onClick={addOperation}><Plus className="h-3.5 w-3.5" />Add operation</Button></section> : null}
    <details open={advancedOpen} onToggle={(event) => { const open = event.currentTarget.open; onAdvancedOpenChange(open, open ? JSON.stringify(primaryConfiguration, null, 2) : undefined); }} className="rounded-md border"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Advanced configuration (JSON)</summary><div className="border-t p-4"><p className="mb-3 text-sm text-muted-foreground">Use this only for provider-specific configuration not represented above. This JSON is persisted exactly as shown.</p><JsonEditor value={advancedConfiguration} onChange={onAdvancedConfigurationChange} /></div></details>
  </section>;
}

function JsonEditor({ value, onChange, rows = "default" }: { value: string; onChange: (value: string) => void; rows?: "default" | "compact" }) {
  const validationError = jsonValidationError(value);
  const format = () => {
    if (validationError) return;
    onChange(JSON.stringify(JSON.parse(value), null, 2));
  };
  return <div>
    <div className={`overflow-hidden rounded-md border bg-background shadow-sm ${validationError ? "border-destructive/60" : "border-input"}`}>
      <div className="flex items-center justify-between gap-3 border-b bg-muted/40 px-3 py-2">
        <span className="font-mono text-xs font-medium text-muted-foreground">JSON</span>
        <div className="flex items-center gap-3"><span aria-live="polite" className={`text-xs font-medium ${validationError ? "text-destructive" : "text-emerald-700 dark:text-emerald-300"}`}>{validationError ? "Invalid JSON" : "Valid JSON"}</span><Button type="button" variant="outline" size="sm" onClick={format} disabled={Boolean(validationError)}>Format</Button></div>
      </div>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} aria-invalid={Boolean(validationError)} className={`${TEXTAREA_CLASS} ${rows === "compact" ? "min-h-32" : "min-h-48"} resize-y rounded-none border-0 shadow-none focus:ring-0`} spellCheck={false} />
    </div>
    {validationError ? <p role="alert" className="mt-1.5 text-xs text-destructive">{validationError}</p> : <p className="mt-1.5 text-xs text-muted-foreground">Use Format to pretty-print the current JSON before validation or activation.</p>}
  </div>;
}

function FormField({ label, description, className, children }: { label: string; description?: string; className?: string; children: ReactNode }) { return <label className={`grid gap-1.5 text-sm ${className ?? ""}`}><span className="font-medium">{label}</span>{children}{description ? <span className="text-xs leading-5 text-muted-foreground">{description}</span> : null}</label>; }
function LoadingState({ label }: { label: string }) { return <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">{label}</div>; }
function ErrorState({ children }: { children: ReactNode }) { return <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{children}</div>; }

function extractObservedToolEvidence(detail: AgentExecutionDetailDto | undefined): ObservedToolEvidence[] {
  if (!detail) return [];
  return detail.events.flatMap((event) => {
    if (event.event_type !== "TOOL_CALL") return [];
    const causalReplay = event.attributes.causal_replay;
    if (!isRecord(causalReplay) || !isRecord(causalReplay.evidence_descriptor)) return [];
    const descriptor = causalReplay.evidence_descriptor;
    const toolName = readString(descriptor.tool_name) ?? readString(event.attributes.tool);
    const schemaId = readString(descriptor.schema_id);
    const schemaVersion = readString(descriptor.schema_version);
    const evidenceReference = readString(descriptor.evidence_ref);
    const replayAdapterId = readString(descriptor.replay_adapter_id);
    if (!toolName || !schemaId || !schemaVersion || !evidenceReference || !replayAdapterId) return [];
    const metadata = isRecord(descriptor.metadata) ? descriptor.metadata : {};
    const jsonSchema = isRecord(metadata.json_schema) ? metadata.json_schema : DEFAULT_JSON_SCHEMA;
    return [{ eventId: event.event_id, tool_name: toolName, schema_id: schemaId, schema_version: schemaVersion, evidenceReference, replayAdapterId, jsonSchema, schemaFields: schemaFieldsFromJsonSchema(jsonSchema) }];
  });
}
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function readString(value: unknown): string | undefined { return typeof value === "string" && value.trim() ? value : undefined; }
function schemaFieldsFromJsonSchema(schema: Record<string, unknown>, basePath = ""): SchemaField[] {
  const properties = isRecord(schema.properties) ? schema.properties : {};
  return Object.entries(properties).flatMap(([name, definition]) => {
    if (!isRecord(definition)) return [];
    const path = `${basePath}/${name.replaceAll("~", "~0").replaceAll("/", "~1")}`;
    const type = readString(definition.type) ?? "value";
    const label = readString(definition.title) ?? name.replaceAll("_", " ");
    const nested = type === "object" ? schemaFieldsFromJsonSchema(definition, path) : [];
    return nested.length ? nested : [{ path, label, type }];
  });
}
function buildPrimaryConfiguration(selectedStrategy: (typeof STRATEGIES)[number], schema: Record<string, unknown>, neutralValue: string, replacementReferences: string[], operations: PerturbOperation[]): Record<string, unknown> {
  const configuration: Record<string, unknown> = { json_schema: schema };
  if (selectedStrategy === "NULLIFY") configuration.neutral_value = parseJsonValue(neutralValue);
  if (selectedStrategy === "REPLACE") configuration.replacement_references = replacementReferences.filter((reference) => reference.trim());
  if (selectedStrategy === "PERTURB") configuration.operations = operations.map((item) => {
    const operation: Record<string, unknown> = { path: item.path, operation: item.operation };
    if (item.operation === "SET") operation.value = parseJsonValue(item.value);
    if (item.operation === "NUMERIC_DELTA") operation.delta = Number(item.value);
    if (item.operation === "NUMERIC_SCALE") operation.scale = Number(item.value);
    if (item.minimum !== "") operation.minimum = Number(item.minimum);
    if (item.maximum !== "") operation.maximum = Number(item.maximum);
    return operation;
  });
  return configuration;
}
function parseJsonValue(value: string): unknown { try { return JSON.parse(value); } catch { return value; } }
function jsonValidationError(value: string): string | null { try { const parsed: unknown = JSON.parse(value); return isRecord(parsed) ? null : "Configuration must be a JSON object."; } catch (error) { return error instanceof Error ? error.message : "Configuration is not valid JSON."; } }
function parseObject(value: string, label: string): Record<string, unknown> | null { try { const parsed: unknown = JSON.parse(value); if (!isRecord(parsed)) throw new Error(); return parsed; } catch { window.alert(`${label} must be a JSON object.`); return null; } }

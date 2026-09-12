"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, CircleAlert, Plus, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createRuntimeConnection,
  listRuntimeConnectionProviders,
  listRuntimeConnections,
  testRuntimeConnection,
  updateRuntimeConnection,
  validateRuntimeConnection,
  type RuntimeConnection,
  type RuntimeConnectionInput,
} from "@/lib/api/runtime-connections";

const CONNECTIONS_KEY = ["runtime-connections"] as const;

type TestNotice = { tone: "success" | "error"; title: string; detail: string };

function connectionPayload({ displayName, provider, baseUrl, organization, apiKeyReference, enabled, scope }: {
  displayName: string; provider: string; baseUrl: string; organization: string; apiKeyReference: string; enabled: boolean; scope: "ORGANIZATION" | "PROJECT";
}): RuntimeConnectionInput {
  const settings: Record<string, unknown> = {};
  if (baseUrl.trim()) settings.base_url = baseUrl.trim();
  if (organization.trim()) settings.organization = organization.trim();
  const secret_refs: Record<string, string> = {};
  if (apiKeyReference.trim()) secret_refs.api_key = apiKeyReference.trim();
  return { display_name: displayName.trim(), provider, settings, secret_refs, enabled, scope };
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "The connection could not be tested. Try again.";
}

function ConnectionTestNotice({ notice }: { notice: TestNotice }) {
  const successful = notice.tone === "success";
  const Icon = successful ? CheckCircle2 : CircleAlert;
  return <div role={successful ? "status" : "alert"} aria-live={successful ? "polite" : "assertive"} className={`flex items-start gap-3 rounded-md border px-4 py-3 text-sm shadow-sm ${successful ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200" : "border-destructive/40 bg-destructive/10 text-destructive"}`}><Icon className="mt-0.5 h-4 w-4 shrink-0" /><div><p className="font-medium">{notice.title}</p><p className="mt-0.5 opacity-90">{notice.detail}</p></div></div>;
}

function TestStatusBadge({ status }: { status: RuntimeConnection["last_test_status"] }) {
  const tone = status === "SUCCEEDED"
    ? "border-transparent bg-[#2ed64c] text-slate-950"
    : status === "FAILED"
      ? "border-transparent bg-[#ff4740] text-slate-950"
      : "border-border/60 bg-muted/40 text-muted-foreground";
  return <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${tone}`}>{status === "NOT_TESTED" ? "Not tested" : status}</span>;
}

export function RuntimeConnectionsPanel() {
  const client = useQueryClient();
  const connections = useQuery({ queryKey: CONNECTIONS_KEY, queryFn: listRuntimeConnections });
  const providers = useQuery({ queryKey: ["runtime-connection-providers"], queryFn: listRuntimeConnectionProviders });
  const [editing, setEditing] = useState<RuntimeConnection | null>(null);
  const [open, setOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [provider, setProvider] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [organization, setOrganization] = useState("");
  const [apiKeyReference, setApiKeyReference] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [scope, setScope] = useState<"ORGANIZATION" | "PROJECT">("ORGANIZATION");
  const [validated, setValidated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [testNotice, setTestNotice] = useState<TestNotice | null>(null);
  const testNoticeTimer = useRef<number | null>(null);

  const create = useMutation({ mutationFn: createRuntimeConnection, onSuccess: async () => { await client.invalidateQueries({ queryKey: CONNECTIONS_KEY }); closeForm(); } });
  const update = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof updateRuntimeConnection>[1] }) => updateRuntimeConnection(id, payload), onSuccess: async () => { await client.invalidateQueries({ queryKey: CONNECTIONS_KEY }); closeForm(); } });
  const validate = useMutation({ mutationFn: validateRuntimeConnection, onSuccess: (result) => { setValidated(true); setMessage(result.message); showTestNotice({ tone: "success", title: "Connection test succeeded", detail: result.message }); }, onError: (reason) => showTestNotice({ tone: "error", title: "Connection test failed", detail: errorMessage(reason) }) });
  const test = useMutation({ mutationFn: testRuntimeConnection, onSuccess: async (connection) => { const succeeded = connection.last_test_status === "SUCCEEDED"; showTestNotice({ tone: succeeded ? "success" : "error", title: `${connection.display_name}: connection test ${succeeded ? "succeeded" : "failed"}`, detail: connection.last_test_message ?? "No test detail was returned." }); await client.invalidateQueries({ queryKey: CONNECTIONS_KEY }); }, onError: (reason) => showTestNotice({ tone: "error", title: "Connection test failed", detail: errorMessage(reason) }) });
  const toggle = useMutation({ mutationFn: ({ id, enabled: nextEnabled }: { id: string; enabled: boolean }) => updateRuntimeConnection(id, { enabled: nextEnabled }), onSuccess: async () => { await client.invalidateQueries({ queryKey: CONNECTIONS_KEY }); } });

  useEffect(() => {
    if (!provider && providers.data?.find((item) => item.allowed)) setProvider(providers.data.find((item) => item.allowed)?.key ?? "");
  }, [provider, providers.data]);

  function resetForm() {
    setEditing(null); setDisplayName(""); setProvider(providers.data?.find((item) => item.allowed)?.key ?? "openai"); setBaseUrl(""); setOrganization(""); setApiKeyReference(""); setEnabled(true); setScope("ORGANIZATION"); setValidated(false); setMessage(null);
  }
  function closeForm() { setOpen(false); resetForm(); }
  function edit(connection: RuntimeConnection) {
    setEditing(connection); setDisplayName(connection.display_name); setProvider(connection.provider); setBaseUrl(String(connection.settings.base_url ?? "")); setOrganization(String(connection.settings.organization ?? "")); setApiKeyReference(connection.secret_refs.api_key ?? ""); setEnabled(connection.enabled); setScope(connection.scope); setValidated(false); setMessage(null); setOpen(true);
  }
  function payload() { return connectionPayload({ displayName, provider, baseUrl, organization, apiKeyReference, enabled, scope }); }
  function showTestNotice(notice: TestNotice) {
    if (testNoticeTimer.current !== null) window.clearTimeout(testNoticeTimer.current);
    setTestNotice(notice);
    testNoticeTimer.current = window.setTimeout(() => { setTestNotice(null); testNoticeTimer.current = null; }, 3_000);
  }
  function submit() {
    const next = payload();
    if (editing) update.mutate({ id: editing.runtime_connection_id, payload: { display_name: next.display_name, settings: next.settings, secret_refs: next.secret_refs, enabled: next.enabled } });
    else create.mutate(next);
  }
  const formError = create.error ?? update.error ?? validate.error;
  const customProvider = provider === "custom";
  const anthropicProvider = provider === "anthropic";

  return <section className="min-w-0 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-2xl font-semibold">Runtime Connections</h2><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Tenant-owned credentials and endpoint configuration for invoking registered models. Platform integration environment variables remain deployment-owned.</p></div><Button onClick={() => { resetForm(); setOpen(true); }}><Plus className="h-4 w-4" />New Runtime Connection</Button></div>
    {testNotice ? <ConnectionTestNotice notice={testNotice} /> : null}
    {open ? <Card><CardContent className="grid gap-4 p-5 md:grid-cols-2"><div className="md:col-span-2"><h3 className="font-semibold">{editing ? "Edit Runtime Connection" : "Create Runtime Connection"}</h3><p className="mt-1 text-xs text-muted-foreground">Use a secret reference, never a raw key. Test validates configuration and secret resolution without exposing secret values.</p></div><label className="grid gap-1 text-sm">Name<Input value={displayName} onChange={(event) => { setDisplayName(event.target.value); setValidated(false); }} placeholder={anthropicProvider ? "Anthropic Development" : "OpenAI Development"} /></label><label className="grid gap-1 text-sm">Provider<select value={provider} disabled={Boolean(editing)} onChange={(event) => { const nextProvider = event.target.value; setProvider(nextProvider); if (nextProvider === "anthropic") setOrganization(""); setValidated(false); }} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70">{(providers.data ?? []).filter((item) => item.allowed || item.key === provider).map((item) => <option key={item.key} value={item.key}>{item.display_name}</option>)}</select></label><label className="grid gap-1 text-sm">Base URL {customProvider ? "(required)" : "(optional)"}<Input value={baseUrl} onChange={(event) => { setBaseUrl(event.target.value); setValidated(false); }} placeholder={customProvider ? "https://runtime.example.com/v1" : "Provider default"} /></label><label className="grid gap-1 text-sm">Organization (optional)<Input value={organization} disabled={anthropicProvider} onChange={(event) => { setOrganization(event.target.value); setValidated(false); }} placeholder="org_..." /></label><label className="grid gap-1 text-sm">API key secret reference {customProvider ? "(optional)" : ""}<Input value={apiKeyReference} onChange={(event) => { setApiKeyReference(event.target.value); setValidated(false); }} placeholder={anthropicProvider ? "env://ANTHROPIC_API_KEY" : "env://OPENAI_DEVELOPMENT_API_KEY"} /></label><label className="grid gap-1 text-sm">Scope<select value={scope} disabled={Boolean(editing)} onChange={(event) => setScope(event.target.value as "ORGANIZATION" | "PROJECT")} className="h-9 rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="ORGANIZATION">Organization — shared by projects</option><option value="PROJECT">Current project</option></select></label><label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" checked={enabled} onChange={(event) => { setEnabled(event.target.checked); setValidated(false); }} />Active <span className="text-xs text-muted-foreground">Active connections must pass validation before saving.</span></label>{message && validated ? <p className="flex items-center gap-2 text-sm text-emerald-700 md:col-span-2 dark:text-emerald-400"><Check className="h-4 w-4" />{message}</p> : null}{formError ? <p className="text-sm text-destructive md:col-span-2">{formError.message}</p> : null}<div className="flex flex-wrap gap-2 md:col-span-2"><Button variant="outline" onClick={() => validate.mutate(payload())} disabled={validate.isPending || !displayName.trim() || !provider}>{validate.isPending ? "Testing…" : "Test Connection"}</Button><Button onClick={submit} disabled={(enabled && !validated) || create.isPending || update.isPending}>{create.isPending || update.isPending ? "Saving…" : editing ? "Save Connection" : "Create Connection"}</Button><Button variant="outline" onClick={closeForm}>Cancel</Button></div></CardContent></Card> : null}
    {connections.isLoading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading runtime connections…</CardContent></Card> : null}
    {connections.error ? <Card><CardContent className="p-6 text-sm text-destructive">Unable to load runtime connections: {connections.error.message}</CardContent></Card> : null}
    {!connections.isLoading && !connections.error ? <Card><CardContent className="p-0">{connections.data?.length ? <div className="divide-y">{connections.data.map((connection) => <div key={connection.runtime_connection_id} className="flex flex-wrap items-center justify-between gap-4 p-4"><div><div className="flex flex-wrap items-center gap-2"><span className="font-medium">{connection.display_name}</span><span className={`rounded border px-2 py-0.5 text-xs ${connection.enabled ? "border-emerald-300 bg-emerald-50 text-emerald-700" : "text-muted-foreground"}`}>{connection.status}</span><span className="rounded border px-2 py-0.5 text-xs">{connection.scope}</span></div><div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"><span>{connection.provider} · {Object.keys(connection.secret_refs).length} secret reference{Object.keys(connection.secret_refs).length === 1 ? "" : "s"}</span><span aria-hidden="true">·</span><span>Test</span><TestStatusBadge status={connection.last_test_status} /></div>{connection.last_test_message ? <p className="mt-1 text-xs text-muted-foreground">{connection.last_test_message}</p> : null}</div><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => test.mutate(connection.runtime_connection_id)} disabled={test.isPending}><RotateCw className="h-3.5 w-3.5" />Test Connection</Button><Button size="sm" variant="outline" onClick={() => edit(connection)}>Edit</Button><Button size="sm" variant="outline" onClick={() => toggle.mutate({ id: connection.runtime_connection_id, enabled: !connection.enabled })} disabled={toggle.isPending}>{connection.enabled ? "Disable" : "Enable"}</Button></div></div>)}</div> : <div className="p-8 text-sm text-muted-foreground">No runtime connections exist for this organization or project. Create one before invoking a registered model.</div>}</CardContent></Card> : null}
  </section>;
}

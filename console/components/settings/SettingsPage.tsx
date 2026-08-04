"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Database, LockKeyhole, RefreshCw, Save, Settings2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { listSettingCategories, listSettings, updateSetting } from "@/lib/api/settings";
import type { PlatformSetting, SettingScope } from "@/types/settings";

export function SettingsPage() {
  const [category, setCategory] = useState("General");
  const [scope, setScope] = useState<SettingScope>("SYSTEM");
  const categories = useQuery({ queryKey: ["setting-categories"], queryFn: listSettingCategories });
  const settings = useQuery({ queryKey: ["settings", category, scope], queryFn: () => listSettings(category, scope) });

  return <div className="mx-auto max-w-7xl space-y-6 p-6 lg:p-10">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><div className="mb-2 flex items-center gap-2 text-sm font-medium text-primary"><Settings2 className="h-4 w-4" />Configuration control plane</div>
        <h1 className="text-4xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Inspect deployment configuration and safely change validated operational settings.</p></div>
      <div className="flex gap-2"><select aria-label="Settings scope" value={scope} onChange={event => setScope(event.target.value as SettingScope)} className="h-10 rounded-md border bg-background px-3 text-sm"><option value="SYSTEM">System</option><option value="ORGANIZATION">Organization</option><option value="PROJECT">Project</option></select>
      <Button variant="outline" onClick={() => settings.refetch()}><RefreshCw className="mr-2 h-4 w-4" />Refresh</Button></div>
    </div>
    <div className="grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
      <nav className="space-y-1 rounded-xl border bg-card p-2 lg:sticky lg:top-4 lg:self-start">
        {(categories.data || []).map(item => <button key={item.key} onClick={() => setCategory(item.name)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition ${category === item.name ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>
          <span>{item.name}</span><span className={`text-xs ${category === item.name ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{item.setting_count}</span>
        </button>)}
      </nav>
      <section className="min-w-0 space-y-4">
        <div><h2 className="text-2xl font-semibold">{category}</h2><p className="mt-1 text-sm text-muted-foreground">Effective values follow Environment → Runtime → Default precedence.</p></div>
        {settings.isLoading ? <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading settings…</CardContent></Card> : null}
        {settings.error ? <Card><CardContent className="p-6 text-sm text-destructive">Unable to load settings: {settings.error.message}</CardContent></Card> : null}
        {(settings.data || []).map(setting => <SettingCard key={`${setting.key}:${scope}`} setting={setting} />)}
      </section>
    </div>
  </div>;
}

function SettingCard({ setting }: { setting: PlatformSetting }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(formatValue(setting.effective_value));
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const update = useMutation({
    mutationFn: () => updateSetting(setting.key, parseDraft(setting, draft), reason, setting.edit_scope, setting.version ?? 0),
    onSuccess: async () => { setSaved(true); setReason(""); await queryClient.invalidateQueries({ queryKey: ["settings"] }); setTimeout(() => setSaved(false), 1800); },
  });
  const sourceTone = useMemo(() => setting.source === "ENVIRONMENT" ? "secondary" : setting.source.startsWith("RUNTIME_") ? "default" : "outline", [setting.source]);

  return <Card className="overflow-hidden"><CardContent className="p-0">
    <div className="grid gap-5 p-5 md:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)]">
      <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{setting.display_name}</h3><Badge variant={sourceTone}>{setting.source}</Badge>{setting.restart_required ? <Badge variant="outline">Restart Required</Badge> : setting.runtime_applied ? <Badge variant="outline">Live consumer</Badge> : setting.mutable ? <Badge variant="outline">Consumer unavailable</Badge> : <Badge variant="outline">Read Only</Badge>}</div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{setting.description}</p>
        <code className="mt-3 block truncate text-xs text-muted-foreground">{setting.key}</code>
        <div className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4"><Meta label="Default" value={formatValue(setting.default)} /><Meta label="Scope" value={setting.edit_scope} /><Meta label="Inherited from" value={setting.inherited_from ?? "Default"} /><Meta label="Version" value={setting.version ? `v${setting.version}` : "New Override"} /></div>
      </div>
      <div className="space-y-3 rounded-lg border bg-muted/25 p-4">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{setting.editable ? <Check className="h-3.5 w-3.5" /> : <LockKeyhole className="h-3.5 w-3.5" />}Effective value</div>
        <SettingInput setting={setting} value={draft} onChange={setDraft} />
        {setting.editable ? <><Input value={reason} onChange={event => setReason(event.target.value)} placeholder="Reason for change" />
          <Button className="w-full" disabled={!reason.trim() || update.isPending} onClick={() => update.mutate()}>{saved ? <Check className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}{saved ? "Saved" : update.isPending ? "Saving…" : "Save runtime value"}</Button></> : <div className="flex items-start gap-2 rounded-md bg-background p-3 text-xs text-muted-foreground"><Database className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{setting.source === "ENVIRONMENT" ? `Controlled by ${setting.environment_variable}.` : "Read-only deployment or system metadata."}</span></div>}
        {!setting.runtime_applied && setting.mutable ? <p className="text-xs text-amber-700">No live runtime consumer is available yet; editing is disabled.</p> : null}
        {update.error ? <p className="text-xs text-destructive">{update.error.message.includes("409") ? "This setting changed. Refresh before saving again." : update.error.message}</p> : null}
      </div>
    </div>
  </CardContent></Card>;
}

function SettingInput({ setting, value, onChange }: { setting: PlatformSetting; value: string; onChange: (value: string) => void }) {
  if (setting.value_type === "BOOLEAN") return <select disabled={!setting.editable} value={value} onChange={event => onChange(event.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-70"><option value="true">Enabled</option><option value="false">Disabled</option></select>;
  if (setting.value_type === "ENUM") return <select disabled={!setting.editable} value={value} onChange={event => onChange(event.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-70">{setting.enum_values.map(item => <option key={item} value={item}>{item}</option>)}</select>;
  if (setting.value_type === "JSON") return <textarea disabled={!setting.editable} value={value} onChange={event => onChange(event.target.value)} className="min-h-24 w-full rounded-md border bg-background p-3 font-mono text-xs disabled:opacity-70" />;
  return <Input disabled={!setting.editable} type={setting.value_type === "INTEGER" || setting.value_type === "FLOAT" ? "number" : "text"} step={setting.value_type === "FLOAT" ? "any" : undefined} value={value} onChange={event => onChange(event.target.value)} />;
}

function Meta({ label, value }: { label: string; value: string }) { return <div><div className="text-muted-foreground">{label}</div><div className="mt-1 truncate font-medium">{value}</div></div>; }
function formatValue(value: unknown): string { return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? ""); }
function parseDraft(setting: PlatformSetting, value: string): unknown { if (setting.value_type === "INTEGER") return Number.parseInt(value, 10); if (setting.value_type === "FLOAT") return Number.parseFloat(value); if (setting.value_type === "BOOLEAN") return value === "true"; if (setting.value_type === "JSON") return JSON.parse(value); return value; }

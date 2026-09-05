"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import type React from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDashboardSummary } from "@/lib/api/dashboard";
import type {
  DashboardMetric,
  PlatformHealthComponent,
  PlatformHealthStatus,
  RecentActivityItem,
} from "@/types/dashboard";

const QUICK_ACTIONS = [
  {
    label: "Run Evaluation",
    href: "/experiments",
    icon: <ClipboardCheck className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "Create Replay",
    href: "/replays/new",
    icon: <Activity className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "Evaluate Decision",
    href: "/decisions",
    icon: <ClipboardCheck className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "Configure Evaluation Provider",
    href: "/assets/providers?new=1",
    icon: <ShieldCheck className="h-4 w-4" />,
    enabled: true,
  },
];

export function HomeDashboard() {
  const query = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: getDashboardSummary,
  });

  return (
    <div className="h-[calc(100vh-4rem)] overflow-y-auto">
      <div className="studio-page flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h1 className="text-3xl font-semibold tracking-normal">Home</h1>
            </div>
            <p className="mt-2 max-w-[760px] text-sm text-muted-foreground">
              Operational overview for the current project.
            </p>
          </div>
        </div>

        {query.isLoading ? (
          <StatePanel label="Loading dashboard..." />
        ) : query.isError ? (
          <ErrorPanel />
        ) : query.data ? (
          <div className="grid w-full gap-6 2xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="flex min-w-0 flex-col gap-6">
              <NeedsAttention signals={query.data.attentionSignals} />

              {query.data.operationalSections.map((section) => (
                <section key={section.key} className="space-y-4">
                  <SectionHeader
                    icon={sectionIcon(section.key)}
                    title={section.label}
                  />
                  <MetricGrid metrics={section.metrics} sectionKey={section.key} />
                </section>
              ))}

              <RecentActivity items={query.data.recentActivity} />
            </div>

            <aside className="flex min-w-0 flex-col gap-6">
              <QuickActions />
              <PlatformHealth
                components={query.data.platformHealth}
                checkedAt={query.data.healthCheckedAt}
              />
            </aside>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
}: {
  icon: React.ReactNode;
  title: string;
}) {
  return (
    <div className="flex items-center gap-2">
      {icon}
      <h2 className="text-lg font-semibold tracking-normal">{title}</h2>
    </div>
  );
}

function sectionIcon(sectionKey: string) {
  if (sectionKey === "evaluation-replay") {
    return <Activity className="h-4 w-4 text-primary" />;
  }
  if (sectionKey === "agent-runtime") {
    return <Gauge className="h-4 w-4 text-primary" />;
  }
  return <ShieldCheck className="h-4 w-4 text-primary" />;
}

function MetricGrid({
  metrics,
  sectionKey,
}: {
  metrics: DashboardMetric[];
  sectionKey: string;
}) {
  const toneClasses = sectionKey === "agent-runtime"
    ? ["bg-card", "border-blue-500/30 bg-blue-500/5", "border-orange-500/30 bg-orange-500/5", "border-primary/30 bg-primary/5"]
    : ["bg-card", "border-primary/30 bg-primary/5", "border-emerald-500/30 bg-emerald-500/5", "border-blue-500/30 bg-blue-500/5"];
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric, index) => (
        <Card key={metric.label} className={`min-h-[126px] ${toneClasses[index % toneClasses.length]}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-muted-foreground">
              {metric.label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold tracking-normal">
              {metric.value.toLocaleString()}
            </div>
            {metric.description ? (
              <p className="mt-3 text-sm leading-5 text-muted-foreground">
                {metric.description}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function NeedsAttention({
  signals,
}: {
  signals: { label: string; value: number; detail: string }[];
}) {
  return (
    <section className="space-y-4">
      <SectionHeader
        icon={<AlertCircle className="h-4 w-4 text-primary" />}
        title="Needs Attention"
      />
      <Card className={signals.length ? "border-amber-400/50 bg-card" : "border-emerald-500/30 bg-emerald-500/5"}>
        <CardContent className="p-4">
          {signals.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {signals.map((signal) => {
                const tone = attentionTone(signal.label);
                return <div key={signal.label} className={`flex items-start justify-between gap-3 rounded-md border bg-card px-3 py-2.5 transition-colors ${tone.card}`}>
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{signal.label}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{signal.detail}</div>
                  </div>
                  <span className={`inline-flex min-w-9 items-center justify-center rounded-md border px-2 py-1 text-lg font-semibold tabular-nums ${tone.count}`}>{signal.value}</span>
                </div>;
              })}
            </div>
          ) : (
            <div>
              <div className="font-medium text-emerald-800 dark:text-emerald-200">No operational issues require attention.</div>
              <p className="mt-1 text-sm text-muted-foreground">Jobs, runtime evidence, replay work, and ontology synchronization are clear.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function attentionTone(label: string) {
  if (label.includes("Runtime") || label.includes("Jobs")) {
    return { card: "border-rose-400/50 hover:bg-rose-500/5", count: "border-rose-200 bg-rose-300 text-slate-950" };
  }
  if (label.includes("Evaluation")) {
    return { card: "border-orange-400/50 hover:bg-orange-500/5", count: "border-orange-200 bg-orange-300 text-slate-950" };
  }
  if (label.includes("Replay")) {
    return { card: "border-amber-400/50 hover:bg-amber-500/5", count: "border-amber-200 bg-amber-300 text-slate-950" };
  }
  if (label.includes("Causal")) {
    return { card: "border-violet-400/50 hover:bg-violet-500/5", count: "border-violet-200 bg-violet-300 text-slate-950" };
  }
  return { card: "border-amber-400/50 hover:bg-amber-500/5", count: "border-amber-200 bg-amber-300 text-slate-950" };
}

function PlatformHealth({
  components,
  checkedAt,
}: {
  components: PlatformHealthComponent[];
  checkedAt: string | null;
}) {
  const statusOrder: Record<PlatformHealthStatus, number> = {
    Unavailable: 0,
    Warning: 1,
    Unknown: 2,
    "IN MEMORY": 3,
    Healthy: 4,
  };
  const orderedComponents = [...components].sort(
    (left, right) => statusOrder[left.status] - statusOrder[right.status],
  );
  return (
    <section className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <SectionHeader
          icon={<CheckCircle2 className="h-4 w-4 text-primary" />}
          title="Platform Health"
        />
        {checkedAt ? <span className="text-xs text-muted-foreground">Last checked {formatTimestamp(checkedAt)}</span> : null}
      </div>
      <Card>
        <CardContent className="p-0">
          <div className="divide-y">
            {orderedComponents.map((component) => (
              <div
                key={component.component}
                className="grid gap-3 px-4 py-3 sm:grid-cols-[1fr_auto]"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {component.component}
                  </div>
                  {component.detail ? (
                    <div className="mt-1 text-sm text-muted-foreground">
                      {component.detail}
                    </div>
                  ) : null}
                  {component.component === "Ontology Synchronizer" &&
                  component.status === "Warning" ? (
                    <Link
                      href="/graph/synchronization"
                      className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                      Review sync events
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  ) : null}
                </div>
                <HealthBadge status={component.status} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function HealthBadge({ status }: { status: PlatformHealthStatus }) {
  const classes: Record<PlatformHealthStatus, string> = {
    Healthy: "border-emerald-200 bg-emerald-50 text-emerald-700",
    Warning: "border-amber-200 bg-amber-50 text-amber-700",
    Unavailable: "border-red-200 bg-red-50 text-red-700",
    Unknown: "border-slate-200 bg-slate-50 text-slate-600",
    "IN MEMORY": "border-sky-200 bg-sky-50 text-sky-700",
  };

  return (
    <span
      className={`inline-flex h-7 items-center justify-center rounded-md border px-2 text-xs font-medium ${classes[status]}`}
    >
      {status}
    </span>
  );
}

function RecentActivity({ items }: { items: RecentActivityItem[] }) {
  return (
    <section className="space-y-4">
      <SectionHeader
        icon={<BriefcaseBusiness className="h-4 w-4 text-primary" />}
        title="Recent Activity"
      />
      <Card>
        <CardContent className="p-0">
          {items.length ? (
            <div className="divide-y">
              {items.map((item) => (
                <div
                  key={`${item.timestamp}-${item.resource}-${item.action}`}
                  className="grid gap-3 px-4 py-3 lg:grid-cols-[150px_minmax(0,1fr)_180px_110px]"
                >
                  <ListField
                    label="Timestamp"
                    value={formatTimestamp(item.timestamp)}
                  />
                  <ListField label="Resource" value={item.resource} mono />
                  <ListField label="Action" value={item.action} />
                  <ListField label="Status" value={item.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="px-4 py-8 text-sm text-muted-foreground">
              No governance activity has been recorded yet.
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function QuickActions() {
  return (
    <section className="space-y-4">
      <SectionHeader
        icon={<ArrowRight className="h-4 w-4 text-primary" />}
        title="Quick Actions"
      />
      <Card>
        <CardContent className="grid gap-2 p-4">
          {QUICK_ACTIONS.map((action) =>
            action.enabled ? (
              <Button
                key={action.label}
                asChild
                variant="outline"
                className="justify-between"
              >
                <Link href={action.href}>
                  <span className="flex items-center gap-2">
                    {action.icon}
                    {action.label}
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            ) : (
              <Button
                key={action.label}
                type="button"
                variant="outline"
                className="justify-between"
                disabled
                title={`${action.label} will be available later`}
              >
                <span className="flex items-center gap-2">
                  {action.icon}
                  {action.label}
                </span>
                <ArrowRight className="h-4 w-4" />
              </Button>
            ),
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function ListField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-1 truncate text-sm text-foreground ${
          mono ? "font-mono" : ""
        }`}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function StatePanel({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {label}
      </CardContent>
    </Card>
  );
}

function ErrorPanel() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-6 text-sm text-destructive">
        <AlertCircle className="h-4 w-4" />
        Dashboard summary is unavailable.
      </CardContent>
    </Card>
  );
}

function formatTimestamp(timestamp: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

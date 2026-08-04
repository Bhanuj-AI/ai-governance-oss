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
  Network,
  ListRestart,
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
    label: "Configure Evaluation Provider",
    href: "/assets/providers?new=1",
    icon: <ShieldCheck className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "Evaluate Decision",
    href: "/decisions",
    icon: <ClipboardCheck className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "View Ontology",
    href: "/graph",
    icon: <Network className="h-4 w-4" />,
    enabled: true,
  },
  {
    label: "Sync Events",
    href: "/graph/synchronization",
    icon: <ListRestart className="h-4 w-4" />,
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
      <div className="flex w-full flex-col gap-6 px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <h1 className="text-3xl font-semibold tracking-normal">Home</h1>
            </div>
            <p className="mt-2 max-w-[760px] text-sm text-muted-foreground">
              Operational overview for governance decisions, platform activity,
              system health and recent changes.
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
              <section className="space-y-4">
                <SectionHeader
                  icon={<Gauge className="h-4 w-4 text-primary" />}
                  title="Governance Overview"
                />
                <MetricGrid metrics={query.data.governanceStatistics} />
              </section>

              <section className="space-y-4">
                <SectionHeader
                  icon={<Network className="h-4 w-4 text-primary" />}
                  title="Ontology Projection"
                />
                <MetricGrid metrics={query.data.ontologyProjectionStatistics} />
              </section>

              <section className="space-y-4">
                <SectionHeader
                  icon={<Activity className="h-4 w-4 text-primary" />}
                  title="Platform Activity"
                />
                <MetricGrid metrics={query.data.platformStatistics} />
              </section>

              <RecentActivity items={query.data.recentActivity} />
            </div>

            <aside className="flex min-w-0 flex-col gap-6">
              <QuickActions />
              <PlatformHealth components={query.data.platformHealth} />
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

function MetricGrid({ metrics }: { metrics: DashboardMetric[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map((metric) => (
        <Card key={metric.label} className="min-h-[126px]">
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

function PlatformHealth({
  components,
}: {
  components: PlatformHealthComponent[];
}) {
  return (
    <section className="space-y-4">
      <SectionHeader
        icon={<CheckCircle2 className="h-4 w-4 text-primary" />}
        title="Platform Health"
      />
      <Card>
        <CardContent className="p-0">
          <div className="divide-y">
            {components.map((component) => (
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

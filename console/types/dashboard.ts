export type DashboardMetricDto = {
  label: string;
  value: number;
  description: string | null;
};

export type PlatformHealthStatus =
  | "Healthy"
  | "Warning"
  | "Unavailable"
  | "Unknown"
  | "IN MEMORY";

export type PlatformHealthComponentDto = {
  component: string;
  status: PlatformHealthStatus;
  detail: string | null;
};

export type RecentActivityItemDto = {
  timestamp: string;
  resource: string;
  action: string;
  status: string;
};

export type DashboardMetricSectionDto = {
  key: string;
  label: string;
  metrics: DashboardMetricDto[];
};

export type DashboardAttentionSignalDto = {
  label: string;
  value: number;
  detail: string;
};

export type DashboardSummaryDto = {
  governance_statistics: DashboardMetricDto[];
  ontology_projection_statistics: DashboardMetricDto[];
  platform_statistics: DashboardMetricDto[];
  platform_health: PlatformHealthComponentDto[];
  recent_activity: RecentActivityItemDto[];
  operational_sections?: DashboardMetricSectionDto[];
  attention_signals?: DashboardAttentionSignalDto[];
  health_checked_at?: string | null;
};

export type DashboardMetric = {
  label: string;
  value: number;
  description: string | null;
};

export type PlatformHealthComponent = {
  component: string;
  status: PlatformHealthStatus;
  detail: string | null;
};

export type RecentActivityItem = {
  timestamp: string;
  resource: string;
  action: string;
  status: string;
};

export type DashboardMetricSection = {
  key: string;
  label: string;
  metrics: DashboardMetric[];
};

export type DashboardAttentionSignal = {
  label: string;
  value: number;
  detail: string;
};

export type DashboardSummary = {
  governanceStatistics: DashboardMetric[];
  ontologyProjectionStatistics: DashboardMetric[];
  platformStatistics: DashboardMetric[];
  platformHealth: PlatformHealthComponent[];
  recentActivity: RecentActivityItem[];
  operationalSections: DashboardMetricSection[];
  attentionSignals: DashboardAttentionSignal[];
  healthCheckedAt: string | null;
};

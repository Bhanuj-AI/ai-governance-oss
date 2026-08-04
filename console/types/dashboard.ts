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

export type DashboardSummaryDto = {
  governance_statistics: DashboardMetricDto[];
  ontology_projection_statistics: DashboardMetricDto[];
  platform_statistics: DashboardMetricDto[];
  platform_health: PlatformHealthComponentDto[];
  recent_activity: RecentActivityItemDto[];
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

export type DashboardSummary = {
  governanceStatistics: DashboardMetric[];
  ontologyProjectionStatistics: DashboardMetric[];
  platformStatistics: DashboardMetric[];
  platformHealth: PlatformHealthComponent[];
  recentActivity: RecentActivityItem[];
};

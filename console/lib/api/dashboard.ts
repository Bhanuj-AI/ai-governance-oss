import { kavachRequest } from "@/lib/api/client";
import type {
  DashboardMetricDto,
  DashboardSummary,
  DashboardSummaryDto,
  PlatformHealthComponentDto,
  RecentActivityItemDto,
} from "@/types/dashboard";

export async function getDashboardSummary() {
  const dto = await kavachRequest<DashboardSummaryDto>("/api/v1/dashboard");
  return mapDashboardSummary(dto);
}

function mapDashboardSummary(dto: DashboardSummaryDto): DashboardSummary {
  return {
    governanceStatistics: dto.governance_statistics.map(mapMetric),
    ontologyProjectionStatistics: dto.ontology_projection_statistics.map(mapMetric),
    platformStatistics: dto.platform_statistics.map(mapMetric),
    platformHealth: dto.platform_health.map(mapHealthComponent),
    recentActivity: dto.recent_activity.map(mapRecentActivity),
  };
}

function mapMetric(dto: DashboardMetricDto) {
  return {
    label: dto.label,
    value: dto.value,
    description: dto.description,
  };
}

function mapHealthComponent(dto: PlatformHealthComponentDto) {
  return {
    component: dto.component,
    status: dto.status,
    detail: dto.detail,
  };
}

function mapRecentActivity(dto: RecentActivityItemDto) {
  return {
    timestamp: dto.timestamp,
    resource: dto.resource,
    action: dto.action,
    status: dto.status,
  };
}

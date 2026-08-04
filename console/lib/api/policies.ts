import {
  kavachJsonRequest,
  kavachRequest,
  type QueryParams,
} from "@/lib/api/client";
import type {
  CreatePolicyRequest,
  CreatePolicyVersionRequest,
  JsonObject,
  PolicyCondition,
  PolicyConditionDto,
  PolicyDetail,
  PolicyDetailDto,
  PolicyListItem,
  PolicyListItemDto,
  PolicyRule,
  PolicyRuleDto,
  PolicySchema,
  PolicySchemaDto,
  PolicySchemaField,
  PolicySchemaFieldDto,
  PolicySchemaTargetType,
  PolicySchemaTargetTypeDto,
  PolicySimulation,
  PolicySimulationDto,
  PolicyTraceItem,
  PolicyTraceItemDto,
  PolicyVersion,
  PolicyVersionDto,
  PolicyVersionSummary,
  PolicyVersionSummaryDto,
  UpdateDraftPolicyVersionRequest,
} from "@/types/policy";

export async function getPolicySchema() {
  const dto = await kavachRequest<PolicySchemaDto>("/api/v1/policy-schema");
  return mapPolicySchema(dto);
}

export async function getPolicies(params?: QueryParams) {
  const dto = await kavachRequest<PolicyListItemDto[]>(
    "/api/v1/policies",
    params,
  );
  return dto.map(mapPolicyListItem);
}

export async function createPolicy(request: CreatePolicyRequest) {
  const dto = await kavachJsonRequest<PolicyDetailDto, CreatePolicyRequest>(
    "/api/v1/policies",
    { method: "POST", body: request },
  );
  return mapPolicyDetail(dto);
}

export async function getPolicy(policyId: string) {
  const dto = await kavachRequest<PolicyDetailDto>(
    `/api/v1/policies/${encodeURIComponent(policyId)}`,
  );
  return mapPolicyDetail(dto);
}

export async function getPolicyVersion(policyId: string, version: string) {
  const dto = await kavachRequest<PolicyVersionDto>(
    `/api/v1/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version)}`,
  );
  return mapPolicyVersion(dto);
}

export async function createPolicyVersion(
  policyId: string,
  request: CreatePolicyVersionRequest,
) {
  const dto = await kavachJsonRequest<
    PolicyDetailDto,
    CreatePolicyVersionRequest
  >(`/api/v1/policies/${encodeURIComponent(policyId)}/versions`, {
    method: "POST",
    body: request,
  });
  return mapPolicyDetail(dto);
}

export async function updateDraftPolicyVersion(
  policyId: string,
  version: string,
  request: UpdateDraftPolicyVersionRequest,
) {
  const dto = await kavachJsonRequest<
    PolicyDetailDto,
    UpdateDraftPolicyVersionRequest
  >(
    `/api/v1/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version)}/draft`,
    { method: "PUT", body: request },
  );
  return mapPolicyDetail(dto);
}

export async function activatePolicyVersion(
  policyId: string,
  version: string,
  activatedBy: string,
) {
  const dto = await kavachJsonRequest<
    PolicyDetailDto,
    { activated_by: string }
  >(
    `/api/v1/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version)}/activate`,
    { method: "POST", body: { activated_by: activatedBy } },
  );
  return mapPolicyDetail(dto);
}

export async function archivePolicyVersion(
  policyId: string,
  version: string,
  archivedBy: string,
) {
  const dto = await kavachJsonRequest<PolicyDetailDto, { archived_by: string }>(
    `/api/v1/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version)}/archive`,
    { method: "POST", body: { archived_by: archivedBy } },
  );
  return mapPolicyDetail(dto);
}

export async function simulatePolicyVersion(
  policyId: string,
  version: string,
  request: {
    target_type: string;
    target_id: string;
    evidence: JsonObject;
    metadata: JsonObject;
  },
) {
  const dto = await kavachJsonRequest<PolicySimulationDto, typeof request>(
    `/api/v1/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version)}/simulate`,
    { method: "POST", body: request },
  );
  return mapPolicySimulation(dto);
}

export function mapPolicyDetail(dto: PolicyDetailDto): PolicyDetail {
  return {
    policyId: dto.policy_id,
    name: dto.name,
    description: dto.description,
    organizationId: dto.organization_id,
    projectId: dto.project_id,
    category: dto.category,
    owner: dto.owner,
    createdBy: dto.created_by,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
    activeVersion: dto.active_version
      ? mapPolicyVersion(dto.active_version)
      : null,
    draftVersion: dto.draft_version ? mapPolicyVersion(dto.draft_version) : null,
    versions: dto.versions.map(mapPolicyVersionSummary),
    metadata: dto.metadata,
  };
}

export function mapPolicyVersion(dto: PolicyVersionDto): PolicyVersion {
  return {
    policyId: dto.policy_id,
    version: dto.version,
    status: dto.status,
    targetTypes: dto.target_types,
    rules: dto.rules.map(mapPolicyRule),
    createdBy: dto.created_by,
    createdAt: dto.created_at,
    activatedAt: dto.activated_at,
    deprecatedAt: dto.deprecated_at,
    archivedAt: dto.archived_at,
    metadata: dto.metadata,
  };
}

function mapPolicyListItem(dto: PolicyListItemDto): PolicyListItem {
  return {
    policyId: dto.policy_id,
    name: dto.name,
    description: dto.description,
    organizationId: dto.organization_id,
    projectId: dto.project_id,
    category: dto.category,
    owner: dto.owner,
    status: dto.status,
    activeVersion: dto.active_version,
    draftVersion: dto.draft_version,
    targetTypes: dto.target_types,
    highestPriority: dto.highest_priority,
    primaryEffect: dto.primary_effect,
    updatedAt: dto.updated_at,
    createdAt: dto.created_at,
  };
}

function mapPolicyVersionSummary(
  dto: PolicyVersionSummaryDto,
): PolicyVersionSummary {
  return {
    policyId: dto.policy_id,
    version: dto.version,
    status: dto.status,
    targetTypes: dto.target_types,
    createdBy: dto.created_by,
    createdAt: dto.created_at,
    activatedAt: dto.activated_at,
    deprecatedAt: dto.deprecated_at,
    archivedAt: dto.archived_at,
  };
}

function mapPolicyRule(dto: PolicyRuleDto): PolicyRule {
  return {
    ruleId: dto.rule_id,
    name: dto.name,
    priority: dto.priority,
    effect: dto.effect,
    reasonTemplate: dto.reason_template,
    severity: dto.severity,
    conditions: dto.conditions.map(mapPolicyCondition),
    metadata: dto.metadata,
  };
}

function mapPolicyCondition(dto: PolicyConditionDto): PolicyCondition {
  return {
    fieldPath: dto.field_path,
    operator: dto.operator,
    expectedValue: dto.expected_value,
    metadata: dto.metadata,
  };
}

function mapPolicySchema(dto: PolicySchemaDto): PolicySchema {
  return {
    targetTypes: dto.target_types.map(mapSchemaTargetType),
    operators: dto.operators,
    effects: dto.effects,
    statuses: dto.statuses,
    categories: dto.categories,
    severities: dto.severities,
  };
}

function mapSchemaTargetType(
  dto: PolicySchemaTargetTypeDto,
): PolicySchemaTargetType {
  return {
    value: dto.value,
    label: dto.label,
    description: dto.description,
    fields: dto.fields.map(mapSchemaField),
  };
}

function mapSchemaField(dto: PolicySchemaFieldDto): PolicySchemaField {
  return {
    fieldPath: dto.field_path,
    label: dto.label,
    valueType: dto.value_type,
    supportedOperators: dto.supported_operators,
    allowedValues: dto.allowed_values,
    description: dto.description,
  };
}

function mapPolicySimulation(dto: PolicySimulationDto): PolicySimulation {
  return {
    policyId: dto.policy_id,
    version: dto.version,
    targetType: dto.target_type,
    targetId: dto.target_id,
    matched: dto.matched,
    matchedRuleId: dto.matched_rule_id,
    effect: dto.effect,
    reason: dto.reason,
    matchedConditions: dto.matched_conditions.map(mapPolicyCondition),
    unmatchedConditions: dto.unmatched_conditions.map(mapPolicyCondition),
    evaluationTrace: dto.evaluation_trace.map(mapTraceItem),
    metadata: dto.metadata,
  };
}

function mapTraceItem(dto: PolicyTraceItemDto): PolicyTraceItem {
  return {
    ruleId: dto.rule_id,
    ruleName: dto.rule_name,
    conditionFieldPath: dto.condition_field_path,
    operator: dto.operator,
    expectedValue: dto.expected_value,
    actualValue: dto.actual_value,
    matched: dto.matched,
    reason: dto.reason,
  };
}

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonObject = Record<string, JsonValue>;

export type PolicyConditionDto = {
  field_path: string;
  operator: string;
  expected_value: JsonValue | null;
  metadata: JsonObject;
};

export type PolicyRuleDto = {
  rule_id: string;
  name: string;
  priority: number;
  effect: string;
  reason_template: string;
  severity: string | null;
  conditions: PolicyConditionDto[];
  metadata: JsonObject;
};

export type PolicyVersionDto = {
  policy_id: string;
  version: string;
  status: string;
  target_types: string[];
  rules: PolicyRuleDto[];
  created_by: string;
  created_at: string;
  activated_at: string | null;
  deprecated_at: string | null;
  archived_at: string | null;
  metadata: JsonObject;
};

export type PolicyVersionSummaryDto = Omit<PolicyVersionDto, "rules" | "metadata">;

export type PolicyListItemDto = {
  policy_id: string;
  name: string;
  description: string | null;
  organization_id: string;
  project_id: string;
  category: string;
  owner: string;
  status: string;
  active_version: string | null;
  draft_version: string | null;
  target_types: string[];
  highest_priority: number | null;
  primary_effect: string | null;
  updated_at: string;
  created_at: string;
};

export type PolicyDetailDto = {
  policy_id: string;
  name: string;
  description: string | null;
  organization_id: string;
  project_id: string;
  category: string;
  owner: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  active_version: PolicyVersionDto | null;
  draft_version: PolicyVersionDto | null;
  versions: PolicyVersionSummaryDto[];
  metadata: JsonObject;
};

export type PolicySchemaFieldDto = {
  field_path: string;
  label: string;
  value_type: string;
  supported_operators: string[];
  allowed_values: JsonValue[] | null;
  description: string | null;
};

export type PolicySchemaTargetTypeDto = {
  value: string;
  label: string;
  description: string | null;
  fields: PolicySchemaFieldDto[];
};

export type PolicySchemaDto = {
  target_types: PolicySchemaTargetTypeDto[];
  operators: string[];
  effects: string[];
  statuses: string[];
  categories: string[];
  severities: string[];
};

export type PolicyTraceItemDto = {
  rule_id: string;
  rule_name: string;
  condition_field_path: string;
  operator: string;
  expected_value: JsonValue | null;
  actual_value: JsonValue | null;
  matched: boolean;
  reason: string | null;
};

export type PolicySimulationDto = {
  policy_id: string;
  version: string;
  target_type: string;
  target_id: string;
  matched: boolean;
  matched_rule_id: string | null;
  effect: string;
  reason: string;
  matched_conditions: PolicyConditionDto[];
  unmatched_conditions: PolicyConditionDto[];
  evaluation_trace: PolicyTraceItemDto[];
  metadata: JsonObject;
};

export type PolicyCondition = {
  fieldPath: string;
  operator: string;
  expectedValue: JsonValue | null;
  metadata: JsonObject;
};

export type PolicyRule = {
  ruleId: string;
  name: string;
  priority: number;
  effect: string;
  reasonTemplate: string;
  severity: string | null;
  conditions: PolicyCondition[];
  metadata: JsonObject;
};

export type PolicyVersion = {
  policyId: string;
  version: string;
  status: string;
  targetTypes: string[];
  rules: PolicyRule[];
  createdBy: string;
  createdAt: string;
  activatedAt: string | null;
  deprecatedAt: string | null;
  archivedAt: string | null;
  metadata: JsonObject;
};

export type PolicyVersionSummary = Omit<PolicyVersion, "rules" | "metadata">;

export type PolicyListItem = {
  policyId: string;
  name: string;
  description: string | null;
  organizationId: string;
  projectId: string;
  category: string;
  owner: string;
  status: string;
  activeVersion: string | null;
  draftVersion: string | null;
  targetTypes: string[];
  highestPriority: number | null;
  primaryEffect: string | null;
  updatedAt: string;
  createdAt: string;
};

export type PolicyDetail = {
  policyId: string;
  name: string;
  description: string | null;
  organizationId: string;
  projectId: string;
  category: string;
  owner: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  activeVersion: PolicyVersion | null;
  draftVersion: PolicyVersion | null;
  versions: PolicyVersionSummary[];
  metadata: JsonObject;
};

export type PolicySchemaField = {
  fieldPath: string;
  label: string;
  valueType: string;
  supportedOperators: string[];
  allowedValues: JsonValue[] | null;
  description: string | null;
};

export type PolicySchemaTargetType = {
  value: string;
  label: string;
  description: string | null;
  fields: PolicySchemaField[];
};

export type PolicySchema = {
  targetTypes: PolicySchemaTargetType[];
  operators: string[];
  effects: string[];
  statuses: string[];
  categories: string[];
  severities: string[];
};

export type PolicyTraceItem = {
  ruleId: string;
  ruleName: string;
  conditionFieldPath: string;
  operator: string;
  expectedValue: JsonValue | null;
  actualValue: JsonValue | null;
  matched: boolean;
  reason: string | null;
};

export type PolicySimulation = {
  policyId: string;
  version: string;
  targetType: string;
  targetId: string;
  matched: boolean;
  matchedRuleId: string | null;
  effect: string;
  reason: string;
  matchedConditions: PolicyCondition[];
  unmatchedConditions: PolicyCondition[];
  evaluationTrace: PolicyTraceItem[];
  metadata: JsonObject;
};

export type PolicyRuleInput = {
  rule_id: string;
  name: string;
  conditions: PolicyConditionInput[];
  effect: string;
  reason_template: string;
  priority: number;
  severity: string | null;
  metadata: JsonObject;
};

export type PolicyConditionInput = {
  field_path: string;
  operator: string;
  expected_value: JsonValue | null;
  metadata: JsonObject;
};

export type CreatePolicyRequest = {
  name: string;
  description: string | null;
  organization_id: string;
  project_id: string;
  category: string;
  owner: string;
  created_by: string;
  target_types: string[];
  rules: PolicyRuleInput[];
  metadata: JsonObject;
};

export type CreatePolicyVersionRequest = {
  base_version: string | null;
  target_types: string[];
  rules: PolicyRuleInput[];
  created_by: string;
  metadata: JsonObject;
};

export type UpdateDraftPolicyVersionRequest = {
  target_types: string[];
  rules: PolicyRuleInput[];
  updated_by: string;
  metadata: JsonObject;
};

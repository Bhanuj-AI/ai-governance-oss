export type SettingValueType = "STRING" | "INTEGER" | "FLOAT" | "BOOLEAN" | "DURATION" | "ENUM" | "JSON";

export type PlatformSetting = {
  key: string;
  display_name: string;
  description: string;
  category: string;
  value_type: SettingValueType;
  value: unknown;
  effective_value: unknown;
  source: "ENVIRONMENT" | "RUNTIME_PROJECT" | "RUNTIME_ORGANIZATION" | "RUNTIME_SYSTEM" | "DEFAULT";
  default: unknown;
  mutable: boolean;
  editable: boolean;
  sensitive: boolean;
  restart_required: boolean;
  runtime_applied: boolean;
  allowed_scopes: SettingScope[];
  edit_scope: SettingScope;
  edit_scope_id: string;
  inherited_from: SettingScope | null;
  environment_variable: string | null;
  enum_values: string[];
  version: number | null;
  updated_by: string | null;
  updated_at: string | null;
};

export type SettingCategory = { name: string; key: string; setting_count: number };
export type SettingScope = "SYSTEM" | "ORGANIZATION" | "PROJECT";

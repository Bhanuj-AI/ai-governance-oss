import { kavachJsonRequest, kavachRequest } from "./client";
import type { PlatformSetting, SettingCategory, SettingScope } from "@/types/settings";

export const listSettings = (category: string, scope: SettingScope) =>
  kavachRequest<PlatformSetting[]>("/api/v1/settings", { category, scope });

export const listSettingCategories = () =>
  kavachRequest<SettingCategory[]>("/api/v1/settings/categories");

export const updateSetting = (key: string, value: unknown, reason: string, scope: SettingScope, expectedVersion: number) =>
  kavachJsonRequest<PlatformSetting, { value: unknown; reason: string; scope: SettingScope; expected_version: number }>(
    `/api/v1/settings/${encodeURIComponent(key)}`,
    { method: "PATCH", body: { value, reason, scope, expected_version: expectedVersion } },
  );

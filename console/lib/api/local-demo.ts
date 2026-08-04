import { kavachJsonRequest } from "@/lib/api/client";

type DemoSeedResponse = {
  seeded: boolean;
  decision_ids: string[];
};

/** Seed the idempotent, full workflow fixture used by the local Studio mentor. */
export const seedLocalDemoData = () =>
  kavachJsonRequest<DemoSeedResponse, undefined>("/api/v1/local/demo/seed", {
    method: "POST",
  });

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Archive,
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  CirclePlay,
  FilePenLine,
  Filter,
  GitBranch,
  History,
  ListChecks,
  Plus,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  activatePolicyVersion,
  archivePolicyVersion,
  createPolicy,
  createPolicyVersion,
  getPolicies,
  getPolicy,
  getPolicySchema,
  getPolicyVersion,
  simulatePolicyVersion,
  updateDraftPolicyVersion,
} from "@/lib/api/policies";
import { AIGovernanceApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils/cn";
import type {
  CreatePolicyRequest,
  JsonObject,
  JsonValue,
  PolicyCondition,
  PolicyConditionInput,
  PolicyDetail,
  PolicyListItem,
  PolicyRule,
  PolicyRuleInput,
  PolicySchema,
  PolicySchemaField,
  PolicySimulation,
  PolicyVersion,
  UpdateDraftPolicyVersionRequest,
} from "@/types/policy";

const DEFAULT_ACTOR = "studio-admin";
const DEFAULT_ORGANIZATION = "Acme Corporation";
const DEFAULT_PROJECT = "Insurance Platform";
const POLICY_PAGE_SIZE = 10;

type EditorCondition = {
  id: string;
  fieldPath: string;
  operator: string;
  expectedValue: string;
};

type EditorRule = {
  id: string;
  ruleId: string;
  name: string;
  priority: string;
  effect: string;
  severity: string;
  reasonTemplate: string;
  conditions: EditorCondition[];
};

type EditorState = {
  targetTypes: string[];
  rules: EditorRule[];
  metadataJson: string;
};

type DefinitionState = {
  name: string;
  description: string;
  organizationId: string;
  projectId: string;
  category: string;
  owner: string;
  actor: string;
  metadataJson: string;
};

type PolicyFilters = {
  search: string;
  project: string;
  status: string;
  category: string;
  targetType: string;
  effect: string;
  owner: string;
};

const EMPTY_POLICY_FILTERS: PolicyFilters = {
  search: "",
  project: "",
  status: "",
  category: "",
  targetType: "",
  effect: "",
  owner: "",
};

export function PolicyListPage() {
  const [filterInput, setFilterInput] =
    useState<PolicyFilters>(EMPTY_POLICY_FILTERS);
  const [filters, setFilters] =
    useState<PolicyFilters>(EMPTY_POLICY_FILTERS);
  const [page, setPage] = useState(0);
  const schemaQuery = useQuery({
    queryKey: ["policy-schema"],
    queryFn: getPolicySchema,
  });
  const policyQuery = useQuery({
    queryKey: ["policies", filters, page],
    queryFn: () =>
      getPolicies({
        search: filters.search,
        status: filters.status,
        category: filters.category,
        target_type: filters.targetType,
        project_id: filters.project,
        effect: filters.effect,
        owner: filters.owner,
        limit: POLICY_PAGE_SIZE + 1,
        offset: page * POLICY_PAGE_SIZE,
      }),
  });

  const fetchedPolicies = policyQuery.data ?? [];
  const policies = fetchedPolicies.slice(0, POLICY_PAGE_SIZE);
  const hasNextPage = fetchedPolicies.length > POLICY_PAGE_SIZE;
  const projects = unique([
    DEFAULT_PROJECT,
    filters.project,
    filterInput.project,
    ...fetchedPolicies.map((policy) => policy.projectId),
  ]);
  const owners = unique([
    filters.owner,
    filterInput.owner,
    ...fetchedPolicies.map((policy) => policy.owner),
  ]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters({
      ...filterInput,
      search: filterInput.search.trim(),
    });
    setPage(0);
  }

  function resetFilters() {
    setFilterInput(EMPTY_POLICY_FILTERS);
    setFilters(EMPTY_POLICY_FILTERS);
    setPage(0);
  }

  return (
    <PolicyFrame
      title="Policies"
      icon={<SlidersHorizontal className="h-5 w-5 text-primary" />}
      actions={
        <Button asChild>
          <Link href="/policies/new">
            <Plus className="h-4 w-4" />
            Create Policy
          </Link>
        </Button>
      }
    >
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-primary" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 md:grid-cols-2 xl:grid-cols-[1.6fr_repeat(5,1fr)]"
            onSubmit={handleSearch}
          >
            <div>
              <LabelText>Search</LabelText>
              <div className="mt-1 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={filterInput.search}
                    onChange={(event) =>
                      setFilterInput({
                        ...filterInput,
                        search: event.target.value,
                      })
                    }
                    className="pl-9"
                    placeholder="Policy ID, name, owner"
                  />
                </div>
                <Button type="submit" variant="outline">
                  <Search className="h-4 w-4" />
                  Search
                </Button>
                <Button type="button" variant="ghost" onClick={resetFilters}>
                  Reset
                </Button>
              </div>
            </div>
            <SelectBox
              label="Project"
              value={filterInput.project}
              onChange={(project) => setFilterInput({ ...filterInput, project })}
              options={projects}
              includeAny
            />
            <SelectBox
              label="Status"
              value={filterInput.status}
              onChange={(status) => setFilterInput({ ...filterInput, status })}
              options={schemaQuery.data?.statuses ?? []}
              includeAny
            />
            <SelectBox
              label="Category"
              value={filterInput.category}
              onChange={(category) => setFilterInput({ ...filterInput, category })}
              options={schemaQuery.data?.categories ?? []}
              includeAny
            />
            <SelectBox
              label="Target"
              value={filterInput.targetType}
              onChange={(targetType) =>
                setFilterInput({ ...filterInput, targetType })
              }
              options={schemaQuery.data?.targetTypes.map((item) => item.value) ?? []}
              includeAny
            />
            <SelectBox
              label="Effect"
              value={filterInput.effect}
              onChange={(effect) => setFilterInput({ ...filterInput, effect })}
              options={schemaQuery.data?.effects ?? []}
              includeAny
            />
            <div className="xl:col-span-1">
              <SelectBox
                label="Owner"
                value={filterInput.owner}
                onChange={(owner) => setFilterInput({ ...filterInput, owner })}
                options={owners}
                includeAny
              />
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-primary" />
            Policy Inventory
          </CardTitle>
        </CardHeader>
        <CardContent>
          {policyQuery.isLoading ? (
            <StatePanel label="Loading policies..." />
          ) : policyQuery.isError ? (
            <ErrorPanel error={policyQuery.error} />
          ) : policies.length ? (
            <div className="divide-y rounded-md border">
              {policies.map((policy) => (
                <PolicyListRow key={policy.policyId} policy={policy} />
              ))}
            </div>
          ) : (
            <EmptyPanel title="No policies found" />
          )}
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Showing latest {policies.length} policies
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={page === 0 || policyQuery.isFetching}
                onClick={() => setPage((value) => Math.max(0, value - 1))}
              >
                <ArrowLeft className="h-4 w-4" />
                Previous
              </Button>
              <Badge variant="outline">Page {page + 1}</Badge>
              <Button
                type="button"
                variant="outline"
                disabled={!hasNextPage || policyQuery.isFetching}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </PolicyFrame>
  );
}

export function PolicyCreatePage() {
  const router = useRouter();
  const schemaQuery = useQuery({
    queryKey: ["policy-schema"],
    queryFn: getPolicySchema,
  });
  const mutation = useMutation({
    mutationFn: createPolicy,
    onSuccess: (policy) => router.push(`/policies/${policy.policyId}`),
  });

  if (schemaQuery.isLoading) {
    return <PolicyFrame title="Create Policy"><StatePanel label="Loading schema..." /></PolicyFrame>;
  }

  if (schemaQuery.isError || !schemaQuery.data) {
    return (
      <PolicyFrame title="Create Policy">
        <ErrorPanel error={schemaQuery.error ?? new Error("Policy schema unavailable")} />
      </PolicyFrame>
    );
  }

  return (
    <PolicyFrame
      title="Create Policy"
      icon={<Plus className="h-5 w-5 text-primary" />}
      backHref="/policies"
      backLabel="Policy inventory"
    >
      <PolicyForm
        schema={schemaQuery.data}
        mode="create"
        submitLabel="Create Draft"
        error={mutation.error}
        pending={mutation.isPending}
        onSubmit={(definition, editor) =>
          mutation.mutate(buildCreateRequest(definition, editor, schemaQuery.data))
        }
      />
    </PolicyFrame>
  );
}

export function PolicyDetailPage({ policyId }: { policyId: string }) {
  const query = useQuery({
    queryKey: ["policy", policyId],
    queryFn: () => getPolicy(policyId),
  });

  return (
    <PolicyFrame title="Policy Detail" backHref="/policies" backLabel="Policy inventory">
      {query.isLoading ? (
        <StatePanel label="Loading policy..." />
      ) : query.isError ? (
        <ErrorPanel error={query.error} />
      ) : query.data ? (
        <PolicyDetailContent policy={query.data} />
      ) : (
        <EmptyPanel title="Policy not found" />
      )}
    </PolicyFrame>
  );
}

export function PolicyVersionPage({
  policyId,
  version,
  mode,
}: {
  policyId: string;
  version: string;
  mode: "view" | "edit" | "simulate";
}) {
  const policyQuery = useQuery({
    queryKey: ["policy", policyId],
    queryFn: () => getPolicy(policyId),
  });
  const versionQuery = useQuery({
    queryKey: ["policy-version", policyId, version],
    queryFn: () => getPolicyVersion(policyId, version),
  });
  const schemaQuery = useQuery({
    queryKey: ["policy-schema"],
    queryFn: getPolicySchema,
  });

  const title =
    mode === "edit"
      ? "Edit Draft Version"
      : mode === "simulate"
        ? "Simulate Policy"
        : "Policy Version";

  return (
    <PolicyFrame
      title={title}
      backHref={`/policies/${encodeURIComponent(policyId)}`}
      backLabel="Policy detail"
    >
      {policyQuery.isLoading || versionQuery.isLoading || schemaQuery.isLoading ? (
        <StatePanel label="Loading version..." />
      ) : policyQuery.isError ? (
        <ErrorPanel error={policyQuery.error} />
      ) : versionQuery.isError ? (
        <ErrorPanel error={versionQuery.error} />
      ) : schemaQuery.isError ? (
        <ErrorPanel error={schemaQuery.error} />
      ) : policyQuery.data && versionQuery.data && schemaQuery.data ? (
        mode === "edit" ? (
          <PolicyVersionEditor
            policy={policyQuery.data}
            version={versionQuery.data}
            schema={schemaQuery.data}
          />
        ) : mode === "simulate" ? (
          <PolicySimulator
            policy={policyQuery.data}
            version={versionQuery.data}
            schema={schemaQuery.data}
          />
        ) : (
          <PolicyVersionContent
            policy={policyQuery.data}
            version={versionQuery.data}
            schema={schemaQuery.data}
          />
        )
      ) : (
        <EmptyPanel title="Policy version not found" />
      )}
    </PolicyFrame>
  );
}

function PolicyListRow({ policy }: { policy: PolicyListItem }) {
  return (
    <div className="grid gap-3 px-4 py-3 lg:grid-cols-[1.4fr_0.9fr_0.9fr_0.8fr_1fr_130px]">
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Link
            href={`/policies/${encodeURIComponent(policy.policyId)}`}
            className="truncate text-sm font-semibold hover:underline"
          >
            {policy.name}
          </Link>
          <StatusBadge value={policy.status} />
        </div>
        <div className="mt-1 line-clamp-2 text-sm text-muted-foreground">
          {policy.description ?? "No description"}
        </div>
      </div>
      <FieldBlock label="Project" value={policy.projectId} />
      <FieldBlock label="Category" value={policy.category} />
      <FieldBlock label="Owner" value={policy.owner} />
      <div className="grid grid-cols-2 gap-2">
        <FieldBlock label="Active" value={policy.activeVersion ?? "None"} />
        <FieldBlock label="Draft" value={policy.draftVersion ?? "None"} />
        <FieldBlock label="Targets" value={policy.targetTypes.join(", ")} />
        <FieldBlock label="Effect" value={policy.primaryEffect ?? "None"} />
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        <IconLink href={`/policies/${encodeURIComponent(policy.policyId)}`} title="View">
          <ArrowRight className="h-4 w-4" />
        </IconLink>
        {policy.draftVersion ? (
          <IconLink
            href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(policy.draftVersion)}/edit`}
            title="Edit draft"
          >
            <FilePenLine className="h-4 w-4" />
          </IconLink>
        ) : null}
        {(policy.draftVersion ?? policy.activeVersion) ? (
          <IconLink
            href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(policy.draftVersion ?? policy.activeVersion ?? "")}/simulate`}
            title="Simulate"
          >
            <CirclePlay className="h-4 w-4" />
          </IconLink>
        ) : null}
      </div>
    </div>
  );
}

function PolicyDetailContent({ policy }: { policy: PolicyDetail }) {
  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Policy Definition
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2">
              <FieldBlock label="Name" value={policy.name} />
              <FieldBlock label="Category" value={policy.category} />
              <FieldBlock label="Organization" value={policy.organizationId} />
              <FieldBlock label="Project" value={policy.projectId} />
              <FieldBlock label="Owner" value={policy.owner} />
              <FieldBlock label="Created by" value={policy.createdBy} />
              <FieldBlock label="Created" value={formatDate(policy.createdAt)} />
              <FieldBlock label="Updated" value={formatDate(policy.updatedAt)} />
            </div>
            <div className="mt-4 rounded-md border bg-background p-3 text-sm leading-6">
              {policy.description ?? "No description"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <BadgeCheck className="h-4 w-4 text-primary" />
              Current Versions
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <VersionSnapshot
              title="Active Version"
              policyId={policy.policyId}
              version={policy.activeVersion}
            />
            <VersionSnapshot
              title="Draft Version"
              policyId={policy.policyId}
              version={policy.draftVersion}
            />
          </CardContent>
        </Card>
      </div>
      <VersionHistory policy={policy} />
    </>
  );
}

function VersionSnapshot({
  title,
  policyId,
  version,
}: {
  title: string;
  policyId: string;
  version: PolicyVersion | null;
}) {
  if (!version) {
    return (
      <div className="rounded-md border bg-background p-3 text-sm text-muted-foreground">
        <div className="font-medium text-foreground">{title}</div>
        <div className="mt-1">None</div>
      </div>
    );
  }
  return (
    <div className="rounded-md border bg-background p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium">{title}</div>
        <StatusBadge value={version.status} />
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <FieldBlock label="Version" value={version.version} />
        <FieldBlock label="Targets" value={version.targetTypes.join(", ")} />
        <FieldBlock label="Effect" value={version.rules[0]?.effect ?? "None"} />
        <FieldBlock
          label="Priority"
          value={String(
            Math.min(...version.rules.map((rule) => rule.priority)),
          )}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button asChild size="sm" variant="outline">
          <Link
            href={`/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version.version)}`}
          >
            View
          </Link>
        </Button>
        {version.status === "DRAFT" ? (
          <Button asChild size="sm" variant="outline">
            <Link
              href={`/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version.version)}/edit`}
            >
              Edit
            </Link>
          </Button>
        ) : null}
        {version.status !== "ARCHIVED" ? (
          <Button asChild size="sm" variant="outline">
            <Link
              href={`/policies/${encodeURIComponent(policyId)}/versions/${encodeURIComponent(version.version)}/simulate`}
            >
              Simulate
            </Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function VersionHistory({ policy }: { policy: PolicyDetail }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <History className="h-4 w-4 text-primary" />
          Version History
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y rounded-md border">
          {policy.versions.map((version) => (
            <Link
              key={version.version}
              href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(version.version)}`}
              className="grid gap-3 px-4 py-3 hover:bg-accent/55 lg:grid-cols-[120px_140px_1fr_1fr_34px]"
            >
              <FieldBlock label="Version" value={version.version} />
              <div>
                <LabelText>Status</LabelText>
                <StatusBadge value={version.status} />
              </div>
              <FieldBlock label="Created by" value={version.createdBy} />
              <FieldBlock label="Created" value={formatDate(version.createdAt)} />
              <div className="flex items-center justify-end">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
              </div>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function PolicyVersionContent({
  policy,
  version,
  schema,
}: {
  policy: PolicyDetail;
  version: PolicyVersion;
  schema: PolicySchema;
}) {
  return (
    <>
      <VersionHeader policy={policy} version={version} schema={schema} />
      <RulesReadOnly version={version} schema={schema} />
    </>
  );
}

function VersionHeader({
  policy,
  version,
  schema,
}: {
  policy: PolicyDetail;
  version: PolicyVersion;
  schema: PolicySchema;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-primary" />
            {policy.name} v{version.version}
          </CardTitle>
          <StatusBadge value={version.status} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <FieldBlock label="Targets" value={version.targetTypes.join(", ")} />
          <FieldBlock label="Created by" value={version.createdBy} />
          <FieldBlock label="Created" value={formatDate(version.createdAt)} />
          <FieldBlock
            label="Activated"
            value={version.activatedAt ? formatDate(version.activatedAt) : "None"}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <VersionActions policy={policy} version={version} schema={schema} />
        </div>
      </CardContent>
    </Card>
  );
}

function VersionActions({
  policy,
  version,
  schema,
}: {
  policy: PolicyDetail;
  version: PolicyVersion;
  schema: PolicySchema;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const createMutation = useMutation({
    mutationFn: () =>
      createPolicyVersion(policy.policyId, {
        base_version: version.version,
        target_types: version.targetTypes,
        rules: version.rules.map(ruleToInput),
        created_by: DEFAULT_ACTOR,
        metadata: version.metadata,
      }),
    onSuccess: async (detail) => {
      await queryClient.invalidateQueries({ queryKey: ["policy", policy.policyId] });
      const draftVersion = detail.draftVersion?.version;
      if (draftVersion) {
        router.push(
          `/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(draftVersion)}/edit`,
        );
      }
    },
  });
  const activateMutation = useLifecycleMutation(policy.policyId, () =>
    activatePolicyVersion(policy.policyId, version.version, DEFAULT_ACTOR),
  );
  const archiveMutation = useLifecycleMutation(policy.policyId, () =>
    archivePolicyVersion(policy.policyId, version.version, DEFAULT_ACTOR),
  );

  return (
    <>
      {version.status === "DRAFT" ? (
        <>
          <Button asChild variant="outline">
            <Link
              href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(version.version)}/edit`}
            >
              <FilePenLine className="h-4 w-4" />
              Edit Draft
            </Link>
          </Button>
          <Button
            type="button"
            onClick={() => activateMutation.mutate()}
            disabled={activateMutation.isPending}
          >
            <BadgeCheck className="h-4 w-4" />
            Activate
          </Button>
        </>
      ) : version.status === "ACTIVE" ? (
        <Button
          type="button"
          variant="outline"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !schema.targetTypes.length}
        >
          <Plus className="h-4 w-4" />
          New Version
        </Button>
      ) : null}
      {version.status !== "ARCHIVED" ? (
        <>
          <Button asChild variant="outline">
            <Link
              href={`/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(version.version)}/simulate`}
            >
              <CirclePlay className="h-4 w-4" />
              Simulate
            </Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => archiveMutation.mutate()}
            disabled={archiveMutation.isPending}
          >
            <Archive className="h-4 w-4" />
            Archive
          </Button>
        </>
      ) : null}
      <MutationError error={createMutation.error ?? activateMutation.error ?? archiveMutation.error} />
    </>
  );
}

function PolicyVersionEditor({
  policy,
  version,
  schema,
}: {
  policy: PolicyDetail;
  version: PolicyVersion;
  schema: PolicySchema;
}) {
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: (request: UpdateDraftPolicyVersionRequest) =>
      updateDraftPolicyVersion(policy.policyId, version.version, request),
    onSuccess: () =>
      router.push(
        `/policies/${encodeURIComponent(policy.policyId)}/versions/${encodeURIComponent(version.version)}`,
      ),
  });

  if (version.status !== "DRAFT") {
    return (
      <Card>
        <CardContent className="pt-4">
          <EmptyPanel title="This version is read-only" />
        </CardContent>
      </Card>
    );
  }

  return (
    <PolicyForm
      schema={schema}
      mode="edit"
      initialEditor={editorFromVersion(version)}
      submitLabel="Save Draft"
      error={mutation.error}
      pending={mutation.isPending}
      onSubmit={(_definition, editor) =>
        mutation.mutate({
          target_types: editor.targetTypes,
          rules: rulesToInputs(editor, schema),
          updated_by: DEFAULT_ACTOR,
          metadata: parseObject(editor.metadataJson, "Version metadata"),
        })
      }
    />
  );
}

function PolicySimulator({
  policy,
  version,
  schema,
}: {
  policy: PolicyDetail;
  version: PolicyVersion;
  schema: PolicySchema;
}) {
  const [targetType, setTargetType] = useState(
    version.targetTypes[0] ?? schema.targetTypes[0]?.value ?? "",
  );
  const [targetId, setTargetId] = useState("candidate-1");
  const [evidenceJson, setEvidenceJson] = useState(
    JSON.stringify(sampleEvidence(targetType), null, 2),
  );
  const [metadataJson, setMetadataJson] = useState('{"source":"studio"}');
  const [formError, setFormError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () =>
      simulatePolicyVersion(policy.policyId, version.version, {
        target_type: targetType,
        target_id: targetId,
        evidence: parseObject(evidenceJson, "Evidence JSON"),
        metadata: parseObject(metadataJson, "Metadata JSON"),
      }),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    try {
      parseObject(evidenceJson, "Evidence JSON");
      parseObject(metadataJson, "Metadata JSON");
      mutation.mutate();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Invalid JSON");
    }
  }

  return (
    <>
      <VersionHeader policy={policy} version={version} schema={schema} />
      {version.status === "ARCHIVED" ? (
        <EmptyPanel title="Archived versions cannot be simulated" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2">
                <CirclePlay className="h-4 w-4 text-primary" />
                Simulation Input
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={handleSubmit}>
                <SelectBox
                  label="Target type"
                  value={targetType}
                  onChange={(value) => {
                    setTargetType(value);
                    setEvidenceJson(JSON.stringify(sampleEvidence(value), null, 2));
                  }}
                  options={version.targetTypes}
                />
                <TextField label="Target ID" value={targetId} onChange={setTargetId} />
                <JsonField label="Evidence JSON" value={evidenceJson} onChange={setEvidenceJson} rows={12} />
                <JsonField label="Metadata" value={metadataJson} onChange={setMetadataJson} rows={4} />
                {formError ? <InlineError message={formError} /> : null}
                <MutationError error={mutation.error} />
                <Button type="submit" disabled={mutation.isPending || !targetType || !targetId.trim()}>
                  <CirclePlay className="h-4 w-4" />
                  Run Simulation
                </Button>
              </form>
            </CardContent>
          </Card>
          <SimulationResultPanel result={mutation.data} pending={mutation.isPending} />
        </div>
      )}
    </>
  );
}

function SimulationResultPanel({
  result,
  pending,
}: {
  result?: PolicySimulation;
  pending: boolean;
}) {
  if (pending) {
    return <StatePanel label="Running simulation..." />;
  }

  if (!result) {
    return <EmptyPanel title="No simulation result" />;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <BadgeCheck className="h-4 w-4 text-primary" />
          Simulation Result
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldBlock label="MATCHED" value={result.matched ? "Yes" : "No"} />
          <FieldBlock label="EFFECT" value={result.effect} />
          <FieldBlock label="MATCHED rule" value={result.matchedRuleId ?? "None"} />
          <FieldBlock label="TARGET" value={`${result.targetType}/${result.targetId}`} />
        </div>
        <div className="rounded-md border bg-background p-3 text-sm leading-6">
          {result.reason}
        </div>
        <ConditionList title="Matched Conditions" conditions={result.matchedConditions} />
        <ConditionList title="Unmatched Conditions" conditions={result.unmatchedConditions} />
        <TraceList result={result} />
      </CardContent>
    </Card>
  );
}

function PolicyForm({
  schema,
  mode,
  initialEditor,
  submitLabel,
  error,
  pending,
  onSubmit,
}: {
  schema: PolicySchema;
  mode: "create" | "edit";
  initialEditor?: EditorState;
  submitLabel: string;
  error: unknown;
  pending: boolean;
  onSubmit: (definition: DefinitionState, editor: EditorState) => void;
}) {
  const [definition, setDefinition] = useState<DefinitionState>(() => ({
    name: "",
    description: "",
    organizationId: DEFAULT_ORGANIZATION,
    projectId: DEFAULT_PROJECT,
    category: schema.categories[0] ?? "",
    owner: "governance",
    actor: DEFAULT_ACTOR,
    metadataJson: '{"source":"studio"}',
  }));
  const [editor, setEditor] = useState<EditorState>(
    () => initialEditor ?? defaultEditor(schema),
  );
  const [formError, setFormError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    try {
      validateEditor(editor, schema);
      if (mode === "create") {
        validateDefinition(definition);
        parseObject(definition.metadataJson, "Policy metadata");
      }
      parseObject(editor.metadataJson, "Version metadata");
      onSubmit(definition, editor);
    } catch (nextError) {
      setFormError(
        nextError instanceof Error ? nextError.message : "Policy form is invalid.",
      );
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      {mode === "create" ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Policy Definition</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <TextField label="Name" value={definition.name} onChange={(value) => setDefinition({ ...definition, name: value })} />
            <TextField label="Organization" value={definition.organizationId} onChange={(value) => setDefinition({ ...definition, organizationId: value })} />
            <TextField label="Project" value={definition.projectId} onChange={(value) => setDefinition({ ...definition, projectId: value })} />
            <SelectBox label="Category" value={definition.category} onChange={(value) => setDefinition({ ...definition, category: value })} options={schema.categories} />
            <TextField label="Owner" value={definition.owner} onChange={(value) => setDefinition({ ...definition, owner: value })} />
            <TextField label="Created by" value={definition.actor} onChange={(value) => setDefinition({ ...definition, actor: value })} />
            <div className="md:col-span-2 xl:col-span-3">
              <LabelText>Description</LabelText>
              <textarea
                value={definition.description}
                onChange={(event) =>
                  setDefinition({ ...definition, description: event.target.value })
                }
                className={textareaClassName}
                rows={3}
              />
            </div>
            <div className="md:col-span-2 xl:col-span-3">
              <JsonField label="Metadata" value={definition.metadataJson} onChange={(value) => setDefinition({ ...definition, metadataJson: value })} rows={4} />
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Policy Version</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <TargetSelector schema={schema} editor={editor} setEditor={setEditor} />
          <RuleBuilder schema={schema} editor={editor} setEditor={setEditor} />
          <JsonField label="Version metadata" value={editor.metadataJson} onChange={(value) => setEditor({ ...editor, metadataJson: value })} rows={4} />
          {formError ? <InlineError message={formError} /> : null}
          <MutationError error={error} />
          <Button type="submit" disabled={pending}>
            <Save className="h-4 w-4" />
            {submitLabel}
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}

function TargetSelector({
  schema,
  editor,
  setEditor,
}: {
  schema: PolicySchema;
  editor: EditorState;
  setEditor: (editor: EditorState) => void;
}) {
  return (
    <div>
      <LabelText>Target Scope</LabelText>
      <div className="mt-2 flex flex-wrap gap-2">
        {schema.targetTypes.map((targetType) => {
          const selected = editor.targetTypes.includes(targetType.value);
          return (
            <button
              key={targetType.value}
              type="button"
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium",
                selected ? "border-primary bg-accent text-accent-foreground" : "bg-background",
              )}
              onClick={() =>
                setEditor({
                  ...editor,
                  targetTypes: selected
                    ? editor.targetTypes.filter((value) => value !== targetType.value)
                    : [...editor.targetTypes, targetType.value],
                })
              }
            >
              {targetType.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RuleBuilder({
  schema,
  editor,
  setEditor,
}: {
  schema: PolicySchema;
  editor: EditorState;
  setEditor: (editor: EditorState) => void;
}) {
  function updateRule(ruleId: string, nextRule: EditorRule) {
    setEditor({
      ...editor,
      rules: editor.rules.map((rule) => (rule.id === ruleId ? nextRule : rule)),
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <LabelText>Rules</LabelText>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setEditor({ ...editor, rules: [...editor.rules, defaultRule(schema)] })}
        >
          <Plus className="h-4 w-4" />
          Rule
        </Button>
      </div>
      {editor.rules.map((rule, index) => (
        <div key={rule.id} className="rounded-md border bg-background p-3">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="text-sm font-semibold">Rule {index + 1}</div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={editor.rules.length === 1}
              onClick={() =>
                setEditor({
                  ...editor,
                  rules: editor.rules.filter((item) => item.id !== rule.id),
                })
              }
              title="Remove rule"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            <TextField label="Rule ID" value={rule.ruleId} onChange={(value) => updateRule(rule.id, { ...rule, ruleId: value })} />
            <TextField label="Name" value={rule.name} onChange={(value) => updateRule(rule.id, { ...rule, name: value })} />
            <TextField label="Priority" value={rule.priority} onChange={(value) => updateRule(rule.id, { ...rule, priority: value })} />
            <SelectBox label="Effect" value={rule.effect} onChange={(value) => updateRule(rule.id, { ...rule, effect: value })} options={schema.effects} />
            <SelectBox label="Severity" value={rule.severity} onChange={(value) => updateRule(rule.id, { ...rule, severity: value })} options={schema.severities} />
            <TextField label="Reason" value={rule.reasonTemplate} onChange={(value) => updateRule(rule.id, { ...rule, reasonTemplate: value })} />
          </div>
          <ConditionBuilder schema={schema} rule={rule} updateRule={(nextRule) => updateRule(rule.id, nextRule)} />
        </div>
      ))}
    </div>
  );
}

function ConditionBuilder({
  schema,
  rule,
  updateRule,
}: {
  schema: PolicySchema;
  rule: EditorRule;
  updateRule: (rule: EditorRule) => void;
}) {
  const fields = schema.targetTypes.flatMap((targetType) => targetType.fields);

  function updateCondition(conditionId: string, next: EditorCondition) {
    updateRule({
      ...rule,
      conditions: rule.conditions.map((condition) =>
        condition.id === conditionId ? next : condition,
      ),
    });
  }

  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <LabelText>Conditions</LabelText>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            updateRule({
              ...rule,
              conditions: [...rule.conditions, defaultCondition(schema)],
            })
          }
        >
          <Plus className="h-4 w-4" />
          Condition
        </Button>
      </div>
      {rule.conditions.map((condition) => {
        const field = fields.find((item) => item.fieldPath === condition.fieldPath) ?? fields[0];
        const operatorOptions = field?.supportedOperators ?? schema.operators;
        const expectsValue = !["EXISTS", "MISSING"].includes(condition.operator);
        return (
          <div
            key={condition.id}
            className="grid gap-2 rounded-md border bg-card p-2 md:grid-cols-[1fr_190px_1fr_40px]"
          >
            <SelectBox
              label="Field"
              value={condition.fieldPath}
              onChange={(value) => {
                const nextField = fields.find((item) => item.fieldPath === value);
                updateCondition(condition.id, {
                  ...condition,
                  fieldPath: value,
                  operator: nextField?.supportedOperators[0] ?? condition.operator,
                  expectedValue: "",
                });
              }}
              options={fields.map((item) => item.fieldPath)}
            />
            <SelectBox
              label="Operator"
              value={condition.operator}
              onChange={(value) => updateCondition(condition.id, { ...condition, operator: value })}
              options={operatorOptions}
            />
            {field?.allowedValues?.length ? (
              <SelectBox
                label="Expected"
                value={condition.expectedValue}
                onChange={(value) => updateCondition(condition.id, { ...condition, expectedValue: value })}
                options={field.allowedValues.map(String)}
                disabled={!expectsValue}
              />
            ) : (
              <TextField
                label="Expected"
                value={condition.expectedValue}
                onChange={(value) => updateCondition(condition.id, { ...condition, expectedValue: value })}
                disabled={!expectsValue}
              />
            )}
            <div className="flex items-end">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                disabled={rule.conditions.length === 1}
                onClick={() =>
                  updateRule({
                    ...rule,
                    conditions: rule.conditions.filter((item) => item.id !== condition.id),
                  })
                }
                title="Remove condition"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RulesReadOnly({ version, schema }: { version: PolicyVersion; schema: PolicySchema }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-primary" />
          Rules
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {version.rules.map((rule) => (
          <div key={rule.ruleId} className="rounded-md border bg-background p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-semibold">{rule.name}</div>
                <div className="mt-1 font-mono text-xs text-muted-foreground">
                  {rule.ruleId}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{rule.effect}</Badge>
                {rule.severity ? <Badge variant="secondary">{rule.severity}</Badge> : null}
                <Badge variant="outline">Priority {rule.priority}</Badge>
              </div>
            </div>
            <div className="mt-3 rounded-md border bg-card p-3 text-sm">
              {rule.reasonTemplate}
            </div>
            <ConditionList title="Conditions" conditions={rule.conditions} schema={schema} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ConditionList({
  title,
  conditions,
  schema,
}: {
  title: string;
  conditions: PolicyCondition[];
  schema?: PolicySchema;
}) {
  const fields = schema?.targetTypes.flatMap((targetType) => targetType.fields) ?? [];
  return (
    <div>
      <LabelText>{title}</LabelText>
      <div className="mt-2 divide-y rounded-md border">
        {conditions.length ? (
          conditions.map((condition, index) => {
            const field = fields.find((item) => item.fieldPath === condition.fieldPath);
            return (
              <div key={`${condition.fieldPath}-${index}`} className="grid gap-2 p-3 text-sm md:grid-cols-[1fr_180px_1fr]">
                <FieldBlock label="Field" value={field?.label ?? condition.fieldPath} />
                <FieldBlock label="Operator" value={condition.operator} />
                <FieldBlock label="Expected" value={formatJsonValue(condition.expectedValue)} />
              </div>
            );
          })
        ) : (
          <div className="p-3 text-sm text-muted-foreground">None</div>
        )}
      </div>
    </div>
  );
}

function TraceList({ result }: { result: PolicySimulation }) {
  return (
    <div>
      <LabelText>Evaluation Trace</LabelText>
      <div className="mt-2 divide-y rounded-md border">
        {result.evaluationTrace.map((item, index) => (
          <div key={`${item.ruleId}-${item.conditionFieldPath}-${index}`} className="grid gap-2 p-3 text-sm lg:grid-cols-[1fr_1fr_120px_120px]">
            <FieldBlock label="Rule" value={item.ruleName} />
            <FieldBlock label="Field" value={item.conditionFieldPath} />
            <FieldBlock label="Actual" value={formatJsonValue(item.actualValue)} />
            <div>
              <LabelText>MATCHED</LabelText>
              <Badge variant={item.matched ? "secondary" : "outline"}>
                {item.matched ? "Yes" : "No"}
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PolicyFrame({
  title,
  children,
  icon,
  actions,
  backHref,
  backLabel,
}: {
  title: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  backHref?: string;
  backLabel?: string;
}) {
  return (
    <div className="h-[calc(100vh-3.5rem)] overflow-y-auto">
      <div className="studio-page flex flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {backHref ? (
              <Link
                href={backHref}
                className="mb-3 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="h-4 w-4" />
                {backLabel ?? "Back"}
              </Link>
            ) : null}
            <div className="flex min-w-0 items-center gap-2">
              {icon ?? <SlidersHorizontal className="h-5 w-5 text-primary" />}
              <h1 className="truncate text-2xl font-semibold tracking-normal">
                {title}
              </h1>
            </div>
          </div>
          {actions}
        </div>
        {children}
      </div>
    </div>
  );
}

function useLifecycleMutation(policyId: string, mutationFn: () => Promise<PolicyDetail>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["policy", policyId] }),
        queryClient.invalidateQueries({ queryKey: ["policies"] }),
        queryClient.invalidateQueries({ queryKey: ["policy-version"] }),
      ]);
    },
  });
}

function buildCreateRequest(
  definition: DefinitionState,
  editor: EditorState,
  schema: PolicySchema,
): CreatePolicyRequest {
  return {
    name: definition.name.trim(),
    description: definition.description.trim() || null,
    organization_id: definition.organizationId.trim(),
    project_id: definition.projectId.trim(),
    category: definition.category,
    owner: definition.owner.trim(),
    created_by: definition.actor.trim(),
    target_types: editor.targetTypes,
    rules: rulesToInputs(editor, schema),
    metadata: parseObject(definition.metadataJson, "Policy metadata"),
  };
}

function rulesToInputs(editor: EditorState, schema: PolicySchema): PolicyRuleInput[] {
  return editor.rules.map((rule) => ({
    rule_id: rule.ruleId.trim(),
    name: rule.name.trim(),
    conditions: rule.conditions.map((condition) =>
      conditionToInput(condition, schema),
    ),
    effect: rule.effect,
    reason_template: rule.reasonTemplate.trim(),
    priority: Number(rule.priority),
    severity: rule.severity || null,
    metadata: {},
  }));
}

function ruleToInput(rule: PolicyRule): PolicyRuleInput {
  return {
    rule_id: rule.ruleId,
    name: rule.name,
    conditions: rule.conditions.map((condition) => ({
      field_path: condition.fieldPath,
      operator: condition.operator,
      expected_value: condition.expectedValue,
      metadata: condition.metadata,
    })),
    effect: rule.effect,
    reason_template: rule.reasonTemplate,
    priority: rule.priority,
    severity: rule.severity,
    metadata: rule.metadata,
  };
}

function conditionToInput(
  condition: EditorCondition,
  schema: PolicySchema,
): PolicyConditionInput {
  const field = findSchemaField(schema, condition.fieldPath);
  const expectedValue =
    condition.operator === "EXISTS" || condition.operator === "MISSING"
      ? null
      : parseExpectedValue(condition.expectedValue, field);
  return {
    field_path: condition.fieldPath,
    operator: condition.operator,
    expected_value: expectedValue,
    metadata: {},
  };
}

function validateDefinition(definition: DefinitionState) {
  const required = [
    definition.name,
    definition.organizationId,
    definition.projectId,
    definition.category,
    definition.owner,
    definition.actor,
  ];
  if (required.some((value) => !value.trim())) {
    throw new Error("Policy definition fields are required.");
  }
}

function validateEditor(editor: EditorState, schema: PolicySchema) {
  if (!editor.targetTypes.length) {
    throw new Error("Select at least one target type.");
  }
  if (!editor.rules.length) {
    throw new Error("Add at least one rule.");
  }
  const ruleIds = new Set<string>();
  editor.rules.forEach((rule) => {
    if (!rule.ruleId.trim() || !rule.name.trim() || !rule.reasonTemplate.trim()) {
      throw new Error("Rule ID, name, and reason are required.");
    }
    if (ruleIds.has(rule.ruleId.trim())) {
      throw new Error("Rule IDs must be unique.");
    }
    ruleIds.add(rule.ruleId.trim());
    if (!Number.isFinite(Number(rule.priority)) || Number(rule.priority) < 0) {
      throw new Error("Rule priority must be a non-negative number.");
    }
    if (!rule.effect) {
      throw new Error("Each rule needs an effect.");
    }
    rule.conditions.forEach((condition) => {
      if (!condition.fieldPath || !condition.operator) {
        throw new Error("Each condition needs a field and operator.");
      }
      const expectsValue = !["EXISTS", "MISSING"].includes(condition.operator);
      if (expectsValue && !condition.expectedValue.trim()) {
        throw new Error("Expected value is required for comparison operators.");
      }
      conditionToInput(condition, schema);
    });
  });
}

function parseObject(value: string, label: string): JsonObject {
  const parsed = JSON.parse(value || "{}") as JsonValue;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed;
}

function parseExpectedValue(value: string, field?: PolicySchemaField): JsonValue {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  if (field?.valueType === "number") {
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) {
      throw new Error(`${field.label} expects a numeric value.`);
    }
    return parsed;
  }
  if (trimmed === "true") {
    return true;
  }
  if (trimmed === "false") {
    return false;
  }
  if (trimmed === "null") {
    return null;
  }
  if (trimmed.startsWith("[") || trimmed.startsWith("{")) {
    return JSON.parse(trimmed) as JsonValue;
  }
  return trimmed;
}

function defaultEditor(schema: PolicySchema): EditorState {
  return {
    targetTypes: schema.targetTypes[0]?.value ? [schema.targetTypes[0].value] : [],
    rules: [defaultRule(schema)],
    metadataJson: "{}",
  };
}

function defaultRule(schema: PolicySchema): EditorRule {
  return {
    id: crypto.randomUUID(),
    ruleId: `rule-${Date.now()}`,
    name: "New rule",
    priority: "10",
    effect: schema.effects[0] ?? "",
    severity: schema.severities[0] ?? "",
    reasonTemplate: "Policy rule matched.",
    conditions: [defaultCondition(schema)],
  };
}

function defaultCondition(schema: PolicySchema): EditorCondition {
  const field = schema.targetTypes[0]?.fields[0];
  return {
    id: crypto.randomUUID(),
    fieldPath: field?.fieldPath ?? "",
    operator: field?.supportedOperators[0] ?? schema.operators[0] ?? "",
    expectedValue: "",
  };
}

function editorFromVersion(version: PolicyVersion): EditorState {
  return {
    targetTypes: version.targetTypes,
    rules: version.rules.map((rule) => ({
      id: crypto.randomUUID(),
      ruleId: rule.ruleId,
      name: rule.name,
      priority: String(rule.priority),
      effect: rule.effect,
      severity: rule.severity ?? "",
      reasonTemplate: rule.reasonTemplate,
      conditions: rule.conditions.map((condition) => ({
        id: crypto.randomUUID(),
        fieldPath: condition.fieldPath,
        operator: condition.operator,
        expectedValue:
          condition.expectedValue === null
            ? ""
            : typeof condition.expectedValue === "string"
              ? condition.expectedValue
              : JSON.stringify(condition.expectedValue),
      })),
    })),
    metadataJson: JSON.stringify(version.metadata, null, 2),
  };
}

function findSchemaField(schema: PolicySchema, fieldPath: string) {
  return schema.targetTypes
    .flatMap((targetType) => targetType.fields)
    .find((field) => field.fieldPath === fieldPath);
}

function sampleEvidence(targetType: string): JsonObject {
  if (targetType === "Candidate") {
    return {
      metrics: {
        groundedness: { score: 0.91 },
        answer_relevance: { score: 0.88 },
      },
      cost: { estimated_usd: 1.25 },
      drift: { severity: "LOW" },
    };
  }
  if (targetType === "PromptVersion") {
    return { prompt: { status: "DRAFT", variables: { count: 3 } } };
  }
  if (targetType === "ModelVersion") {
    return { model: { provider: "mock", risk_tier: "LOW" } };
  }
  return {};
}

function SelectBox({
  label,
  value,
  onChange,
  options,
  includeAny = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  includeAny?: boolean;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      >
        {includeAny ? <option value="">Any</option> : null}
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <Input
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1"
      />
    </label>
  );
}

function JsonField({
  label,
  value,
  onChange,
  rows,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows: number;
}) {
  return (
    <label className="block">
      <LabelText>{label}</LabelText>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(textareaClassName, "mt-1 font-mono")}
        rows={rows}
      />
    </label>
  );
}

function FieldBlock({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="min-w-0">
      <LabelText>{label}</LabelText>
      <div className="mt-1 truncate text-sm font-medium">
        {value === null || value === undefined || value === "" ? "None" : value}
      </div>
    </div>
  );
}

function IconLink({
  href,
  title,
  children,
}: {
  href: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex h-8 w-8 items-center justify-center rounded-md border bg-background hover:bg-accent"
      title={title}
      aria-label={title}
    >
      {children}
    </Link>
  );
}

function StatusBadge({ value }: { value: string }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-transparent font-semibold text-[#1f2328]",
        statusBadgeClassName(value),
      )}
    >
      {value}
    </Badge>
  );
}

function statusBadgeClassName(value: string) {
  if (value === "ACTIVE") {
    return "bg-[#32d74b] hover:bg-[#32d74b]";
  }
  if (value === "DRAFT") {
    return "bg-[#ffd60a] hover:bg-[#ffd60a]";
  }
  if (value === "ARCHIVED" || value === "DEPRECATED") {
    return "bg-[#ff453a] hover:bg-[#ff453a]";
  }
  return "bg-[#e5e5ea] hover:bg-[#e5e5ea]";
}

function StatePanel({ label }: { label: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center rounded-md border bg-card text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function EmptyPanel({ title }: { title: string }) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center rounded-md border bg-card px-4 py-6 text-center">
      <ShieldCheck className="h-6 w-6 text-muted-foreground" />
      <div className="mt-3 text-sm font-semibold">{title}</div>
    </div>
  );
}

function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div className="rounded-md border border-destructive/30 bg-card p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold text-destructive">
        <AlertCircle className="h-4 w-4" />
        Request failed
      </div>
      <div className="mt-2 text-muted-foreground">{formatError(error)}</div>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      {message}
    </div>
  );
}

function MutationError({ error }: { error: unknown }) {
  return error ? <InlineError message={formatError(error)} /> : null;
}

function LabelText({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-medium uppercase text-muted-foreground">
      {children}
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) {
    return "None";
  }
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatError(error: unknown) {
  if (error instanceof AIGovernanceApiError) {
    return `${error.code}: ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error.";
}

function formatJsonValue(value: JsonValue | null) {
  if (value === null) {
    return "None";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((left, right) =>
    left.localeCompare(right),
  );
}

const textareaClassName =
  "min-h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";

"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { GraphEntity, GraphRelationship } from "@/types/graph";

export function EntityDetailPanel({
  entity,
  relationship,
}: {
  entity?: GraphEntity;
  relationship?: GraphRelationship;
}) {
  if (!entity && !relationship) {
    return (
      <Card className="h-full min-w-0 rounded-none border-0 border-l shadow-none">
        <CardHeader>
          <CardTitle>Selection</CardTitle>
          <CardDescription>Select a node or edge to inspect it.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className="h-full min-w-0 rounded-none border-0 border-l shadow-none">
      <ScrollArea className="h-full">
        {entity ? <EntityDetails entity={entity} /> : null}
        {relationship ? <RelationshipDetails relationship={relationship} /> : null}
      </ScrollArea>
    </Card>
  );
}

function EntityDetails({ entity }: { entity: GraphEntity }) {
  return (
    <>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Badge>{entity.entityType}</Badge>
          <Badge variant="outline">{entity.lifecycle}</Badge>
        </div>
        <CardTitle className="break-all">{entity.entityId}</CardTitle>
        <CardDescription>{entity.owner}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <DetailRow label="Ontology Version" value={entity.ontologyVersion} />
        <DetailRow label="Created" value={entity.createdAt} />
        <MetadataBlock title="Metadata" value={entity.metadata} />
        <MetadataBlock
          title="Immutable Attributes"
          value={entity.immutableAttributes}
        />
        <MetadataBlock
          title="Mutable Attributes"
          value={entity.mutableAttributes}
        />
      </CardContent>
    </>
  );
}

function RelationshipDetails({
  relationship,
}: {
  relationship: GraphRelationship;
}) {
  return (
    <>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Badge>{relationship.relationshipType}</Badge>
          <Badge variant="outline">Relationship</Badge>
        </div>
        <CardTitle className="break-all">{relationship.relationshipId}</CardTitle>
        <CardDescription>
          {relationship.sourceEntityType} to {relationship.targetEntityType}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <DetailRow label="Source" value={relationship.sourceEntityId} />
        <DetailRow label="Target" value={relationship.targetEntityId} />
        <DetailRow label="Created By" value={relationship.createdBy} />
        <DetailRow label="Ontology Version" value={relationship.ontologyVersion} />
        <DetailRow label="Created" value={relationship.createdAt} />
        <MetadataBlock title="Metadata" value={relationship.metadata} />
      </CardContent>
    </>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-normal text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 break-all text-sm">{value}</div>
    </div>
  );
}

function MetadataBlock({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown>;
}) {
  const rendered = JSON.stringify(value, null, 2);
  return (
    <div>
      <Separator className="mb-3" />
      <div className="mb-2 text-xs font-medium uppercase tracking-normal text-muted-foreground">
        {title}
      </div>
      <pre className="max-h-48 overflow-x-hidden overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs leading-5 [overflow-wrap:anywhere]">
        {rendered === "{}" ? "No values" : rendered}
      </pre>
    </div>
  );
}

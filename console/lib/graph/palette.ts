import type { GraphRelationship, GraphSubgraph } from "@/types/graph";

export type GraphTone = {
  background: string;
  badgeBackground: string;
  border: string;
  selected: string;
  focused: string;
  shadow: string;
  text: string;
  labelText: string;
};

export function relationToneFor(
  entityId: string,
  rootId: string,
  subgraph: GraphSubgraph,
) {
  if (entityId === rootId) {
    return graphPalette.root;
  }

  const directFromRoot = subgraph.edges.some(
    (edge) =>
      edge.relationship.sourceEntityId === rootId &&
      edge.relationship.targetEntityId === entityId,
  );
  if (directFromRoot) {
    return graphPalette.outbound;
  }

  const directToRoot = subgraph.edges.some(
    (edge) =>
      edge.relationship.targetEntityId === rootId &&
      edge.relationship.sourceEntityId === entityId,
  );
  if (directToRoot) {
    return graphPalette.inbound;
  }

  return graphPalette.neutral;
}

export function edgeToneFor(relationship: GraphRelationship, rootId: string) {
  if (relationship.sourceEntityId === rootId) {
    return graphPalette.outbound;
  }
  if (relationship.targetEntityId === rootId) {
    return graphPalette.inbound;
  }
  return graphPalette.neutral;
}

export function statusToneFor(lifecycle: string) {
  const value = lifecycle.toLowerCase();
  if (["approved", "completed", "succeeded"].includes(value)) {
    return graphPalette.success;
  }
  if (["running", "queued", "pending"].includes(value)) {
    return graphPalette.warning;
  }
  if (["failed", "rejected", "blocked", "cancelled"].includes(value)) {
    return graphPalette.danger;
  }
  if (["deprecated", "archived"].includes(value)) {
    return graphPalette.neutral;
  }
  return graphPalette.active;
}

const inputColor = envColor("NEXT_PUBLIC_GRAPH_INPUT_COLOR", "#f5f5f7");
const outputColor = envColor("NEXT_PUBLIC_GRAPH_OUTPUT_COLOR", "#f8fcfc");
const rootColor = envColor("NEXT_PUBLIC_GRAPH_ROOT_COLOR", "#f7f8fb");

const graphPalette = {
  root: tone({
    background: rootColor,
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_ROOT_BADGE_COLOR", "#eceef8"),
    border: envColor("NEXT_PUBLIC_GRAPH_ROOT_BORDER_COLOR", "#7d89b0"),
    selected: envColor("NEXT_PUBLIC_GRAPH_ROOT_SELECTED_COLOR", "#596582"),
    labelText: "var(--graph-root-label-text)",
    text: envColor("NEXT_PUBLIC_GRAPH_ROOT_TEXT_COLOR", "#424b63"),
    shadowRgb: "89 101 130",
  }),
  inbound: tone({
    background: inputColor,
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_INPUT_BADGE_COLOR", "#ededf2"),
    border: envColor("NEXT_PUBLIC_GRAPH_INPUT_BORDER_COLOR", "#8e8e93"),
    selected: envColor(
      "NEXT_PUBLIC_GRAPH_INPUT_SELECTED_COLOR",
      "var(--graph-input-selected-edge)",
    ),
    focused: "var(--graph-input-selected-edge)",
    labelText: "var(--graph-input-label-text)",
    text: envColor("NEXT_PUBLIC_GRAPH_INPUT_TEXT_COLOR", "#3a3a3c"),
    shadowRgb: "99 99 102",
  }),
  outbound: tone({
    background: outputColor,
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_OUTPUT_BADGE_COLOR", "#eff8f7"),
    border: envColor("NEXT_PUBLIC_GRAPH_OUTPUT_BORDER_COLOR", "#65c9c2"),
    selected: envColor("NEXT_PUBLIC_GRAPH_OUTPUT_SELECTED_COLOR", "#239b95"),
    labelText: "var(--graph-output-label-text)",
    text: envColor("NEXT_PUBLIC_GRAPH_OUTPUT_TEXT_COLOR", "#23706d"),
    shadowRgb: "101 201 194",
  }),
  neutral: tone({
    background: envColor("NEXT_PUBLIC_GRAPH_NEUTRAL_COLOR", "#ffffff"),
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_NEUTRAL_BADGE_COLOR", "#eef2f7"),
    border: envColor("NEXT_PUBLIC_GRAPH_NEUTRAL_BORDER_COLOR", "#9aa0a6"),
    selected: envColor("NEXT_PUBLIC_GRAPH_NEUTRAL_SELECTED_COLOR", "#5f6368"),
    labelText: "var(--graph-neutral-label-text)",
    text: envColor("NEXT_PUBLIC_GRAPH_NEUTRAL_TEXT_COLOR", "#3c4043"),
    shadowRgb: "95 99 104",
  }),
  active: tone({
    background: "#ffffff",
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_STATUS_ACTIVE_COLOR", "#edf8f1"),
    border: envColor("NEXT_PUBLIC_GRAPH_STATUS_ACTIVE_BORDER_COLOR", "#34c759"),
    selected: envColor("NEXT_PUBLIC_GRAPH_STATUS_ACTIVE_SELECTED_COLOR", "#248a3d"),
    text: envColor("NEXT_PUBLIC_GRAPH_STATUS_ACTIVE_TEXT_COLOR", "#248a3d"),
    shadowRgb: "52 199 89",
  }),
  success: tone({
    background: "#ffffff",
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_STATUS_SUCCESS_COLOR", "#edf8f1"),
    border: envColor("NEXT_PUBLIC_GRAPH_STATUS_SUCCESS_BORDER_COLOR", "#34c759"),
    selected: envColor("NEXT_PUBLIC_GRAPH_STATUS_SUCCESS_SELECTED_COLOR", "#248a3d"),
    text: envColor("NEXT_PUBLIC_GRAPH_STATUS_SUCCESS_TEXT_COLOR", "#248a3d"),
    shadowRgb: "52 199 89",
  }),
  warning: tone({
    background: "#ffffff",
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_STATUS_WARNING_COLOR", "#fff8dc"),
    border: envColor("NEXT_PUBLIC_GRAPH_STATUS_WARNING_BORDER_COLOR", "#ffcc00"),
    selected: envColor("NEXT_PUBLIC_GRAPH_STATUS_WARNING_SELECTED_COLOR", "#b47f00"),
    text: envColor("NEXT_PUBLIC_GRAPH_STATUS_WARNING_TEXT_COLOR", "#8a5a00"),
    shadowRgb: "255 204 0",
  }),
  danger: tone({
    background: "#ffffff",
    badgeBackground: envColor("NEXT_PUBLIC_GRAPH_STATUS_DANGER_COLOR", "#fff0ef"),
    border: envColor("NEXT_PUBLIC_GRAPH_STATUS_DANGER_BORDER_COLOR", "#ff3b30"),
    selected: envColor("NEXT_PUBLIC_GRAPH_STATUS_DANGER_SELECTED_COLOR", "#c21f17"),
    text: envColor("NEXT_PUBLIC_GRAPH_STATUS_DANGER_TEXT_COLOR", "#b42318"),
    shadowRgb: "255 59 48",
  }),
} satisfies Record<string, GraphTone>;

function tone({
  background,
  badgeBackground,
  border,
  selected,
  focused = selected,
  text,
  labelText = text,
  shadowRgb,
}: {
  background: string;
  badgeBackground: string;
  border: string;
  selected: string;
  focused?: string;
  labelText?: string;
  text: string;
  shadowRgb: string;
}): GraphTone {
  return {
    background,
    badgeBackground,
    border,
    selected,
    focused,
    shadow: `rgb(${shadowRgb} / 0.22)`,
    text,
    labelText,
  };
}

function envColor(name: string, fallback: string) {
  const value = process.env[name];
  return value && value.trim() ? value.trim() : fallback;
}

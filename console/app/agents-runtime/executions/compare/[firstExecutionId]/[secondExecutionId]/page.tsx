import { ExecutionInspectorPage } from "@/components/agent-runtime/ExecutionInspector";

export default async function ExecutionComparisonRoute({ params }: { params: Promise<{ firstExecutionId: string; secondExecutionId: string }> }) {
  const { firstExecutionId, secondExecutionId } = await params;
  return <ExecutionInspectorPage executionIds={[firstExecutionId, secondExecutionId]} />;
}

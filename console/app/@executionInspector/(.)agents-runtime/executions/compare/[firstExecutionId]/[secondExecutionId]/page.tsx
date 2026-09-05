import { ExecutionInspectorModal } from "@/components/agent-runtime/ExecutionInspector";

export default async function InterceptedExecutionComparisonRoute({ params }: { params: Promise<{ firstExecutionId: string; secondExecutionId: string }> }) {
  const { firstExecutionId, secondExecutionId } = await params;
  return <ExecutionInspectorModal executionIds={[firstExecutionId, secondExecutionId]} />;
}

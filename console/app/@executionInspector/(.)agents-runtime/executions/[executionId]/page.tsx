import { ExecutionInspectorModal } from "@/components/agent-runtime/ExecutionInspector";

export default async function InterceptedExecutionInspectorRoute({ params }: { params: Promise<{ executionId: string }> }) {
  const { executionId } = await params;
  return <ExecutionInspectorModal executionIds={[executionId]} />;
}

import { ExecutionInspectorPage } from "@/components/agent-runtime/ExecutionInspector";

export default async function ExecutionInspectorRoute({ params }: { params: Promise<{ executionId: string }> }) {
  const { executionId } = await params;
  return <ExecutionInspectorPage executionIds={[executionId]} />;
}

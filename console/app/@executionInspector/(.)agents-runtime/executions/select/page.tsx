/**
 * Keep the existing execution-picker overlay as the only overlay for this
 * static route. Without this static parallel-route match, the dynamic
 * execution inspector would also intercept the literal "select" segment.
 */
export default function ExecutionInspectorSelectDefault() {
  return null;
}

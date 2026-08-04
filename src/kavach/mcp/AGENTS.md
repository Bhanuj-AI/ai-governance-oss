# Scope

This directory owns MCP transports, tool registration and handlers, REST client
bridges, runtime context, and MCP execution audit integration.

## Architectural Facts

- `src/kavach/mcp/server.py:create_server` assembles the tool registry and the
  REST client used by handlers.
- Optional MCP tool packages are discovered through the `kavach.mcp.plugins`
  entry-point group and register only through `MCPToolPluginContext`.
- MCP tools are REST-backed adapters. They preserve the REST control-plane
  contract rather than reimplementing service or persistence behavior.
- `MCPExecutionAuditRecord` in `src/kavach/mcp/audit.py` is the durable audit
  shape for MCP write operations and contains tenant, actor, correlation, and
  idempotency metadata.

## Change Rules

- Treat tool names and request/result DTOs as public contracts. Keep handlers
  thin, bound list/query output, and map REST failures through the MCP error
  mapping path.
- Establish runtime identity and tenant context before a protected operation.
  Do not return protected prompt content, tokens, or secrets in tool results or
  logs.
- Route tool activity through the approved MCP audit path. Preserve request and
  correlation identifiers so an invocation can be investigated across the REST
  boundary.
- Keep optional tool implementations outside OSS. An MCP plugin may contribute
  REST-backed tools, but it must not bypass the public tool-registration and
  tenant-scoped request context.

## Validation

Use `tests/mcp/test_mcp_server.py`, `tests/mcp/test_mcp_audit.py`, and
`tests/mcp/test_streamable_http.py` as the strongest transport contracts for
the affected change.

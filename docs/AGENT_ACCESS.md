# Agent access

FMR exposes the same deterministic lifecycle through Python, CLI, HTTP `/api/v2`, and an optional MCP stdio server. Agents can discover providers, simulate routes, inspect rejection reasons and missing inputs, prepare handoffs, execute jobs, validate results, and retrieve completed value-free receipts.

```console
fmr-mcp
```

The server implements JSON-RPC lifecycle and tool discovery over stdio. It writes only protocol messages to stdout. The supported protocol version is `2025-11-25`; initialization negotiates that version when a client requests another version.

Tools accept full versioned FMR contracts rather than natural-language shortcuts. Consequently, MCP calls use the same validation, routing, hash-chain, execution, and artifact checks as Python, CLI, and HTTP. Financial values are not copied into execution receipts.

The MCP server is local and has no remote listener or authentication layer. Remote MCP deployment is part of distributed-routing security work, not this package.

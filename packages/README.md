# Nodus Library Incubator

This directory contains incubator scaffolds for proposed standalone Nodus
ecosystem libraries.

Each library is laid out as if it were its own repo:

- `nodus-http`
- `nodus-retry`
- `nodus-events`
- `nodus-store-sql`
- `nodus-agent`
- `nodus-memory`
- `nodus-event`
- `nodus-a2a`

The code here is intentionally Python-first. The public Python APIs are the
canonical contracts that future thin Nodus builtins should wrap.

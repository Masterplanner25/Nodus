Stage 1: Lightweight IDL (Validation Only)

What Claude described:

module: time

functions:
  - name: format
    params:
      - name: date
        type: string
      - name: pattern
        type: string

    returns:
      type: string

Capabilities:

✅ Validate docs

✅ Validate implementation exists

✅ Validate signatures

❌ Generate code

❌ Generate docs

❌ Generate tests

❌ Generate bindings

At this stage it's basically metadata.

Stage 2: Executable Contracts

Now you add behavioral expectations.

module: time

functions:
  - name: format

    params:
      - name: date
        type: string

      - name: pattern
        type: string

    returns:
      type: string

    examples:
      - input:
          date: "2026-01-01"
          pattern: "%Y/%m/%d"

        output: "2026/01/01"

    errors:
      - InvalidDateError

Now the system can:

Generate contract tests
Verify examples
Verify error behavior

Instead of writing:

def test_time_format():
    ...

the test runner generates it.

This is where many languages stop.

Stage 3: Type System

Now the spec becomes richer.

types:

  Date:
    kind: string
    format: iso8601

  FormatPattern:
    kind: string

functions:

  - name: format

    params:
      - name: date
        type: Date

      - name: pattern
        type: FormatPattern

    returns:
      type: string

Now you're defining reusable types.

This starts looking like:

OpenAPI
Protobuf
Smithy
Stage 4: AST-Level Integration

This is where it gets interesting for Nodus.

Imagine:

functions:

  - name: memory.search

    params:
      - name: query
        type: string

    returns:
      type: MemoryResult[]

The compiler now knows:

let results = memory.search("agents")

returns:

MemoryResult[]

without hardcoding anything.

The IDL becomes part of the language.

Stage 5: Code Generation

This is where you officially have a "real" IDL.

Given:

functions:

  - name: memory.search

the system generates:

Python Binding
def memory_search(query: str):
    ...
Nodus Binding
memory.search(query)
Documentation
## memory.search(query)
Contract Tests
def test_memory_search():

from the same source.

Now the IDL is authoritative.

Stage 6: Service Definitions

This is where you enter Protocol Buffers territory.

service: Memory

functions:

  - name: search

  - name: remember

  - name: delete

Now the IDL can generate:

HTTP APIs
MCP tools
Runtime syscalls
SDKs
CLI commands

from one definition.

Why this could actually fit Nodus

The funny thing is that Nodus already has several ingredients:

Parser
AST
Type checker
Schema system
Tool registry
Runtime APIs
Memory APIs
Workflow APIs

A future Nodus IDL could become the canonical definition for:

stdlib
tools
syscalls
runtime APIs
memory APIs
MCP tools

Imagine:

tool:

  name: memory.search

  description: Search memory

  params:
    query:
      type: string

  returns:
    type: MemoryResult[]

From that single file Nodus could generate:

stdlib bindings
MCP schema
OpenAPI schema
documentation
contract tests
runtime registration

all automatically.

The path I'd envision is:

Option B
    ↓
Lightweight IDL
    ↓
Contract-test generation
    ↓
Type definitions
    ↓
Compiler awareness
    ↓
Code generation
    ↓
Service definitions
    ↓
Full Nodus IDL
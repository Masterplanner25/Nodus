Nodus Evolution Policy

This document defines how the Nodus language and runtime are allowed to evolve over time.

Programming languages naturally accumulate features as they grow. Without clear rules, this process can lead to unnecessary complexity, inconsistent semantics, and breaking changes that damage ecosystem stability.

The purpose of this document is to ensure that Nodus evolves intentionally and consistently.

1. Design Stability Principles

All changes to Nodus should follow these principles.

Clarity First

New features must improve the language without making the system harder to understand.

If a feature significantly increases conceptual complexity, it should be reconsidered.

Minimal Core Language

The core language grammar should remain small.

New capabilities should be implemented in:

the runtime

the standard library

tooling

before expanding the syntax of the language.

Backward Compatibility

Breaking changes should be rare.

When breaking changes are necessary:

they must be documented

they must be versioned clearly

migration paths should be provided where possible

2. Types of Changes

Not all changes have the same impact. Nodus distinguishes between several categories.

Bug Fixes

Bug fixes correct behavior that was never intended.

These changes:

do not alter language semantics intentionally

should not break correct programs

are released as patch updates

Example:

0.2.1
Runtime Improvements

These changes improve the runtime implementation without changing the language syntax.

Examples include:

VM performance improvements

scheduler improvements

orchestration runtime improvements

tooling enhancements

These changes typically fall under minor releases.

Language Feature Additions

New syntax or language constructs should be introduced carefully.

Requirements for adding a language feature:

The feature solves a real limitation.

The feature cannot reasonably live in the standard library.

The feature does not complicate the parser excessively.

The feature fits the philosophy described in DESIGN.md.

All new language features must include:

parser updates

compiler updates

runtime implementation

test coverage

specification updates in LANGUAGE_SPEC.md

Language Semantics Changes

Changes that alter the meaning of existing code are considered breaking changes.

These require:

clear documentation

version increment

migration notes

Breaking changes may only occur in major version releases.

3. Versioning Policy

Nodus follows Semantic Versioning.

MAJOR.MINOR.PATCH

Example:

0.3.0
Major

Breaking language or runtime changes.

Example:

1.0.0
Minor

New language features or runtime capabilities.

Example:

0.3.0
Patch

Bug fixes and small internal improvements.

Example:

0.3.1
4. Feature Proposal Process

Significant changes should be proposed before implementation.

A proposal should include:

motivation

design description

implementation approach

alternatives considered

Proposals may be submitted as:

GitHub issues

design documents

pull requests

The goal is to ensure that features are discussed before becoming permanent parts of the language.

5. Language Consistency Rules

When evolving the language, the following rules should be respected.

Avoid Multiple Ways to Do the Same Thing

The language should prefer one clear approach over multiple competing patterns.

Prefer Explicit Behavior

Implicit behaviors that are difficult to reason about should be avoided.

Maintain Tooling Compatibility

Changes should not break:

formatters

AST tools

bytecode disassemblers

debuggers

without strong justification.

6. Runtime Evolution

The runtime can evolve more freely than the language syntax.

Acceptable runtime changes include:

performance improvements

scheduler redesign

improved orchestration systems

enhanced debugging tools

These changes should not break existing programs unless absolutely necessary.

7. Deprecation Process

If a feature must be removed:

Mark the feature as deprecated

Document the replacement

Allow at least one release cycle before removal

Deprecation warnings should be clear and actionable.

8. Long-Term Direction

Nodus is evolving toward a scripting runtime designed for:

automation

orchestration

inspectable execution systems

Future development areas include:

runtime module system improvements

embedding APIs

improved orchestration primitives

stronger tooling

The language core should remain small and understandable even as the runtime grows.

9. Final Principle

The long-term health of the language depends on disciplined evolution.

Every new feature should answer the question:

Does this make the language clearer, or only larger?

If the answer is unclear, the change should be reconsidered.
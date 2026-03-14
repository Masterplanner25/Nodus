Contributing to Nodus

Thank you for your interest in contributing to Nodus.

Nodus is a small, readable scripting language built around a clean pipeline:

Source → Lexer → Parser → AST → Bytecode Compiler → Stack VM

The goal of the project is to maintain a clear, disciplined architecture while gradually evolving the language and its tooling.

Even small contributions should respect this structure.

Project Philosophy

Nodus prioritizes:

• Clarity over cleverness
• Small, understandable components
• Stable language semantics
• Deterministic tooling
• Incremental evolution

Changes should improve readability, reliability, or tooling quality without unnecessarily increasing complexity.

Repository Structure
nodus/
│
├─ lexer.py                # Tokenizer
├─ parser.py               # Parser → AST
├─ ast_nodes.py            # AST node definitions
├─ compiler.py             # AST → bytecode
├─ vm.py                   # Stack virtual machine
├─ task_graph.py           # Task/workflow runtime layer
├─ workflow_lowering.py    # Workflow → task graph lowering
│
├─ ast_printer.py          # AST inspection tooling
├─ formatter.py            # Deterministic formatter
│
├─ cli.py                  # CLI interface
├─ runner.py               # Execution helpers
├─ api.py                  # Optional service layer
│
├─ stdlib/                 # Standard library modules
│
tests/
│
docs/
│
README.md
LANGUAGE_SPEC.md
CHANGELOG.md

If adding new components, keep the architecture consistent with this structure.

Development Setup

Clone the repository:

git clone https://github.com/<repo>/nodus.git
cd nodus

Create a virtual environment:

python -m venv .venv

Activate it:

Linux / Mac
source .venv/bin/activate
Windows (PowerShell)
.venv\Scripts\Activate.ps1

Install development dependencies:

pip install -r requirements-dev.txt
Running Tests

Nodus uses pytest for testing.

Run the full test suite:

pytest

Run with verbose output:

pytest -v

Run a single test file:

pytest tests/test_vm.py

All contributions must pass the full test suite.

CLI Development Tools

Several CLI tools help inspect the language.

Parse and print AST:

nodus ast file.nd

Compile and disassemble:

nodus dis file.nd

Validate code:

nodus check file.nd

Format source code:

nodus fmt file.nd

These tools should remain stable and deterministic.

Code Style Guidelines

Follow standard Python practices.

General rules:

• Follow PEP8
• Prefer clear names over short names
• Keep functions small and focused
• Avoid deeply nested logic
• Avoid hidden side effects

Formatting should be handled by the project formatter where possible.

Example:

Good:

def compile_expression(expr):
    left = compile_node(expr.left)
    right = compile_node(expr.right)
    emit(OP_ADD)

Avoid:

def c(e): emit(OP_ADD)
Submitting Changes

Fork the repository

Create a feature branch

git checkout -b feature/my-change

Implement your change

Add or update tests

Run the test suite

Commit with clear messages

Example commit message:

Add AST serialization support for tooling

Submit a pull request.

Language Feature Changes

Changes to the language itself must be handled carefully.

Before adding a new feature:

Ask:

• Does this improve clarity or ergonomics?
• Does it complicate the parser or VM?
• Can it be implemented in the stdlib instead?

New syntax should be rare and justified.

Required steps for language changes:

Update the parser

Update AST definitions if needed

Update the compiler

Update the VM

Add tests

Update LANGUAGE_SPEC.md

Pull requests missing these updates may be rejected.

Standard Library Contributions

The standard library should remain small and coherent.

Good additions:

• Frequently needed utilities
• Cross-platform abstractions
• Pure functions

Avoid:

• Large frameworks
• Highly specialized features
• Heavy dependencies

Backwards Compatibility

Breaking changes should be avoided unless necessary.

If a breaking change is required:

• Document it clearly
• Update the changelog
• Bump the appropriate version

Versioning

Nodus follows Semantic Versioning.

MAJOR.MINOR.PATCH

Examples:

0.2.0
0.3.0
1.0.0

Meaning:

• MAJOR — breaking changes
• MINOR — new features
• PATCH — bug fixes

Release Process

Update CHANGELOG.md

Ensure all tests pass

Tag the release

git tag v0.3.0
git push origin v0.3.0

Publish release notes.

Reporting Issues

When reporting a bug include:

• Nodus version
• Operating system
• Minimal reproducible example

Example:

fn main() {
  let x = [1,2,3]
  print(x[5])
}

Expected vs actual behavior should be clearly described.

Code of Conduct

Be respectful and constructive.

Nodus is an educational and experimental language project intended to promote learning and exploration in language design.

Final Notes

The most valuable contributions are:

• improved tests
• documentation improvements
• bug fixes
• tooling enhancements

The goal is not to make Nodus large — it is to make it clear, understandable, and well-engineered.
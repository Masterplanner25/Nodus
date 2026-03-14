This document describes the internal architecture of the Nodus language.

It is intended for contributors working on the compiler, runtime, and tooling.

Language Architecture Overview

Nodus follows a classic interpreter pipeline:

Source Code
   ↓
Lexer (tokenizer)
   ↓
Parser
   ↓
AST
   ↓
Bytecode Compiler
   ↓
Stack Virtual Machine

Each stage has a clearly defined responsibility.

Core Components
Lexer

File:

lexer.py

Responsibilities:

Convert source text into tokens

Handle keywords, literals, operators, and identifiers

Track token position for error reporting

The lexer should remain simple and deterministic.

Parser

File:

parser.py

Responsibilities:

Convert tokens into an Abstract Syntax Tree (AST)

Enforce language grammar rules

Produce structured AST nodes defined in ast_nodes.py

The parser uses recursive descent parsing.

AST Nodes

File:

ast_nodes.py

Defines the language structure.

Examples include:

Module

FnDef

Block

Binary

Identifier

Call

If

While

The AST should remain explicit and readable.

Compiler

File:

compiler.py

Responsibilities:

Convert AST nodes into bytecode instructions

Manage constants and function objects

Emit instructions for the virtual machine

The compiler should avoid complex optimizations at this stage.

Clarity is preferred over aggressive optimization.

Virtual Machine

File:

vm.py

The Nodus runtime executes bytecode instructions.

Key characteristics:

stack-based execution model

deterministic instruction behavior

explicit instruction set

Example instructions:

PUSH_CONST
LOAD_VAR
STORE_VAR
CALL
RETURN
ADD
SUB
JUMP

The VM is intentionally simple to make execution behavior easy to understand.

Task Graph Runtime

Files:

task_graph.py
workflow_lowering.py

These components allow Nodus to express workflow-style execution.

The workflow system lowers high-level constructs into executable task graphs.

This is optional runtime functionality layered on top of the language core.

Tooling

Nodus includes several inspection tools.

AST Viewer
nodus ast file.nd

Prints the parsed AST structure.

Bytecode Disassembler
nodus dis file.nd

Displays compiled bytecode without executing the program.

Validator
nodus check file.nd

Performs static checks on code.

Formatter
nodus fmt file.nd

Enforces deterministic formatting.

Testing Philosophy

Tests should cover:

parser correctness

bytecode generation

runtime behavior

CLI tools

Tests should prefer small programs with deterministic output.

Design Goals

The language is designed to be:

readable

predictable

easy to debug

easy to inspect internally

Nodus prioritizes engineering clarity over feature count.

Future Development Areas

Examples of future improvements:

richer standard library

improved debugging tools

language server integration

performance improvements in the VM

These should be added without compromising architectural clarity.

Final Note

If the code becomes hard to explain, the design has likely become too complex.

The best language systems remain small, understandable, and well-structured.
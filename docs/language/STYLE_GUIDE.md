Nodus Style Guide

This document defines the recommended coding style for Nodus programs.

The goals of the style guide are:

readability

consistency

predictable formatting

easier collaboration

Where possible, formatting should be handled automatically using the built-in formatter:

nodus fmt

The formatter enforces most structural rules described here.

1. General Philosophy

Nodus code should prioritize clarity over cleverness.

Preferred characteristics:

short functions

descriptive names

explicit control flow

minimal nesting

consistent formatting

Programs should be easy to read even for someone unfamiliar with the project.

2. File Organization

Typical file structure:

imports
constants
records/types
helper functions
main logic

Example:

import std:strings
import std:collections

fn normalize_name(name) {
    return strings.trim(strings.lower(name))
}

fn main() {
    let name = normalize_name(" Alice ")
    print(name)
}
3. Naming Conventions
Variables

Use lower_snake_case.

user_name
task_count
current_index

Avoid single-letter names except in short loops.

Functions

Use lower_snake_case.

parse_input
load_config
run_workflow

Function names should describe actions.

Records / Structured Data

Use lower_snake_case for fields.

user = {
    name: "Alice",
    age: 30,
    is_active: true
}
Constants

Use UPPER_SNAKE_CASE for values intended to remain constant.

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 10
4. Indentation

Indentation uses four spaces.

Do not use tabs.

Example:

fn example() {
    let x = 1
    let y = 2
    return x + y
}
5. Line Length

Recommended maximum line length:

100 characters

Break long expressions across lines.

Example:

let result =
    compute_value(a, b, c)
    + compute_value(d, e, f)
6. Spacing Rules

Spaces should appear around binary operators.

Good:

a + b
x == y
count * 10

Avoid:

a+b
x==y
count*10
7. Function Style

Functions should remain short and focused.

Example:

fn is_even(n) {
    return n % 2 == 0
}

Avoid large multi-purpose functions.

Break complex logic into helper functions.

8. Control Flow

Prefer explicit control flow.

Example:

if count > 0 {
    process_items()
}

Avoid nested conditionals when possible.

Prefer early returns.

Example:

fn process(value) {
    if value == null {
        return
    }

    handle(value)
}
9. Collections

Use lists for ordered collections.

numbers = [1, 2, 3]

Use maps for key/value structures.

config = {
    host: "localhost",
    port: 8080
}

Avoid deeply nested data structures unless necessary.

10. Error Handling

Prefer clear error handling rather than deeply nested logic.

Example:

fn load_config(path) {
    if not exists(path) {
        return error("missing config")
    }

    return read_file(path)
}

Keep error paths obvious.

11. Comments

Use comments sparingly and only when they add clarity.

Good comments explain why, not what.

Good:

# retry because the external API occasionally fails
retry_request()

Avoid obvious comments:

# increment i
i = i + 1
12. Formatting

Use the built-in formatter whenever possible.

nodus fmt

The formatter ensures:

consistent indentation

normalized spacing

stable formatting across codebases

Manual formatting should follow the same conventions.

13. Import Style

Imports should appear at the top of the file.

Example:

import std:strings
import std:collections
import std:json

Group imports logically if the file grows large.

14. Function Length

Recommended limit:

30–40 lines

Longer functions should be broken into smaller helpers.

15. Avoid Clever Tricks

Readable code is preferred over clever code.

Avoid constructs that require readers to mentally simulate execution.

Example to avoid:

value = condition and compute_a() or compute_b()

Prefer explicit code:

if condition {
    value = compute_a()
} else {
    value = compute_b()
}
16. Tooling Integration

Tools that enforce or assist style:

nodus fmt      # formatting
nodus check    # validation
nodus ast      # inspect structure
nodus dis      # inspect bytecode

These tools support readable and maintainable programs.

17. Style Consistency

Consistency is more important than personal preference.

If a file already follows a style pattern, maintain that pattern when modifying it.

Final Principle

Good Nodus code should be easy to read, easy to debug, and easy to maintain.

If code becomes difficult to understand, it should be simplified.
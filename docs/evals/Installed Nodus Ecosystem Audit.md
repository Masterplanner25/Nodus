# Installed Nodus Ecosystem Audit

You are conducting an audit of the Nodus ecosystem exactly as it exists inside the currently active Python virtual environment.

Your objective is to determine what a user receives after installation.

## Critical Constraint

You are ONLY allowed to inspect artifacts that are available from the active virtual environment.

Treat the environment as if it were delivered to a user with no source repositories.

Do NOT inspect:

* sibling directories
* parent directories
* local development repositories
* git history
* source checkouts outside site-packages
* documents outside installed packages

If you discover files outside the virtual environment, ignore them.

The audit target is:

"What is installed and usable inside this venv?"

---

## Discovery Phase

Determine:

* Python version
* Installed packages
* Package metadata
* Package dependencies
* Console entry points
* Executables
* Importable modules
* Public APIs

Produce:

* Installed package inventory
* Package relationship map
* Entry-point inventory

---

## Package Surface Audit

For every installed Nodus-related package:

Determine:

* package name
* version
* purpose
* exposed modules
* public interfaces
* CLI commands
* documented capabilities

Classify each package as:

* Core Runtime
* Language
* SDK
* Tooling
* Integration
* Extension
* Experimental

---

## Nodus Language Audit

Using only the installed package contents:

Determine:

* execution model
* parser architecture
* compiler architecture
* bytecode architecture
* runtime architecture
* scheduler model
* module system
* package system

Verify through execution whenever possible.

Document:

* supported language features
* unsupported language features
* experimental features

For every claim:

Mark as:

* Verified
* Inferred
* Unknown

---

## CLI Audit

Inspect all installed commands.

For each command:

Determine:

* purpose
* available subcommands
* help quality
* discoverability
* error handling

Verify behavior through execution.

Produce:

* complete CLI inventory
* command hierarchy
* examples

---

## User Experience Audit

Assume you are a brand-new user.

You have only:

* the virtual environment
* installed packages
* command line access

You do NOT have:

* source repositories
* internal knowledge
* developer guidance

Attempt to answer:

1. What is Nodus?
2. How do I install it?
3. How do I run it?
4. How do I write my first program?
5. How do I discover advanced features?

Identify:

* onboarding gaps
* discoverability problems
* hidden assumptions

---

## Documentation Audit

Audit only documentation that ships with installed packages.

Ignore documentation outside the venv.

Determine:

* what documentation is available
* where it is located
* whether users can discover it

Evaluate:

* completeness
* consistency
* onboarding quality

---

## Ecosystem Cohesion Audit

Based solely on installed packages:

Determine:

* what appears to be the core product
* what appears optional
* what appears experimental

Create:

* package dependency map
* capability map
* user-facing architecture map

---

## Production Readiness Assessment

Score:

* Language Readiness
* Runtime Readiness
* Tooling Readiness
* CLI Readiness
* Documentation Readiness
* Developer Experience

Use a 1–10 scale.

Justify each score.

---

## Final Report

Produce:

### What Is Installed

A concise description of the ecosystem present in this venv.

### What A User Can Actually Do

List capabilities verified through execution.

### What Is Missing

List capabilities that appear incomplete or unavailable.

### Biggest Risks

Rank by severity.

### Highest-Leverage Improvements

Rank by user impact.

### First-Time User Verdict

Answer:

"If a developer installed this environment today, how quickly could they become productive?"

---

Remember:

Audit the installed environment.

Not the source repositories.

Not the development ecosystem.

Not the author's intended architecture.

Only what is actually present inside the active virtual environment.

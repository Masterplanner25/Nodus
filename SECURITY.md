Security Policy
Supported Versions

Nodus is currently in early development.

Security fixes will be applied to the latest version only.

Version	Supported
Latest	✅
Older versions	❌
Reporting a Vulnerability

If you discover a security vulnerability, please do not open a public issue immediately.

Instead:

Email the maintainer or open a private security report through GitHub.

Provide as much information as possible.

Include:

Description of the vulnerability

Steps to reproduce

Potential impact

Suggested mitigation if known

What Qualifies as a Security Issue

Examples include:

Arbitrary code execution through the runtime

Unsafe file system access

Sandbox escapes (if applicable)

Memory or VM state corruption

Unsafe interpreter behavior

General bugs or crashes should be reported through normal GitHub issues.

Responsible Disclosure

Once a vulnerability is reported:

It will be investigated

A fix will be developed

A patch release will be published

Contributors who report vulnerabilities responsibly will be credited where appropriate.

Security Philosophy

Nodus prioritizes:

predictable runtime behavior

explicit execution semantics

minimal hidden side effects

Because Nodus executes code, careful review of runtime and VM behavior is important.
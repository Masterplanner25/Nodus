File one or more GitHub issues for the Nodus project (Masterplanner25/Nodus).

Arguments: $ARGUMENTS
(Pass a brief description, or nothing — the command will prompt for details.)

## Steps

1. **Determine the next BUG number** by checking the highest existing issue
   number on GitHub via the API:

   ```python
   import urllib.request, json
   # GET /repos/Masterplanner25/Nodus/issues?state=all&per_page=1&sort=created&direction=desc
   # Read the number field from the first result
   ```

2. **Gather issue details** (if not already provided in $ARGUMENTS):
   - BUG-NNN title (short, imperative)
   - Subsystem: one of `cli`, `runtime`, `compiler`, `lexer`, `parser`,
     `vm`, `stdlib`, `embedding`, `repl`, `lsp`, `dap`, `server`, `docs`
   - Severity: `critical`, `high`, `medium`, `low`, `cosmetic`
   - Summary, reproduction steps, expected behavior, fix direction,
     affected versions

3. **Write a Python script to a temp file** — do not use inline heredocs:

   ```python
   import urllib.request, json

   token = '<token from git credential fill>'
   headers = {
       'Accept': 'application/vnd.github+json',
       'Authorization': f'Bearer {token}',
       'X-GitHub-Api-Version': '2022-11-28',
       'User-Agent': 'nodus-dev',
       'Content-Type': 'application/json'
   }

   issues = [
       {
           'title': 'BUG-NNN: description',
           'body': (
               "## Summary\n\n...\n\n"
               "## Reproduction\n\n```\n...\n```\n\n"
               "## Expected behavior\n\n...\n\n"
               "## Fix direction\n\n...\n\n"
               "## Affected versions\n\nv2.1.1 (current). Likely all prior versions."
           ),
           'labels': ['bug', 'subsystem:X', 'severity:Y'],
           'milestone': None   # always — milestones are not used
       }
   ]

   for issue in issues:
       body = json.dumps(issue).encode()
       req = urllib.request.Request(
           'https://api.github.com/repos/Masterplanner25/Nodus/issues',
           data=body, headers=headers, method='POST'
       )
       with urllib.request.urlopen(req) as r:
           created = json.loads(r.read())
           print(f'#{created["number"]} {created["title"]}')
   ```

4. **Get the token**:
   ```bash
   git credential fill <<< $'protocol=https\nhost=github.com'
   ```

5. **Run the script** and report the created issue numbers and URLs.

6. **Update CHANGELOG.md** — add a one-line entry under `[Unreleased]` in
   the appropriate section (Bug, or a new subsection if needed).

## Labels reference

- Subsystem: `subsystem:cli`, `subsystem:runtime`, `subsystem:compiler`,
  `subsystem:lexer`, `subsystem:parser`, `subsystem:vm`, `subsystem:stdlib`,
  `subsystem:embedding`, `subsystem:repl`, `subsystem:lsp`, `subsystem:dap`,
  `subsystem:server`, `subsystem:docs`
- Severity: `severity:critical`, `severity:high`, `severity:medium`,
  `severity:low`, `severity:cosmetic`
- Always include `bug` as the first label

## Milestone — none, always

**Do not assign a milestone and do not create one.** Decided 2026-08-26; all
eleven are closed. Pass `'milestone': None`.

They were never doing the job the name suggests: at the moment of the decision
**zero of the 45 open issues carried one**, and the last milestone created was
`v5.0` — 5.0.1 through 5.5.0 all shipped without any. Release scope lives in
`CHANGELOG.md`'s `[Unreleased]` section, which the release process reads and
`nodus_gate --closed-issues` drives off.

What an issue *does* need is the label set above: `bug` where it applies, a
`subsystem:`, and a `severity:`. Those are what triage actually reads.

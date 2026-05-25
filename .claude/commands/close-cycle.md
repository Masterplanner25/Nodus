Close out a completed Nodus release cycle: add resolution comments to issues
that lack them, close any remaining open issues, close the milestone, and
verify counts.

Arguments: $ARGUMENTS
(Pass the version string, e.g. `3.0.1`, and optionally the milestone number.
If the milestone number is omitted, look it up from the open/closed milestone
list.)

## Step 1 — Identify the milestone

Get the token:
```bash
git credential fill <<< $'protocol=https\nhost=github.com'
```

List milestones to confirm the target:
```python
import urllib.request, json

token = '<token>'
headers = {
    'Accept': 'application/vnd.github+json',
    'Authorization': f'Bearer {token}',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'nodus-dev',
}

req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/milestones?state=all&per_page=20',
    headers=headers
)
with urllib.request.urlopen(req) as r:
    milestones = json.loads(r.read())
for m in milestones:
    print(m['number'], m['title'], m['state'], m['open_issues'], 'open')
```

Confirm the milestone number matches the target version before proceeding.

## Step 2 — List all issues in the milestone

```python
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/issues?milestone=N&state=all&per_page=100',
    headers=headers
)
with urllib.request.urlopen(req) as r:
    issues = json.loads(r.read())
for i in issues:
    print(i['number'], i['state'], i['title'])
```

For each issue, check whether it already has a resolution comment (look for
a comment containing "Resolved in v").

## Step 3 — Add resolution comments to issues that lack them

For each issue without a resolution comment, POST:

```python
comment_body = "Resolved in vX.Y.Z — <one sentence describing the fix>."
# POST /repos/Masterplanner25/Nodus/issues/N/comments  {"body": comment_body}
```

Comment shape: one sentence, past tense, specific. "Fixed by stripping the
.nd extension before building the error path list" not "Fixed."

Write the script to a temp file and run it — do not inline heredocs.

## Step 4 — Close any remaining open issues

For each issue still open:

```python
# PATCH /repos/Masterplanner25/Nodus/issues/N  {"state": "closed"}
```

## Step 5 — Close the milestone

```python
body = json.dumps({"state": "closed"}).encode()
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/milestones/N',
    data=body, headers={**headers, 'Content-Type': 'application/json'}, method='PATCH'
)
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read())
    print(result['state'], result['open_issues'], 'open')
```

## Step 6 — Verify

```python
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/milestones/N',
    headers=headers
)
with urllib.request.urlopen(req) as r:
    m = json.loads(r.read())
assert m['open_issues'] == 0, f"Expected 0 open, got {m['open_issues']}"
print(f"Milestone '{m['title']}': {m['closed_issues']} closed, 0 open. State: {m['state']}")
```

## Post-close checklist

- [ ] Milestone shows 0 open issues on GitHub
- [ ] Milestone state is `closed`
- [ ] Every issue has a resolution comment
- [ ] `CHANGELOG.md` `[Unreleased]` is empty (ready for next cycle)

Transition open issues from a superseded milestone to a new one, then close
the old milestone. Use this when a milestone is folded into a larger cycle
rather than completed normally (e.g. v3.1 superseded by v4.0).

Arguments: $ARGUMENTS
(Pass "SOURCE_TITLE -> TARGET_TITLE", e.g. `v3.1 -> v4.0`. Optionally append
label changes as `+add-label` or `-remove-label`.)

## Step 1 — Identify source and target milestones

Get the token:
```bash
git credential fill <<< $'protocol=https\nhost=github.com'
```

List all milestones to confirm numbers:
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

Note the milestone numbers for SOURCE and TARGET before proceeding.

## Step 2 — List open issues in the source milestone

```python
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/issues?milestone=SOURCE_NUM&state=open&per_page=100',
    headers=headers
)
with urllib.request.urlopen(req) as r:
    issues = json.loads(r.read())
for i in issues:
    print(i['number'], i['title'], [l['name'] for l in i['labels']])
```

Print the full list and confirm with the user before making any changes.

## Step 3 — Create the target milestone if it doesn't exist

Only if the target milestone is missing:
```python
body = json.dumps({
    'title': 'vX.Y',
    'description': 'One-line description of this cycle.',
}).encode()
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/milestones',
    data=body, headers={**headers, 'Content-Type': 'application/json'}, method='POST'
)
with urllib.request.urlopen(req) as r:
    m = json.loads(r.read())
    print(f"Created #{m['number']} '{m['title']}'")
```

## Step 4 — Move issues to the target milestone

Write the script to a temp file and run it — do not inline heredocs.

```python
TARGET_MILESTONE = <TARGET_NUM>
LABEL_ADD = []      # labels to add to every issue, e.g. ['tier:2-enhancement']
LABEL_REMOVE = []   # labels to remove, e.g. ['phase:1-design']

for issue in issues:
    number = issue['number']
    current_labels = [l['name'] for l in issue['labels']]
    new_labels = list(set(current_labels + LABEL_ADD) - set(LABEL_REMOVE))

    patch = json.dumps({
        'milestone': TARGET_MILESTONE,
        'labels': new_labels,
    }).encode()
    req = urllib.request.Request(
        f'https://api.github.com/repos/Masterplanner25/Nodus/issues/{number}',
        data=patch, headers={**headers, 'Content-Type': 'application/json'}, method='PATCH'
    )
    with urllib.request.urlopen(req) as r:
        updated = json.loads(r.read())
        print(f"  #{updated['number']} → milestone {updated['milestone']['title']}, labels: {[l['name'] for l in updated['labels']]}")
```

## Step 5 — Close the source milestone

```python
body = json.dumps({'state': 'closed'}).encode()
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/milestones/SOURCE_NUM',
    data=body, headers={**headers, 'Content-Type': 'application/json'}, method='PATCH'
)
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read())
    print(f"Source milestone '{result['title']}': {result['state']}, {result['open_issues']} open remaining")
```

## Step 6 — Verify

```python
for num, label in [(SOURCE_NUM, 'source'), (TARGET_NUM, 'target')]:
    req = urllib.request.Request(
        f'https://api.github.com/repos/Masterplanner25/Nodus/milestones/{num}',
        headers=headers
    )
    with urllib.request.urlopen(req) as r:
        m = json.loads(r.read())
    print(f"{label}: '{m['title']}' {m['state']} — {m['open_issues']} open, {m['closed_issues']} closed")
```

Expected: source is `closed` with 0 open issues; target shows the moved issues.

## Post-transition checklist

- [ ] Source milestone is `closed` with 0 open issues
- [ ] Target milestone exists and contains the moved issues
- [ ] Label changes applied correctly on every moved issue
- [ ] `V4_0_PLAN.md` (or equivalent cycle plan) updated to list absorbed issues
- [ ] `CHANGELOG.md` note added if the transition is user-visible

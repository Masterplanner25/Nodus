"""`workflow_wait(event, {schema: ...})`: the resume payload is typed (#472).

The routing half was already right — a waiting run records `step` and `task_id`,
so the response is tied to the node that asked, and `resume_workflow` already
refuses a mismatched `event_type` or `correlation_key`. What was missing was any
statement of what the payload should *contain*: a resuming caller could hand a
waiting step anything, and the step found out by failing somewhere later.

Two things worth knowing about the shape, both decided in
`docs/design/workflow-dsl/00-cluster-decisions.md` D3:

- **Argument 2 type-dispatches.** The issue assumed a free positional slot;
  there was none, all four were named. A **string** is `correlation_key` as it
  always was, a **map** is an options map. That caps positional growth instead of
  adding a fifth argument to a signature that was one option from unwritable.
- **An unspecified schema accepts anything.** Every wait written before this
  declares nothing, so any other reading would make the feature a nuisance.

The schema is normalised and refused at the **wait site**, not at the resume: a
declaration nobody validated until someone tried to use it is the
declared-but-not-enforced shape this cluster keeps removing.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

FLOW = """
workflow w {
    step a { return workflow_wait("approval", %(wait)s) }
    step b after a { return "b saw \\(workflow_resume_payload())" }
}
fn main() {
    let r = run_workflow(w)
    print("STATUS=\\(r["status"])")
    let out = resume_workflow(r["graph_id"], nil, %(payload)s)
    print("RESUME=\\(out)")
}
"""

SCHEMA = '{schema: {approved: "bool", note: "string"}}'


def _run(source: str) -> str:
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            result = NodusRuntime(timeout_ms=None).run_source(source)
        finally:
            os.chdir(cwd)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


class DeclaredSchemaTests(unittest.TestCase):
    # closes: #472
    def test_a_mismatched_payload_is_refused_at_the_resume_call(self):
        """The failure lands on the caller that sent the wrong thing.

        Not inside the step that trusted it — which is the whole point, and why
        the check sits beside the event-type and correlation refusals rather than
        in the step body.
        """
        out = _run(FLOW % {"wait": SCHEMA, "payload": '{approved: "yes", note: "ok"}'})
        self.assertIn('"ok": false', out)
        self.assertIn("argument 'approved' must be a boolean", out)
        # and the waiting step never resumed
        self.assertNotIn("b saw", out)

    def test_a_missing_field_is_refused(self):
        out = _run(FLOW % {"wait": SCHEMA, "payload": "{approved: true}"})
        self.assertIn('"ok": false', out)
        self.assertIn("missing required argument: 'note'", out)

    def test_a_matching_payload_resumes(self):
        out = _run(FLOW % {"wait": SCHEMA, "payload": '{approved: true, note: "ok"}'})
        self.assertIn("b saw", out)
        self.assertNotIn('"ok": false', out)

    def test_the_declared_shape_names_itself_in_the_error(self):
        """A caller that sent the wrong thing should not have to read the source."""
        out = _run(FLOW % {"wait": SCHEMA, "payload": "{approved: true}"})
        self.assertIn("'approval' declares {approved, note}", out)


class CompatibilityTests(unittest.TestCase):
    def test_no_schema_accepts_anything(self):
        """Every wait written before #472 declares nothing and must be untouched."""
        out = _run(FLOW % {"wait": "nil", "payload": "{whatever: 1i}"})
        self.assertIn("b saw", out)

    def test_argument_two_as_a_string_is_still_the_correlation_key(self):
        out = _run(
            'workflow w { step a { return workflow_wait("approval", "order-42") } }\n'
            'fn main() { let r = run_workflow(w); print("W=\\(r["wait"])") }\n'
        )
        self.assertIn('"correlation_key": "order-42"', out)


class RefusedAtTheWaitSiteTests(unittest.TestCase):
    """Refused where the mistake is, rather than when someone tries to resume."""

    def _error(self, wait: str) -> str:
        out = _run(
            "workflow w { step a { return workflow_wait(\"approval\", %s) } }\n"
            'fn main() { let r = run_workflow(w); print("E=\\(r["error"])") }\n' % wait
        )
        return out

    def test_an_unknown_option_is_refused(self):
        self.assertIn("unknown option(s) 'schemaa'", self._error('{schemaa: {a: "bool"}}'))

    def test_an_unknown_type_name_is_refused(self):
        """`boolean` is JSON Schema's spelling; the Nodus name is `bool`."""
        self.assertIn("unknown type 'boolean'", self._error('{schema: {approved: "boolean"}}'))

    def test_mixing_the_map_form_with_positional_arguments_is_refused(self):
        """Two ways of saying the same thing, with no rule for disagreement."""
        out = _run(
            'workflow w { step a { return workflow_wait("approval", {schema: {a: "bool"}}, {x: 1i}) } }\n'
            'fn main() { let r = run_workflow(w); print("E=\\(r["error"])") }\n'
        )
        self.assertIn("takes the options map alone", out)


class TheWaitVocabularyIsCarriedEverywhereTests(unittest.TestCase):
    def test_the_schema_reaches_the_persisted_wait_record(self):
        """Source-adjacent guard for the bug this feature hit while being built.

        The wait is rebuilt field-by-field in `_workflow_wait_info` rather than
        passed through, so `schema` was silently dropped between the step and the
        store on the first pass — the run waited, the resume validated nothing,
        and every test that only checked "a good payload resumes" still passed.
        Asserting the schema is *visible on the waiting result* is what catches
        that, because it fails on a drop even when the happy path works.
        """
        out = _run(
            'workflow w { step a { return workflow_wait("approval", %s) } }\n'
            'fn main() { let r = run_workflow(w); print("W=\\(r["wait"])") }\n' % SCHEMA
        )
        self.assertIn('"schema"', out)
        self.assertIn('"required": ["approved", "note"]', out)


if __name__ == "__main__":
    unittest.main()

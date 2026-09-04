"""Walking the VM call chain.

One question — *which VM is the root of this call?* — answered in one place
(#751). It was answered privately in four builtin modules, byte-identical, with
`test_module`'s copy documented as a copy of `tool_module`'s.

Deliberately importing nothing. `nodus.vm.vm` imports `nodus.builtins` at module
level, so a builtin cannot import the VM back without a cycle — `tool_module`
already reaches for `VM` inside a function body for exactly that reason. A helper
that touches only `getattr` needs no imports at all, which keeps it importable
from anywhere.
"""

from __future__ import annotations


def root_vm(vm):
    """Follow the `_caller_vm` chain to the root VM.

    `NodusModule.invoke_function()` creates a fresh child VM per call and sets
    `child._caller_vm = caller_vm`. Stdlib builtins (tool, test, …) close over
    whichever VM was current at registration time — and since stdlib methods are
    always called via `invoke_function`, that closing VM is a child, not the
    root. This traversal is what makes a builtin mutate the root VM's shared
    state rather than a per-call child that is about to be discarded.

    That explanation lived beside one of the four copies. It is the load-bearing
    part: without it the walk looks like defensive `getattr` noise, and the next
    reader deletes it or writes a fifth one.
    """
    root = vm
    while True:
        parent = getattr(root, "_caller_vm", None)
        if parent is None:
            return root
        root = parent

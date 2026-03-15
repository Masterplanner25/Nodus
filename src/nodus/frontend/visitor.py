"""NodeVisitor base class for AST traversal in Nodus.

All AST walkers (module stamping, info collection, analysis) should extend
NodeVisitor to benefit from the consistent dispatch mechanism.

Adding a new AST node type
--------------------------
When a new node type is added to ast_nodes.py, every NodeVisitor subclass
that handles the node's syntactic category *must* add a corresponding
``visit_<ClassName>`` method.  Failing to do so will cause
``NotImplementedError`` to be raised at runtime when the visitor encounters
an instance of the new node.  This is intentional — it surfaces missing
visitor coverage early rather than silently skipping nodes.
"""


class NodeVisitor:
    """Abstract AST visitor with automatic method dispatch.

    Subclasses implement ``visit_<ClassName>`` methods for each node type
    they handle.  The :meth:`visit` method routes to the correct handler
    based on the runtime type of the node.

    If no ``visit_<ClassName>`` method is found, :meth:`visit_default` is
    called.  The default implementation raises ``NotImplementedError``;
    subclasses that need generic/fallback behaviour (e.g. the
    :class:`~nodus.tooling.loader.ModuleStamper`) should override it.
    """

    def visit(self, node):
        """Dispatch *node* to the appropriate ``visit_<ClassName>`` method."""
        if node is None:
            return None
        method_name = f"visit_{type(node).__name__}"
        method = getattr(self, method_name, None)
        if method is None:
            return self.visit_default(node)
        return method(node)

    def visit_default(self, node):
        """Called when no specific visitor method exists for *node*'s type.

        Raises ``NotImplementedError`` by default.  Override in subclasses
        that require generic fallback behaviour.
        """
        raise NotImplementedError(
            f"{type(self).__name__} has no visitor method for "
            f"{type(node).__name__}.  Add a visit_{type(node).__name__} "
            f"method or override visit_default()."
        )

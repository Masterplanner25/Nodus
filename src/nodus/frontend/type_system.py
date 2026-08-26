"""Static type helpers for Nodus."""


class NodusType:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other) -> bool:
        return isinstance(other, NodusType) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return self.name


class FunctionType(NodusType):
    def __init__(self, params: list[NodusType], return_type: NodusType):
        super().__init__("function")
        self.params = params
        self.return_type = return_type

    def __repr__(self) -> str:
        params = ", ".join(param.name for param in self.params)
        return f"function({params}) -> {self.return_type.name}"


ANY = NodusType("any")
INT = NodusType("int")
FLOAT = NodusType("float")
STRING = NodusType("string")
BOOL = NodusType("bool")
LIST = NodusType("list")
MAP = NodusType("map")
RECORD = NodusType("record")
FUNCTION = NodusType("function")
NIL = NodusType("nil")

# The spellable type vocabulary. **This is the set, named once** (#609): the
# parser validates against it, `nodus check` and the editor diagnostics report
# against it, and a name added here becomes spellable everywhere at once.
#
# It was smaller and quietly wrong before #609. `map` was missing while looking
# nameable — `fn f(y: map)` checked clean and meant `any` — and `record` was in
# here but is a keyword, so `-> record` was `Expected identifier, got 'record'`:
# a dead entry. Both are reachable now; see `parser.parse_type_name`.
TYPE_NAMES = {
    "any": ANY,
    "int": INT,
    "float": FLOAT,
    "string": STRING,
    "bool": BOOL,
    "list": LIST,
    "map": MAP,
    "record": RECORD,
    "function": FUNCTION,
    "nil": NIL,
}


def is_known_type_name(name: str) -> bool:
    """Is `name` a type this checker can mean anything by?

    The parser asks before accepting an annotation. Do not inline a membership
    test against `TYPE_NAMES` at a call site — that is how the two ended up
    disagreeing in the first place.
    """
    return name in TYPE_NAMES


def suggest_type_name(name: str) -> str | None:
    """Closest real type name to `name`, or None. Same mechanism as #490's."""
    import difflib

    match = difflib.get_close_matches(name, list(TYPE_NAMES), n=1, cutoff=0.6)
    return match[0] if match else None


def parse_type_name(name: str | None) -> NodusType:
    if name is None:
        return ANY
    # Still tolerant: an unknown name degrades to ANY rather than crashing the
    # checker. The *diagnostic* is the parser's job (#609), because only it has
    # the token to point at. Until 6.0.0 an unknown name is a warning, so this
    # has to keep producing something.
    return TYPE_NAMES.get(name, ANY)


def is_assignable(expected: NodusType, actual: NodusType) -> bool:
    if expected == ANY or actual == ANY:
        return True
    if expected == FLOAT and actual == INT:
        return True
    if expected == FUNCTION and isinstance(actual, FunctionType):
        return True
    # `map` and `record` are one static type today: the analyzer infers RECORD
    # for a map literal as well as a record literal, so a checker that told them
    # apart would reject correct code. They are spelled separately because both
    # words are real in the language and a user writes whichever they mean; when
    # the inference side learns the difference, delete this line and the two
    # names part company on their own.
    if {expected, actual} == {MAP, RECORD}:
        return True
    return expected == actual


def combine_types(left: NodusType, right: NodusType) -> NodusType:
    if left == right:
        return left
    if left == ANY or right == ANY:
        return ANY
    if (left == INT and right == FLOAT) or (left == FLOAT and right == INT):
        return FLOAT
    return ANY

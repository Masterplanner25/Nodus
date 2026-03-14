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
RECORD = NodusType("record")
FUNCTION = NodusType("function")
NIL = NodusType("nil")

TYPE_NAMES = {
    "any": ANY,
    "int": INT,
    "float": FLOAT,
    "string": STRING,
    "bool": BOOL,
    "list": LIST,
    "record": RECORD,
    "function": FUNCTION,
}


def parse_type_name(name: str | None) -> NodusType:
    if name is None:
        return ANY
    return TYPE_NAMES.get(name, ANY)


def is_assignable(expected: NodusType, actual: NodusType) -> bool:
    if expected == ANY or actual == ANY:
        return True
    if expected == FLOAT and actual == INT:
        return True
    if expected == FUNCTION and isinstance(actual, FunctionType):
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

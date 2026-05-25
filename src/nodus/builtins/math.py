"""Math builtin functions for the Nodus VM."""

import math as _math
import random


def register(vm, registry) -> None:
    """Register numeric/math builtins onto the registry."""

    def builtin_math_abs(value):
        return abs(vm.ensure_number(value, "math_abs(x)"))

    def builtin_math_min(a, b):
        vm.ensure_number(a, "math_min(a, b)")
        vm.ensure_number(b, "math_min(a, b)")
        return min(a, b)

    def builtin_math_max(a, b):
        vm.ensure_number(a, "math_max(a, b)")
        vm.ensure_number(b, "math_max(a, b)")
        return max(a, b)

    def builtin_math_floor(value):
        return float(_math.floor(vm.ensure_number(value, "math_floor(x)")))

    def builtin_math_ceil(value):
        return float(_math.ceil(vm.ensure_number(value, "math_ceil(x)")))

    def builtin_math_sqrt(value):
        number = vm.ensure_number(value, "math_sqrt(x)")
        if number < 0:
            vm.runtime_error("runtime", "math_sqrt(x) expects a non-negative number")
        return _math.sqrt(number)

    def builtin_math_random():
        return random.random()

    def builtin_math_parse_int(s):
        vm.ensure_string(s, "math.parse_int(s)")
        try:
            return int(s)
        except ValueError:
            return vm.make_err("parse_error", f'not an integer: "{s}"')

    def builtin_math_to_int(n):
        vm.ensure_number(n, "math.to_int(n)")
        if isinstance(n, int) and not isinstance(n, bool):
            return n
        if _math.isnan(n) or _math.isinf(n):
            return 0
        return int(n)

    def builtin_math_to_float(n):
        vm.ensure_number(n, "math.to_float(n)")
        return float(n)

    def builtin_math_is_int(n):
        if isinstance(n, bool):
            return False
        return isinstance(n, int)

    def builtin_math_idiv(a, b):
        a_is_int = isinstance(a, int) and not isinstance(a, bool)
        b_is_int = isinstance(b, int) and not isinstance(b, bool)
        if not a_is_int and not b_is_int:
            return vm.make_err("type_error", "math.idiv requires int args, got float and float")
        if not a_is_int:
            return vm.make_err("type_error", "math.idiv requires int args, got float")
        if not b_is_int:
            return vm.make_err("type_error", "math.idiv requires int args, got int and float")
        if b == 0:
            return vm.make_err("math_error", "division by zero")
        # Truncation toward zero (C/Java semantics, not Python floor division)
        result = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            result = -result
        return result

    registry.add("math_abs", 1, builtin_math_abs)
    registry.add("math_min", 2, builtin_math_min)
    registry.add("math_max", 2, builtin_math_max)
    registry.add("math_floor", 1, builtin_math_floor)
    registry.add("math_ceil", 1, builtin_math_ceil)
    registry.add("math_sqrt", 1, builtin_math_sqrt)
    registry.add("math_random", 0, builtin_math_random)
    registry.add("math_parse_int", 1, builtin_math_parse_int)
    registry.add("math_to_int", 1, builtin_math_to_int)
    registry.add("math_to_float", 1, builtin_math_to_float)
    registry.add("math_is_int", 1, builtin_math_is_int)
    registry.add("math_idiv", 2, builtin_math_idiv)

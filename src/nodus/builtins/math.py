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

    registry.add("math_abs", 1, builtin_math_abs)
    registry.add("math_min", 2, builtin_math_min)
    registry.add("math_max", 2, builtin_math_max)
    registry.add("math_floor", 1, builtin_math_floor)
    registry.add("math_ceil", 1, builtin_math_ceil)
    registry.add("math_sqrt", 1, builtin_math_sqrt)
    registry.add("math_random", 0, builtin_math_random)

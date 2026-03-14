import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import nodus as lang
code = """
let count = 0
let A = task(fn() {
    if (count == 0) {
        count = 1
        throw "fail"
    }
    return 5
}, { "retries": 2, "retry_delay_ms": 5 })
let result = run_graph([A])
print(result)
"""
_ast, code, functions, code_locs = lang.compile_source(code, source_path='main.nd', import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None})
vm = lang.VM(code, functions, code_locs=code_locs, source_path='main.nd')
vm.run()

import sys, os, threading, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import nodus as lang
from server import WorkerManager
from task_graph import set_default_dispatcher
wm = WorkerManager()
set_default_dispatcher(wm)
wm.register()
code = """
let A = task(fn() { return 5 }, nil)
let result = run_graph([A])
"""
_ast, code_b, functions, code_locs = lang.compile_source(code, source_path='main.nd', import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None})
vm = lang.VM(code_b, functions, code_locs=code_locs, source_path='main.nd')
vm.worker_dispatcher = wm

def run():
    vm.run()

t = threading.Thread(target=run)
t.start()
for i in range(20):
    job = wm.poll('w_1')
    print('job', job)
    if job.get('job_id'):
        wm.result('w_1', job['job_id'], 'execute')
        break
    time.sleep(0.05)

t.join(2)

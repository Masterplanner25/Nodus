"""FastAPI execution service for Nodus runner functions."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nodus.tooling.runner import (
    agent_call_result,
    build_ast,
    check_source,
    disassemble_source,
    memory_delete_result,
    memory_get_result,
    memory_keys_result,
    memory_put_result,
    plan_graph_source,
    resume_graph,
    run_source,
    tool_call_result,
)
from nodus.orchestration.task_graph import latest_graph_state, load_graph_state


class ExecutionState:
    def __init__(self):
        self.last_vm = None

    def _graph_metadata(self, vm, graph_id: str | None = None) -> dict:
        resolved_id = graph_id
        if resolved_id is None and vm is not None and getattr(vm, "last_graph_plan", None):
            resolved_id = vm.last_graph_plan.get("graph_id")

        if resolved_id is None:
            resolved_id, state = latest_graph_state()
        else:
            state = load_graph_state(resolved_id)

        tasks = state.get("tasks", {}) if state else {}
        status = state.get("status") if state else None
        return {"graph_id": resolved_id, "tasks": tasks, "graph_status": status}

    def execute(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        result, vm = run_source(code, filename=filename)
        self.last_vm = vm
        return result

    def check(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        return check_source(code, filename=filename)

    def ast(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        compact = bool(payload.get("compact", False))
        return build_ast(code, filename=filename, compact=compact)

    def disassemble(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        return disassemble_source(code, filename=filename)

    def plan_graph(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        result, vm = plan_graph_source(code, filename=filename)
        self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("plan", {}).get("graph_id")))
        return result

    def resume_graph(self, payload: dict) -> dict:
        graph_id = payload.get("graph_id")
        if self.last_vm is not None:
            from nodus.tooling.runner import resume_graph_in_vm
            result, vm = resume_graph_in_vm(self.last_vm, graph_id)
        else:
            result, vm = resume_graph(graph_id)
        self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, graph_id))
        return result

    def graph_run(self, payload: dict) -> dict:
        code = payload.get("code", "")
        filename = payload.get("filename")
        result, vm = run_source(code, filename=filename)
        self.last_vm = vm
        result.update(self._graph_metadata(vm))
        return result

    def graph_plan(self, payload: dict) -> dict:
        return self.plan_graph(payload)

    def graph_resume(self, payload: dict) -> dict:
        return self.resume_graph(payload)

    def runtime_events(self) -> dict:
        vm = self.last_vm
        events = [event.to_dict() for event in vm.event_bus.events()] if vm is not None else []
        return {"ok": True, "events": events}

    def tool_call(self, payload: dict) -> dict:
        return tool_call_result(payload.get("name"), payload.get("args", {}), vm=self.last_vm)

    def agent_call(self, payload: dict) -> dict:
        return agent_call_result(payload.get("name"), payload.get("payload"), vm=self.last_vm)

    def memory_get(self, key: str | None = None) -> dict:
        if key is None:
            return memory_keys_result(vm=self.last_vm)
        return memory_get_result(key, vm=self.last_vm)

    def memory_put(self, payload: dict) -> dict:
        return memory_put_result(payload.get("key"), payload.get("value"), vm=self.last_vm)

    def memory_delete(self, key: str) -> dict:
        return memory_delete_result(key, vm=self.last_vm)


def create_app(state: ExecutionState | None = None) -> FastAPI:
    state = state or ExecutionState()
    app = FastAPI()

    @app.post("/execute")
    async def execute(request: Request):
        payload = await request.json()
        return JSONResponse(state.execute(payload))

    @app.post("/check")
    async def check(request: Request):
        payload = await request.json()
        return JSONResponse(state.check(payload))

    @app.post("/ast")
    async def ast(request: Request):
        payload = await request.json()
        return JSONResponse(state.ast(payload))

    @app.post("/disassemble")
    async def disassemble(request: Request):
        payload = await request.json()
        return JSONResponse(state.disassemble(payload))

    @app.post("/dis")
    async def dis(request: Request):
        payload = await request.json()
        return JSONResponse(state.disassemble(payload))

    @app.post("/plan_graph")
    async def plan_graph(request: Request):
        payload = await request.json()
        return JSONResponse(state.plan_graph(payload))

    @app.post("/resume_graph")
    async def resume_graph_endpoint(request: Request):
        payload = await request.json()
        return JSONResponse(state.resume_graph(payload))

    @app.post("/graph/run")
    async def graph_run(request: Request):
        payload = await request.json()
        return JSONResponse(state.graph_run(payload))

    @app.post("/graph/plan")
    async def graph_plan(request: Request):
        payload = await request.json()
        return JSONResponse(state.graph_plan(payload))

    @app.post("/graph/resume")
    async def graph_resume(request: Request):
        payload = await request.json()
        return JSONResponse(state.graph_resume(payload))

    @app.get("/runtime/events")
    async def runtime_events():
        return JSONResponse(state.runtime_events())

    @app.post("/tool/call")
    async def tool_call(request: Request):
        payload = await request.json()
        return JSONResponse(state.tool_call(payload))

    @app.post("/agent/call")
    async def agent_call(request: Request):
        payload = await request.json()
        return JSONResponse(state.agent_call(payload))

    @app.get("/memory")
    async def memory(key: str | None = None):
        return JSONResponse(state.memory_get(key))

    @app.post("/memory")
    async def memory_put(request: Request):
        payload = await request.json()
        return JSONResponse(state.memory_put(payload))

    @app.delete("/memory/{key}")
    async def memory_delete(key: str):
        return JSONResponse(state.memory_delete(key))

    return app

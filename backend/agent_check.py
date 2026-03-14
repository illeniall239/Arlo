import sys
print("Python:", sys.version)
try:
    from app.services.agent_runner import _build_tools
    t = _build_tools()
    print("OK — tools:", [fd.name for fd in t.function_declarations])
except Exception as e:
    print("FAIL:", e)
    import traceback; traceback.print_exc()

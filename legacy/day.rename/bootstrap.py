"""Community source entry point; never downloads or installs dependencies."""
import importlib.util
import json
import sys

NAME = 'day.rename'
MISSING = [name for name in ("tkinter", "PIL", "customtkinter") if importlib.util.find_spec(name) is None]
if sys.version_info < (3, 12):
    MISSING.insert(0, "Python 3.12+")

if MISSING:
    text = "需要 Python 3.12+（含 Tcl/Tk）、Pillow 和 CustomTkinter。请按插件 README 安装 requirements.txt；缺少：" + ", ".join(MISSING)
    if "--standalone" in sys.argv:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "插件依赖未就绪", 0)
        raise SystemExit(1)
    if "--self-test" in sys.argv:
        print(json.dumps({"ok": False, "error": text}, ensure_ascii=False), flush=True)
        raise SystemExit(1)
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            method = request.get("method")
            if method == "initialize":
                result = {"protocolVersion": "1", "name": NAME}
            elif method in ("query", "action"):
                print(json.dumps({"jsonrpc": "2.0", "method": "winshun/notify", "params": {"text": text}}, ensure_ascii=False), flush=True)
                result = {"items": [{"id": "dependencies", "title": "请先安装插件依赖", "subtitle": text, "valid": False}]} if method == "query" else {"effects": [{"type": "notify", "text": text}]}
            elif method == "shutdown":
                result = {}
            else:
                result = {}
            if "id" in request:
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}, ensure_ascii=False), flush=True)
            if method == "shutdown":
                break
        except (ValueError, TypeError):
            continue
else:
    from main import main
    main()

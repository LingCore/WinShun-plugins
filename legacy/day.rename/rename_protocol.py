"""Resident JSON-RPC reader; UI work is posted to the Tk main-thread queue."""
import json
import threading


def serve(stream_in, stream_out, post):
    lock = threading.Lock()

    def send(message):
        with lock:
            stream_out.write(json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False) + "\n")
            stream_out.flush()

    for line in stream_in:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        method, request_id = message.get("method"), message.get("id")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            if request_id is not None:
                send({"id": request_id, "error": {"code": -32602, "message": "Invalid params"}})
            continue
        if method == "initialize":
            post(("settings", params.get("settings") or {}))
            if params.get("dataDir"):
                post(("data_dir", params["dataDir"]))
            send({"id": request_id, "result": {"protocolVersion": "1", "name": "day.rename"}})
        elif method == "query":
            # instant command: typing the exact keyword opens the local window.
            post(("show", None))
            send({"id": request_id, "result": {"items": [{
                "id": "open", "title": "打开批量重命名", "subtitle": "本地规则 / 名称预览 / 批量执行",
                "icon": "glyph:U+E8AC"}]}})
        elif method == "action":
            post(("show", None))
            send({"id": request_id, "result": {"effects": [{"type": "hide"}]}})
        elif method == "settingsChanged":
            post(("settings", params.get("settings") or {}))
        elif method == "shutdown":
            send({"id": request_id, "result": {}})
            post(("quit", None))
            return
        elif method != "cancel" and request_id is not None:
            send({"id": request_id, "error": {"code": -32601, "message": "Method not found"}})
    post(("quit", None))

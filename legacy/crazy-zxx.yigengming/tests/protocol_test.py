"""Exercise the actual PowerShell entry and JSON-RPC, with declared job limits."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_job import PluginJob

root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / 'plugin.json').read_text(encoding='utf-8-sig'))
powershell = Path(__import__('os').environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
scratch = root / 'tests/.runs'
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as data:
    started = time.perf_counter()
    process = subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'main.ps1')],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    job = PluginJob(process, manifest['runtime']['memoryMB'], allow_processes=True)
    def rpc(method, params=None, ident=1):
        request = {'jsonrpc':'2.0', 'id':ident, 'method':method, 'params': params or {}}
        process.stdin.write(json.dumps(request, ensure_ascii=False) + '\n')
        process.stdin.flush()
        line = process.stdout.readline()
        assert line, f'PowerShell ended during {method}'
        response = json.loads(line)
        assert response['jsonrpc'] == '2.0' and response['id'] == ident
        return response
    try:
        initialized = rpc('initialize', {'dataDir':data})
        assert initialized['result']['name'] == '易更名'
        startup = (time.perf_counter() - started) * 1000
        assert startup < manifest['runtime']['timeoutMs'], startup
        for command in ['rename', 'create']:
            item = rpc('query', {'command':command, 'text':'D:\\测试目录\\带 空格'}, 2)['result']['items'][0]
            assert item['title'].startswith('易更名') and item['valid']
            assert item['data']['text'] == 'D:\\测试目录\\带 空格'
        assert rpc('cancel', {}, 3)['result'] == {}
        assert rpc('settingsChanged', {}, 4)['result'] == {}
        assert rpc('unknown', {}, 5)['error']['code'] == -32601
        times = []
        for i in range(50):
            start = time.perf_counter()
            assert len(rpc('query', {'command':'rename', 'text':'中文'}, 10+i)['result']['items']) == 1
            times.append((time.perf_counter()-start)*1000)
        assert max(times) < 1500
        assert rpc('shutdown', {}, 99)['result'] == {}
        process.wait(timeout=10)
        assert process.returncode == 0
        print(f'PASS PowerShell entry, initialize/query/cancel/settingsChanged/errors/shutdown, UTF-8, 50 queries; startup={startup:.0f}ms, max-query={max(times):.2f}ms; 512MB job with declared compiler processes')
    finally:
        if process.poll() is None:
            process.kill()
        stdout, stderr = process.communicate(timeout=10)
        job.close()
        if stderr:
            print(stderr)

import pathlib
p = pathlib.Path("tools/probe_online_play.py")
t = p.read_text(encoding="utf-8")
t = t.replace('cache = proxy.local_path(f"{state[\'track\'].source_id}:{state[\'track\'].remote_id}:standard")\n        size = cache.stat().st_size if cache and cache.exists() else -1',
              'cache = Path(proxy.local_path(f"{state[\'track\'].source_id}:{state[\'track\'].remote_id}:standard"))\n        size = cache.stat().st_size if cache.exists() else -1')
p.write_text(t, encoding="utf-8")
print("ok")

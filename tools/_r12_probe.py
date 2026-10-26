import os
import requests, json
URL = os.environ.get("HUSHPLAYER_PROBE_SUBSCRIPTION", "")
r = requests.get(url, timeout=15, headers={"User-Agent": "HushPlayer/1.0.12"})
print(r.status_code, r.headers.get("content-type"), len(r.content))
data = r.json()
print(type(data))
if isinstance(data, dict):
    print(list(data.keys())[:10])
    for key in ("sources", "plugins", "data"):
        if key in data and isinstance(data[key], list):
            print(key, len(data[key]))
            print(json.dumps(data[key][0], ensure_ascii=False)[:500])
            break
elif isinstance(data, list):
    print(len(data))
    print(json.dumps(data[0], ensure_ascii=False)[:500])

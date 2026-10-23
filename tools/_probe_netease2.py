import json, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ids = [33894312, 1330348068]
r = requests.get("https://music.163.com/api/song/detail", params={"ids": json.dumps(ids)}, headers={"User-Agent": UA, "Referer": "https://music.163.com/"}, timeout=15)
print(r.status_code, r.headers.get("content-type"))
d = r.json(); s = (d.get("songs") or [])[0]
print(len(d.get("songs") or []), s.get("name"), [a.get("name") for a in s.get("artists") or []], (s.get("album") or {}).get("name"), s.get("duration"))

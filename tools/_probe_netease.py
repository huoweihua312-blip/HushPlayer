import json, sys, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
url = "https://music.163.com/api/v6/playlist/detail?id=3778678&n=1000&s=0"
r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://music.163.com/"}, timeout=15)
print("status", r.status_code, "bytes", len(r.content))
data = r.json()
pl = data.get("playlist") or {}
print("name", pl.get("name"), "tracks", len(pl.get("tracks") or []), "trackIds", len(pl.get("trackIds") or []))
t = (pl.get("tracks") or [{}])[0]
print("keys", sorted(t.keys())[:14])
print("first", t.get("name"), "|", [(a.get("name")) for a in (t.get("ar") or [])], "|", (t.get("al") or {}).get("name"), "|", t.get("dt"))

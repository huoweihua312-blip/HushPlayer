import requests, sys
url = sys.argv[1]
uas = {
 "default": {},
 "browserish": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36", "Accept": "*/*", "Accept-Encoding": "identity"},
 "hush": {"User-Agent": "HushPlayer/1.0 (Windows 10; desktop music player)", "Accept": "*/*", "Accept-Encoding": "identity"},
}
for name, h in uas.items():
    try:
        r = requests.get(url, headers=h, stream=True, timeout=12)
        print(name, r.status_code, r.headers.get("Content-Type"), len(next(r.iter_content(1024), b"")))
    except Exception as e:
        print(name, "ERR", e)

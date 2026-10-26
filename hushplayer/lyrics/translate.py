"""把外文歌词逐行翻译成中文（用于音源没有自带翻译的情况）。

音源插件大多只返回原文歌词，``tlyric`` 之类的翻译字段通常被丢掉；为了让
「显示翻译」按钮对外文歌曲真正可用，这里提供一层按行翻译：

* 优先使用微软 Edge 的免费翻译接口（先取临时 token，再批量翻译）；
* 失败后退回 Google 的 gtx 接口；
* 再失败退回 MyMemory。

翻译结果按行缓存到 ``cache/lyrics/translations.json``，同一首歌反复播放、
或同一句歌词在别的歌里再次出现时不会重复请求。所有网络调用都在线程池里
执行，绝不阻塞 UI。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Iterable

import requests

from ..core.logging_setup import get_logger
from ..core.paths import data_dir

log = get_logger("lyrics.translate")

TARGET = "zh-Hans"
_TIMEOUT = (5, 15)
_MAX_BATCH = 40
_MAX_CACHE = 6000
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HushPlayer/1.0"

_EDGE_AUTH = "https://edge.microsoft.com/translate/auth"
_EDGE_API = "https://api-edge.cognitive.microsofttranslator.com/translate"
_GOOGLE_API = "https://translate.googleapis.com/translate_a/single"
_MYMEMORY_API = "https://api.mymemory.translated.net/get"

_LATIN = re.compile(r"[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u3040-\u30FF\uAC00-\uD7AF]")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_KANA = re.compile(r"[\u3040-\u30ff]")

_lock = threading.Lock()
_memory: dict[str, str] = {}
_cache_path: Path | None = None
_token: str = ""
_token_at: float = 0.0


def _cache_file() -> Path:
    global _cache_path
    if _cache_path is None:
        _cache_path = data_dir() / "cache" / "lyrics" / "translations.json"
    return _cache_path


def _load_cache() -> None:
    if _memory:
        return
    path = _cache_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and isinstance(value, str):
                _memory[key] = value


def _save_cache() -> None:
    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = dict(list(_memory.items())[-_MAX_CACHE:])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:  # 缓存失败不影响本次翻译
        log.warning("写入翻译缓存失败：%s", exc)


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def needs_translation(text: str) -> bool:
    """只有明显是外文的行才送去翻译，避免把中文歌词重写成机翻。"""

    text = (text or "").strip()
    if not text:
        return False
    if _KANA.search(text):
        # 日文歌词里汉字比例可能很高，但有假名就一定不是中文。
        return True
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if latin == 0:
        return False
    return latin >= max(2, cjk)


def _cached(text: str) -> str:
    with _lock:
        _load_cache()
        return _memory.get(_key(text), "")


def _store(text: str, translated: str) -> None:
    if not translated:
        return
    with _lock:
        _load_cache()
        _memory[_key(text)] = translated


# --------------------------------------------------------------------- 提供方
def _edge_token(force: bool = False) -> str:
    global _token, _token_at
    if _token and not force and time.time() - _token_at < 480:
        return _token
    response = requests.get(_EDGE_AUTH, timeout=_TIMEOUT, headers={"User-Agent": _UA})
    response.raise_for_status()
    token = response.text.strip()
    if not token:
        raise ValueError("edge token empty")
    _token, _token_at = token, time.time()
    return token


def _translate_edge(lines: list[str]) -> list[str]:
    url = f"{_EDGE_API}?api-version=3.0&to={TARGET}"
    body = [{"Text": line} for line in lines]
    headers = {
        "Authorization": f"Bearer {_edge_token()}",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }
    response = requests.post(url, json=body, timeout=_TIMEOUT, headers=headers)
    if response.status_code in (401, 403):
        headers["Authorization"] = f"Bearer {_edge_token(force=True)}"
        response = requests.post(url, json=body, timeout=_TIMEOUT, headers=headers)
    response.raise_for_status()
    payload = response.json()
    out: list[str] = []
    for item in payload:
        translations = (item or {}).get("translations") or []
        out.append(str((translations[0] or {}).get("text") or "").strip() if translations else "")
    return out if len(out) == len(lines) else []


def _translate_google(lines: list[str]) -> list[str]:
    joined = "\n".join(lines)
    params = {"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": joined}
    response = requests.get(
        _GOOGLE_API, params=params, timeout=_TIMEOUT, headers={"User-Agent": _UA}
    )
    response.raise_for_status()
    payload = response.json()
    chunks = payload[0] if isinstance(payload, list) and payload else []
    translated = "".join(str(chunk[0]) for chunk in chunks if chunk and chunk[0])
    rows = translated.split("\n")
    if len(rows) != len(lines):
        return []
    return [row.strip() for row in rows]


def _translate_mymemory(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        response = requests.get(
            _MYMEMORY_API,
            params={"q": line[:480], "langpair": "en|zh-CN"},
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA},
        )
        response.raise_for_status()
        payload = response.json() or {}
        text = str((payload.get("responseData") or {}).get("translatedText") or "").strip()
        out.append(text)
    return out if len(out) == len(lines) else []


# --------------------------------------------------------------------- 对外 api
def translate_lines(lines: Iterable[str]) -> list[str]:
    """按行翻译，返回与输入等长的列表；无法翻译时为空字符串。"""

    rows = list(lines)
    if not rows:
        return []
    result = ["" for _ in rows]
    pending: list[int] = []
    for index, row in enumerate(rows):
        if not needs_translation(row):
            continue
        cached = _cached(row)
        if cached:
            result[index] = cached
        else:
            pending.append(index)

    if not pending:
        return result

    providers = (_translate_edge, _translate_google, _translate_mymemory)
    for start in range(0, len(pending), _MAX_BATCH):
        batch = pending[start : start + _MAX_BATCH]
        texts = [rows[index].strip() for index in batch]
        translated: list[str] = []
        for provider in providers:
            try:
                translated = provider(texts)
            except Exception as exc:  # noqa: BLE001 - 换下一个提供方
                log.debug("翻译提供方 %s 失败：%s", provider.__name__, exc)
                translated = []
            if translated:
                break
        for index, text in zip(batch, translated):
            if text:
                result[index] = text
                _store(rows[index], text)
    _save_cache()
    return result


def clear_cache() -> None:
    with _lock:
        _memory.clear()
    try:
        _cache_file().unlink()
    except OSError:
        pass

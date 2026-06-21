import threading
import time
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()
_MAXSIZE = 256
_DEFAULT_TTL = 30


def build_key(org_id: str, prefix: str, **params: Any) -> str:
    items = sorted((k, str(v)) for k, v in params.items() if v is not None)
    return f"{org_id}:{prefix}:{'&'.join(f'{k}={v}' for k, v in items)}"


def get_cached(key: str) -> Any | None:
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > _DEFAULT_TTL:
            del _cache[key]
            return None
        return value


def set_cached(key: str, value: Any) -> None:
    with _lock:
        _cache[key] = (time.monotonic(), value)
        if len(_cache) > _MAXSIZE:
            sorted_keys = sorted(_cache, key=lambda k: _cache[k][0])
            for k in sorted_keys[: _MAXSIZE // 4]:
                del _cache[k]


def invalidate_org(org_id: str) -> None:
    with _lock:
        keys = [k for k in _cache if k.startswith(f"{org_id}:")]
        for k in keys:
            del _cache[k]


def clear() -> None:
    with _lock:
        _cache.clear()

import os

TESTING = os.environ.get("TESTING") == "1"

if TESTING:

    class _NoopLimiter:
        def limit(self, *args, **kwargs):
            return lambda f: f

    limiter = _NoopLimiter()
else:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

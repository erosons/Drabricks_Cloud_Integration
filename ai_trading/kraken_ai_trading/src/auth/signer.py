import base64
import fcntl
import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

# Shared nonce file — one counter across all processes using the same API key.
# File-locking ensures no two processes ever get the same value, eliminating
# the EAPI:Invalid nonce error that occurs when concurrent REST calls race.
_NONCE_FILE = Path("/tmp/kraken_nonce.dat")


@dataclass
class KrakenAuth:
    api_key: str
    api_secret: str

    def generate_nonce(self) -> str:
        with open(_NONCE_FILE, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            raw = f.read().strip()
            last = int(raw) if raw else 0
            # Always advance: at least last+1, never behind current clock
            nonce = max(last + 1, int(time.time_ns() // 1_000))
            f.seek(0)
            f.truncate()
            f.write(str(nonce))
        return str(nonce)

    def sign(self, urlpath: str, data: dict) -> str:
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data["nonce"]) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()
        mac = hmac.new(base64.b64decode(self.api_secret), message, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    def get_headers(self, urlpath: str, data: dict) -> dict:
        return {
            "API-Key": self.api_key,
            "API-Sign": self.sign(urlpath, data),
            "Content-Type": "application/x-www-form-urlencoded",
        }

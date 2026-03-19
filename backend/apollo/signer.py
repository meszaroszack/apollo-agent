"""
KalshiSigner — Native RSA-PSS / SHA-256 request signing.

Kalshi mandates:
  signature = RSA-PSS( SHA256, timestamp + method + path )
  where path = URL path with ALL query parameters stripped.

Never use a third-party Kalshi SDK; sign every private request here.
"""

import base64
import hashlib
import time
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


class KalshiSigner:
    """
    Handles RSA-PSS signing for every authenticated Kalshi API call.

    Usage
    -----
    signer = KalshiSigner(key_id="your-key-id", private_key_pem="-----BEGIN...")
    headers = signer.build_auth_headers("GET", "/trade-api/v2/portfolio/balance")
    """

    SALT_LENGTH = padding.PSS.DIGEST_LENGTH  # Kalshi spec: PSS.DIGEST_LENGTH

    def __init__(self, key_id: str, private_key_pem: str):
        """
        Parameters
        ----------
        key_id : str
            The KALSHI_ACCESS_KEY (UUID) shown in your Kalshi account settings.
        private_key_pem : str
            Full contents of your .key file (PEM-encoded RSA private key).
        """
        self.key_id = key_id
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode() if isinstance(private_key_pem, str) else private_key_pem,
            password=None,
            backend=default_backend(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_auth_headers(
        self,
        method: str,
        path: str,
        timestamp_ms: Optional[int] = None,
    ) -> dict[str, str]:
        """
        Return a dict of HTTP headers required by Kalshi for authenticated calls.

        Parameters
        ----------
        method : str
            HTTP verb in UPPER-CASE  (e.g. "GET", "POST", "DELETE").
        path : str
            The request path.  Query parameters are stripped automatically.
            Example: "/trade-api/v2/portfolio/balance?cursor=abc" → "/trade-api/v2/portfolio/balance"
        timestamp_ms : int | None
            Epoch timestamp in milliseconds.  Defaults to now.
        """
        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        clean_path = self._strip_query(path)
        message = self._build_message(ts, method.upper(), clean_path)
        signature_b64 = self._sign(message)

        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_query(path: str) -> str:
        """Remove query string and fragment from path."""
        return path.split("?")[0].split("#")[0]

    @staticmethod
    def _build_message(timestamp_ms: int, method: str, path: str) -> bytes:
        """
        Construct the canonical message string per Kalshi spec:
            <timestamp_ms><METHOD><path>
        """
        msg = f"{timestamp_ms}{method}{path}"
        return msg.encode("utf-8")

    def _sign(self, message: bytes) -> str:
        """
        Sign with RSA-PSS (SHA-256, MGF1-SHA-256, salt_length=SALT_LENGTH).
        Returns Base64-encoded signature suitable for the HTTP header.
        """
        signature_bytes = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=self.SALT_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature_bytes).decode("utf-8")

    # WebSocket auth is performed by sending the same signed headers used for
    # HTTP requests during the upgrade handshake (see OrderbookManager).

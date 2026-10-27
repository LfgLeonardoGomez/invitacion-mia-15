"""Deterministic disposable fixture material; never used as application defaults."""

import base64

TEST_LINK_KEY = base64.urlsafe_b64encode(b"L" * 32).decode("ascii")

"""Output contract shared by every command (see README "Built for agents").

- Success: exit 0. With --json, stdout is exactly one JSON document; "nothing
  found" is valid empty JSON, never an error.
- Errors: one line on stderr, exit 1 (text and JSON mode alike).
- Usage errors: exit 2 (argparse).
- Diagnostics (progress, warnings, [skip] notices): stderr, never stdout.
"""

import json
import re
import sys

# credentials that can ride in URLs (FRED puts api_key in the query string)
_SECRET = re.compile(r"((?:api_key|apikey|access_token|token)=)[^&\s'\"]+", re.IGNORECASE)


def redact(text):
    """Text with URL-borne credentials masked."""
    return _SECRET.sub(r"\1***", str(text))


def emit_json(obj):
    """The single JSON document a --json run writes to stdout."""
    print(json.dumps(obj, indent=2, default=str))


def warn(msg):
    """Diagnostic for humans and logs; never pollutes stdout."""
    print(msg, file=sys.stderr)


def fail(msg, code=1):
    """User-facing error: message on stderr, non-zero exit."""
    print(f"finresearch: error: {redact(msg)}", file=sys.stderr)
    sys.exit(code)

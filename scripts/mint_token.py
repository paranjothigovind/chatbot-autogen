"""Print a signed local-dev bearer token: `uv run python scripts/mint_token.py <user_id>`."""

import sys

from app.core.auth import mint_local_dev_token
from app.core.config import get_settings

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: mint_token.py <user_id>")
    sys.stdout.write(mint_local_dev_token(get_settings(), sys.argv[1]) + "\n")

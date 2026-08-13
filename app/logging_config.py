"""
One-line logging setup, imported first thing in app/main.py.

Swaps the app's scattered print() calls for the standard `logging`
module — same visibility in Cloud Logging (both go to stdout/stderr),
but with actual levels (INFO/WARNING/ERROR) so a log platform can
filter/alert on errors specifically instead of grepping raw text, plus
a timestamp and the originating module name on every line for free.

LOG_LEVEL env var lets this be turned up (DEBUG) or down (WARNING) per
environment without a code change; defaults to INFO.
"""
import logging
import os

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

import json
import subprocess
from urllib.parse import urlsplit


ALLOWED_HOSTS = {"xz.ke.com", "xz.esf.fang.com", "xuzhou.anjuke.com"}
MARKER = "PROPERTY_DISCOVERY_JSON:"


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port is not None):
        raise ValueError("Only configured HTTPS public listing hosts are allowed")
    if parsed.query or parsed.fragment:
        raise ValueError("Queries/fragments are not accepted; do not store session tokens")
    allowed_paths = {
        "xz.ke.com": ("/ershoufang/", "/xiaoqu/"),
        "xz.esf.fang.com": ("/house/", "/chushou/"),
        "xuzhou.anjuke.com": ("/sale/",),
    }
    if not parsed.path.startswith(allowed_paths[parsed.hostname]):
        raise ValueError("URL is not a public listing/community path")
    return parsed.hostname


def read_page(url, script, timeout=50):
    """Normal Chrome navigation only. No cookies, tokens, APIs or challenge actions."""
    validate_url(url)
    # Each extraction checks for gates before returning only allowlisted DOM fields.
    program = (f"new_tab({url!r})\nwait_for_load()\n"
               f"print({MARKER!r} + js({script!r}))\n")
    try:
        result = subprocess.run(["browser-harness"], input=program, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "browser_error", "reason": type(exc).__name__}
    lines = [line[len(MARKER):] for line in result.stdout.splitlines()
             if line.startswith(MARKER)]
    if result.returncode or not lines:
        return {"status": "browser_error", "reason": "harness_failed_or_no_payload"}
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"status": "browser_error", "reason": "invalid_payload"}
    if not isinstance(payload, dict):
        return {"status": "browser_error", "reason": "unexpected_payload_type"}
    return payload

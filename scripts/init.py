#!/usr/bin/env python3
"""projarvis interactive initialization script — one command to go from clone to running."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CADDYFILE = ROOT / "Caddyfile"
DOTENV = ROOT / ".env"
CONFIG_TOML = ROOT / "config" / "app_config.toml"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_AVAILABILITY = {
    "monday":    [["09:00", "12:00"], ["14:00", "18:00"]],
    "tuesday":   [["09:00", "12:00"], ["14:00", "18:00"]],
    "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
    "thursday":  [["09:00", "12:00"], ["14:00", "18:00"]],
    "friday":    [["09:00", "12:00"], ["14:00", "17:00"]],
    "saturday":  [],
    "sunday":    [],
}


def ask(prompt: str, default: str = "") -> str:
    if default:
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer if answer else default
    return input(f"{prompt}: ").strip()


def ask_required(prompt: str) -> str:
    while True:
        answer = input(f"{prompt}: ").strip()
        if answer:
            return answer
        print("  Required. Please enter a value.")


def banner(title: str) -> None:
    print()
    print("=" * 50)
    print(f"  {title}")
    print("=" * 50)


# ---------------------------------------------------------------------------
# 1. Domain
# ---------------------------------------------------------------------------

def step_domain() -> str:
    banner("Domain")
    print("The domain name that points to this server (Caddy will get HTTPS certs).")
    print("Use 'localhost' only for local testing (no HTTPS).")
    return ask_required("Domain")


# ---------------------------------------------------------------------------
# 2. Access credentials
# ---------------------------------------------------------------------------

def _hash_password(plaintext: str) -> str:
    """Generate bcrypt hash using caddy in Docker."""
    print("  Generating password hash (may pull caddy image the first time)...")
    result = subprocess.run(
        [
            "docker", "run", "--rm", "caddy:2-alpine",
            "caddy", "hash-password", "--plaintext", plaintext,
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def step_auth() -> tuple[str, str]:
    banner("Access Credentials")
    print("Set a username and password to protect the app via HTTPS Basic Auth.")
    username = ask_required("Username")
    while True:
        password = input("Password: ").strip()
        if password:
            break
        print("  Required. Please enter a value.")
    password_hash = _hash_password(password)
    return username, password_hash


# ---------------------------------------------------------------------------
# 3. Anthropic API key
# ---------------------------------------------------------------------------

def step_api_key() -> str:
    banner("Anthropic API Key")
    print("The agent uses Claude API. Get a key at https://console.anthropic.com/")
    return ask_required("API Key")


# ---------------------------------------------------------------------------
# 3. Baikal setup + calendar discovery
# ---------------------------------------------------------------------------

def _ensure_caldav_lib() -> None:
    try:
        import caldav  # noqa: F401
    except ImportError:
        print("Installing caldav library for Baikal discovery...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "caldav"])


def _discover_calendars(url: str, username: str, password: str) -> list[dict]:
    import caldav
    client = caldav.DAVClient(url=url, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    results = []
    for cal in calendars:
        results.append({"name": cal.name, "url": str(cal.url)})
    return results


def step_baikal() -> dict:
    banner("Baikal / CalDAV")

    print("Do you already have Baikal initialized?")
    print("  [y] Yes, it's running with a user and calendar")
    print("  [n] No, I need to set it up first")
    has_baikal = ask("Choice", "y").lower().startswith("y")

    if not has_baikal:
        print()
        print("Baikal needs first-time setup via Web UI:")
        print()
        print("  1. Open an SSH tunnel to this server:")
        print("     ssh -L 8080:localhost:8080 <user>@<server-ip>")
        print()
        print("  2. In your local browser, open http://localhost:8080")
        print("     - Create an admin user")
        print("     - Create a calendar (e.g. 'projarvis')")
        print()
        input("Press Enter when Baikal is ready... ")

    print()
    print("CalDAV connection details:")
    print("  (Host URL for discovery, e.g. http://localhost:8080/dav.php/)")
    url = ask("URL", "http://localhost:8080/dav.php/")
    username = ask_required("Username")
    password = ask_required("Password")

    print()
    print("Discovering calendars...")
    try:
        calendars = _discover_calendars(url, username, password)
    except Exception as e:
        print(f"  Discovery failed: {e}")
        print("  Continuing with manual calendar entry.")
        calendar_name = ask("Calendar name", "projarvis")
        # Build container URL from host URL
        container_url = url.replace("localhost:8080", "baikal:80")
        return {
            "url": f"{container_url.rstrip('/')}/calendars/{username}/{calendar_name}/",
            "username": username,
            "password": password,
            "calendar_name": calendar_name,
        }

    if not calendars:
        print("  No calendars found. Creating default entry.")
        calendar_name = ask("Calendar name", "projarvis")
        container_url = url.replace("localhost:8080", "baikal:80")
        return {
            "url": f"{container_url.rstrip('/')}/calendars/{username}/{calendar_name}/",
            "username": username,
            "password": password,
            "calendar_name": calendar_name,
        }

    print()
    print("Available calendars:")
    for i, cal in enumerate(calendars):
        print(f"  [{i + 1}] {cal['name']}")
        print(f"      {cal['url']}")

    while True:
        choice = input(f"Pick one [1-{len(calendars)}]: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(calendars):
                break
        except ValueError:
            pass
        print(f"  Enter 1-{len(calendars)}")

    picked = calendars[idx]
    container_url = picked["url"].replace("localhost:8080", "baikal:80")
    if ":" in container_url and "baikal:80" not in container_url:
        # Try other port patterns
        import re
        container_url = re.sub(r"localhost:\d+", "baikal:80", container_url)
        container_url = re.sub(r"127\.0\.0\.1:\d+", "baikal:80", container_url)

    return {
        "url": container_url,
        "username": username,
        "password": password,
        "calendar_name": picked["name"],
    }


# ---------------------------------------------------------------------------
# 4. App config
# ---------------------------------------------------------------------------

def _parse_time_ranges(raw: str) -> list[list[str]]:
    """Parse '09:00-12:00,14:00-18:00' into [['09:00','12:00'],['14:00','18:00']]."""
    if not raw.strip():
        return []
    ranges = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            start, end = part.split("-")
            ranges.append([start.strip(), end.strip()])
        except ValueError:
            print(f"    Warning: could not parse '{part}', skipping")
    return ranges


def _fmt_ranges(ranges: list[list[str]]) -> str:
    return ",".join(f"{s}-{e}" for s, e in ranges)


def step_app_config() -> dict:
    banner("Schedule Preferences")

    weeks = int(ask("Planning horizon (weeks)", "4"))

    print()
    print("Weekly availability (enter time ranges or leave empty for no availability):")
    print("  Format: 09:00-12:00,14:00-18:00")
    print()
    availability: dict[str, list[list[str]]] = {}
    for day in WEEKDAYS:
        default = _fmt_ranges(DEFAULT_AVAILABILITY[day])
        raw = ask(f"  {day.capitalize():>9}", default)
        availability[day] = _parse_time_ranges(raw)

    print()
    print("Engine settings:")
    max_time = float(ask("  Max solve time (seconds)", "30.0"))
    seed = int(ask("  Random seed", "42"))

    return {
        "horizon_weeks": weeks,
        "availability": availability,
        "max_time_seconds": max_time,
        "random_seed": seed,
    }


# ---------------------------------------------------------------------------
# 5. Write config files
# ---------------------------------------------------------------------------

def _toml_str(value: str) -> str:
    return f'"{value}"'


def write_app_config(caldav: dict, app_cfg: dict) -> None:
    avail = app_cfg["availability"]
    avail_lines = []
    for day in WEEKDAYS:
        ranges = avail[day]
        inner = ", ".join(f'["{s}", "{e}"]' for s, e in ranges)
        avail_lines.append(f"{day:<9} = [{inner}]")

    content = f"""[horizon]
weeks = {app_cfg['horizon_weeks']}

[availability]
{chr(10).join(avail_lines)}

[caldav]
url = "{caldav['url']}"
username = "{caldav['username']}"
password = "{caldav['password']}"
calendar_name = "{caldav['calendar_name']}"

[engine]
max_time_seconds = {app_cfg['max_time_seconds']}
random_seed = {app_cfg['random_seed']}
"""

    CONFIG_TOML.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_TOML.write_text(content)
    print(f"  Wrote {CONFIG_TOML}")


def write_caddyfile(domain: str, username: str, password_hash: str) -> None:
    CADDYFILE.write_text(f"""{domain} {{
    basicauth {{
        {username} {password_hash}
    }}
    reverse_proxy projarvis:8000
}}
""")
    print(f"  Wrote {CADDYFILE}")


def write_dotenv(api_key: str) -> None:
    DOTENV.write_text(f"ANTHROPIC_API_KEY={api_key}\n")
    print(f"  Wrote {DOTENV}")


# ---------------------------------------------------------------------------
# 6. Docker compose + health check
# ---------------------------------------------------------------------------

def docker_up() -> None:
    banner("Starting Services")
    print("Running: docker compose up -d")
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=str(ROOT),
        check=True,
    )

    print()
    print("Waiting for projarvis to be ready...")
    for i in range(30):
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://localhost:8000/api/v1/plan", timeout=5)
            if resp.status == 200:
                print("  Ready!")
                return
        except Exception:
            pass
        time.sleep(2)

    print("  Warning: projarvis did not become ready within 60s.")
    print("  Check logs: docker compose logs projarvis")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print()
    print("╔════════════════════════════════════════════════╗")
    print("║           projarvis — Initial Setup            ║")
    print("╚════════════════════════════════════════════════╝")

    # 1. Domain
    domain = step_domain()

    # 2. Access credentials
    username, password_hash = step_auth()
    write_caddyfile(domain, username, password_hash)

    # 3. API key
    api_key = step_api_key()
    write_dotenv(api_key)

    # 4. Baikal
    _ensure_caldav_lib()
    baikal_cfg = step_baikal()

    # 5. App config
    app_cfg = step_app_config()
    write_app_config(baikal_cfg, app_cfg)

    # 6. Docker compose up
    docker_up()

    # 7. Done
    banner("Setup Complete")
    print(f"  Username:  {username}")
    print(f"  API:       http://localhost:8000/api/v1")
    print(f"  HTTPS:     https://{domain}/api/v1")
    print(f"  Docs:      http://localhost:8000/docs")
    print()
    if domain == "localhost":
        print("  (HTTPS not available with localhost — use HTTP)")
    else:
        print("  Caddy will get HTTPS certs automatically on first request.")
    print()


if __name__ == "__main__":
    main()

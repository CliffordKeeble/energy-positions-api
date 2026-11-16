"""The deploy job's last step: a smoke check of the live app, which can fail.

    python3 scripts/smoke_check.py --app energy-positions-api --resource-group rg-energy-positions
        --expect-image ghcr.io/cliffordkeeble/energy-positions-api:<commit sha>
        --url https://<live address>/portfolios/7/positions/current

It passes only if both of these are seen, in this order, within the limit:

  (a) every revision of the app that carries traffic runs --expect-image. The Azure
      CLI is asked (az containerapp revision list), so this needs a signed-in az.
  (b) GET --url answers 200 with a JSON object that has "settlement_period" and
      "net_mwh".

The app scales to nothing and its database sleeps, so anything else is tried again:
every 5 seconds, each request allowed 60 seconds, the whole check 300 seconds unless
--limit says otherwise. The time to the first 200 is printed.

What turns it red, so that a green means something:

  - A tag that is not the one deployed. If the deployment pointed the app at a tag
    that does not exist, the new revision never becomes ready and the old one keeps
    the traffic. If the check is told to expect the wrong tag, no revision matches.
    Either way (a) fails at the limit.
  - A wrong path, or an app that cannot reach its database: (b) never sees its 200.

Away from the deploy job there is no signed-in az, so --endpoint-only runs (b) alone,
and says that (a) was not checked:

    uv run python scripts/smoke_check.py --endpoint-only --url https://<live address>/portfolios/7/positions/current

Standard library only, and nothing newer than Python 3.10: the deploy job runs this
with the runner's own python3, not the project's.

Exit status: 0 passed, 1 failed, 2 could not start.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.client import HTTPException

REQUIRED_KEYS = ("settlement_period", "net_mwh")

DEFAULT_LIMIT_SECONDS = 300.0
PAUSE_SECONDS = 5.0
REQUEST_SECONDS = 60.0
AZ_SECONDS = 120.0
BODY_LIMIT_BYTES = 65536


class Unanswered(Exception):
    """A question that got no usable answer this time. It is asked again."""


class Stopwatch:
    """The time since the check began, and what is left of the limit."""

    def __init__(self, limit: float) -> None:
        self.started = time.monotonic()
        self.limit = limit

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def remaining(self) -> float:
        return self.limit - self.elapsed()

    def say(self, message: str) -> None:
        print(f"[{self.elapsed():6.1f} s] {message}", flush=True)

    def pause(self) -> bool:
        """Wait before the next try. False if the limit leaves no room for one."""
        if self.remaining() <= PAUSE_SECONDS:
            return False
        time.sleep(PAUSE_SECONDS)
        return True


# (a) Which image is serving.


def active_revisions(az: str, app: str, group: str, timeout: float) -> list[dict]:
    """The app's active revisions, as the Azure CLI reports them."""
    command = [az, "containerapp", "revision", "list", "--name", app, "--resource-group", group]
    try:
        done = subprocess.run(
            [*command, "--output", "json"], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Unanswered(f"az could not be run: {error}") from error
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        raise Unanswered(f"az exited {done.returncode}: {lines[-1] if lines else 'it said nothing'}")
    try:
        found = json.loads(done.stdout)
    except ValueError as error:
        raise Unanswered(f"az did not print JSON: {error}") from error
    if not isinstance(found, list) or not all(isinstance(revision, dict) for revision in found):
        raise Unanswered("az printed JSON, but not a list of revisions")
    return found


def images(revision: dict) -> list[str]:
    template = (revision.get("properties") or {}).get("template") or {}
    return [str(container.get("image")) for container in template.get("containers") or []]


def traffic(revision: dict) -> float:
    weight = (revision.get("properties") or {}).get("trafficWeight")
    return float(weight) if isinstance(weight, (int, float)) else 0.0


def picture(found: list[dict]) -> list[str]:
    """One line for each revision: what a reader of the log needs to see for themselves."""
    lines = []
    for revision in found:
        properties = revision.get("properties") or {}
        state = properties.get("runningState") or properties.get("healthState") or "state unknown"
        lines.append(
            f"    {revision.get('name')}: {', '.join(images(revision)) or 'no image'}; "
            f"traffic {traffic(revision):g} %; {state}; replicas {properties.get('replicas')}"
        )
    return lines or ["    no active revision"]


def wrong_revisions(found: list[dict], expected: str) -> str | None:
    """None if every revision that carries traffic runs the expected image, else why not."""
    carrying = [revision for revision in found if traffic(revision) > 0]
    if not carrying:
        return "no revision carries traffic"
    wrong = [str(revision.get("name")) for revision in carrying if expected not in images(revision)]
    if wrong:
        return f"traffic goes to {', '.join(wrong)}, which does not run {expected}"
    return None


def check_revisions(watch: Stopwatch, az: str, app: str, group: str, expected: str) -> str | None:
    """Ask until the traffic is on the expected image. None if it is, else the last reason."""
    watch.say(f"(a) is the traffic on {expected}?")
    last_picture: list[str] = []
    while True:
        try:
            found = active_revisions(az, app, group, min(AZ_SECONDS, max(1.0, watch.remaining())))
        except Unanswered as error:
            reason = str(error)
            watch.say(f"    {reason}")
        else:
            reason = wrong_revisions(found, expected)
            now = picture(found)
            if now != last_picture:
                watch.say("the active revisions:")
                print("\n".join(now), flush=True)
                last_picture = now
            if reason is None:
                watch.say("(a) yes")
                return None
            watch.say(f"    not yet: {reason}")
        if not watch.pause():
            return reason


# (b) Whether the live endpoint answers.


def get(url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(BODY_LIMIT_BYTES)
    except urllib.error.HTTPError as error:
        return error.code, error.read(BODY_LIMIT_BYTES)
    except (OSError, HTTPException) as error:  # no connection, a timeout, a cut-off reply
        raise Unanswered(f"no answer: {error}") from error


def wrong_answer(status: int, body: bytes) -> str | None:
    """None if this is the answer the check is waiting for, else what is wrong with it."""
    if status != 200:
        return f"status {status}"
    try:
        parsed = json.loads(body)
    except ValueError:
        return "200, but the body is not JSON"
    if not isinstance(parsed, dict):
        return "200, but the JSON is not an object"
    missing = [key for key in REQUIRED_KEYS if key not in parsed]
    if missing:
        return f"200, but the JSON has no {' and no '.join(missing)}"
    return None


def check_endpoint(watch: Stopwatch, url: str) -> tuple[str | None, str]:
    """Ask until the endpoint answers properly.

    Returns (None, the measurement) if it did, else (the last reason, "").
    """
    watch.say(f"(b) GET {url}")
    first_sent = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        sent = time.monotonic()
        try:
            status, body = get(url, min(REQUEST_SECONDS, max(1.0, watch.remaining())))
            reason = wrong_answer(status, body)
        except Unanswered as error:
            reason = str(error)
        took = time.monotonic() - sent
        if reason is None:
            watch.say(f"    attempt {attempt}: 200 with {' and '.join(REQUIRED_KEYS)}, in {took:.1f} s")
            measurement = (
                f"first 200 after {time.monotonic() - first_sent:.1f} s, counted from the first "
                f"request being sent (attempt {attempt}; that request alone took {took:.1f} s)"
            )
            return None, measurement
        watch.say(f"    attempt {attempt}: {reason}, in {took:.1f} s")
        if not watch.pause():
            return reason, ""


# The verdict.


def report(passed: bool, lines: list[str]) -> int:
    """Print the verdict, and on GitHub put it on the run's summary page as well."""
    print()
    print("\n".join(lines), flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true" and not passed:
        print(f"::error title=smoke check::{lines[0]}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a", encoding="utf-8") as page:
                page.write("### Smoke check\n\n" + "".join(f"- {line}\n" for line in lines))
        except OSError:
            pass  # the summary page is a convenience; the log already has it
    return 0 if passed else 1


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke check of the live app. See the top of this file.")
    parser.add_argument("--url", required=True, help="the live endpoint to GET")
    parser.add_argument("--expect-image", help="the image, with its tag, that must be serving")
    parser.add_argument("--app", help="the container app's name")
    parser.add_argument("--resource-group", help="the container app's resource group")
    parser.add_argument(
        "--endpoint-only", action="store_true", help="skip (a), which needs a signed-in az; run (b) alone"
    )
    parser.add_argument(
        "--limit", type=float, default=DEFAULT_LIMIT_SECONDS, help="seconds for the whole check (default 300)"
    )
    args = parser.parse_args()
    azure = {"--expect-image": args.expect_image, "--app": args.app, "--resource-group": args.resource_group}
    if args.endpoint_only:
        given = [name for name, value in azure.items() if value]
        if given:
            parser.error(f"--endpoint-only skips the revision check, so {', '.join(given)} would be ignored")
    else:
        missing = [name for name, value in azure.items() if not value]
        if missing:
            parser.error(f"{', '.join(missing)} needed (or --endpoint-only, to skip the revision check)")
    if args.limit <= 0:
        parser.error("--limit must be more than 0")
    return args


def main() -> int:
    args = arguments()
    az = None
    if not args.endpoint_only:
        az = shutil.which("az")
        if az is None:
            print("the Azure CLI (az) is not on the path; --endpoint-only runs without it", file=sys.stderr)
            return 2

    watch = Stopwatch(args.limit)
    if az is None:
        serving = "(a) NOT CHECKED (--endpoint-only): which image is serving is not known from this run"
        watch.say(serving)
    else:
        reason = check_revisions(watch, az, args.app, args.resource_group, args.expect_image)
        if reason is not None:
            return report(False, [
                f"FAILED (a) after {watch.elapsed():.1f} s of a {args.limit:g} s limit: {reason}",
                f"expected {args.expect_image}",
            ])
        serving = f"(a) the traffic is on {args.expect_image}"

    reason, measurement = check_endpoint(watch, args.url)
    if reason is not None:
        return report(False, [
            f"FAILED (b) after {watch.elapsed():.1f} s of a {args.limit:g} s limit: "
            f"no 200 with {' and '.join(REQUIRED_KEYS)}; the last try gave: {reason}",
            serving,
            f"GET {args.url}",
        ])
    return report(True, [
        f"PASSED in {watch.elapsed():.1f} s of a {args.limit:g} s limit",
        serving,
        f"(b) {measurement}",
    ])


if __name__ == "__main__":
    sys.exit(main())

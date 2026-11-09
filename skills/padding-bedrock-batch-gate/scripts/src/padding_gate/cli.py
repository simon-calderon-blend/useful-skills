"""padding-gate: status | inject | cleanup for the doc-extraction batch gate.

Exit codes: 0 ok, 1 a write failed part-way, 2 refused (guard, plan or gate),
3 expired or missing AWS credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    SSOError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)

from padding_gate.appconfig import AppConfigError, LiveConfig, load_live_config
from padding_gate.cleanup import (
    CleanupFailed,
    CleanupRefused,
    assess_run,
    delete_run,
    scan_spuria_rows,
    validate_run_id,
)
from padding_gate.conveyor import (
    RunConfigResolver,
    group_by_model,
    needed_count,
    queue_depth,
    queue_url,
    scan_pending,
)
from padding_gate.guards import GuardError, check_profile, verify_account
from padding_gate.inject import (
    DEFAULT_DOC_CODE,
    InjectFailed,
    InjectRefused,
    apply_plan,
    build_plan,
    wait_for_quiet,
)
from padding_gate.resources import BASE_PREFIX, REGION, Resources, resources_for

_EXPIRED_HINT = "AWS credentials expired or missing. Ask the user to run `awsl` (needs a browser), then retry."
_EXPIRED_CODES = {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException"}


class _Context:
    def __init__(self, args: argparse.Namespace, session: Any, res: Resources) -> None:
        self.args = args
        self.res = res
        self._session = session
        self._clients: dict[str, Any] = {}
        self._queue_url: str | None = None

    def client(self, name: str) -> Any:
        if name not in self._clients:
            self._clients[name] = self._session.client(name)
        return self._clients[name]

    def queue_url(self) -> str:
        if self._queue_url is None:
            self._queue_url = queue_url(self.client("sqs"), self.res.queue_name)
        return self._queue_url

    def resolver(self, live: LiveConfig) -> RunConfigResolver:
        return RunConfigResolver(
            self.client("s3"),
            bucket=self.res.bucket,
            base_prefix=BASE_PREFIX,
            pointers_prefix=live.pointers_prefix,
            run_configs_prefix=live.run_configs_prefix,
        )

    def command(self, *tail: str) -> str:
        return " ".join(
            ["padding-gate", *tail[:1], "--env", self.args.env, "--profile", self.args.profile, *tail[1:]]
        )


def _say(json_mode: bool) -> Callable[[str], None]:
    """Human report: stdout normally, stderr under --json so stdout stays one document."""
    stream = sys.stderr if json_mode else sys.stdout
    return lambda line="": print(line, file=stream)


def _snapshot(ctx: _Context, live: LiveConfig):
    url = ctx.queue_url()
    depth = queue_depth(ctx.client("sqs"), url)
    pending = scan_pending(ctx.client("dynamodb"), ctx.res.table)
    resolver = ctx.resolver(live)
    groups, unresolved = group_by_model(pending, resolver)
    return url, depth, pending, resolver, groups, unresolved


def _status(ctx: _Context, live: LiveConfig, account: str) -> int:
    _, depth, pending, _, groups, unresolved = _snapshot(ctx, live)
    target = next((g for g in groups if g.real > 0), None)
    if depth.visible == 0:
        recommendation = {"action": "none", "count": 0, "why": "queue is empty"}
    elif target is None:
        recommendation = {"action": "none", "count": 0, "why": "no real chunk with a resolvable run config"}
    else:
        count = needed_count(live.min_records, depth.visible, target.total)
        recommendation = {
            "action": "inject" if count else "none",
            "count": count,
            "model_id": target.model_id,
            "why": "below the gate; inject only once the depth has held still"
            if count
            else "already at or above the gate",
        }

    rows_by_run: dict[str, list] = defaultdict(list)
    for row in scan_spuria_rows(ctx.client("dynamodb"), ctx.res.table):
        rows_by_run[row.spuria_run_id].append(row)
    runs = [
        asdict(assess_run(run_id, rows, ctx.client("dynamodb"), ctx.client("bedrock"), ctx.res.table))
        for run_id, rows in sorted(rows_by_run.items())
    ]

    report = {
        "env": ctx.args.env,
        "account": account,
        "appconfig": live.sources,
        "min_records": live.min_records,
        "queue": {"visible": depth.visible, "inflight": depth.inflight},
        "pending": {
            "real": sum(not c.is_spuria for c in pending),
            "spuria": sum(c.is_spuria for c in pending),
            "unresolved_run_config": unresolved,
        },
        "groups": [
            {"model_id": g.model_id, "digest": g.digest, "real": g.real, "spuria": g.spuria} for g in groups
        ],
        "recommendation": recommendation,
        "spuria_runs": runs,
    }
    if ctx.args.json:
        print(json.dumps(report, sort_keys=True))
        return 0

    say = _say(False)
    say(f"env {ctx.args.env} (account {account}), min_records_per_job={live.min_records} "
        f"[batch {live.sources['batch']}]")
    say(f"queue: visible={depth.visible} in-flight={depth.inflight}")
    say(f"PENDING chunks: real={report['pending']['real']} spuria={report['pending']['spuria']} "
        f"unresolved={unresolved}")
    for g in groups:
        say(f"  model {g.model_id}: real={g.real} spuria={g.spuria} (run config {g.digest[:16]}...)")
    say(f"recommendation: {recommendation['action']} {recommendation['count'] or ''} - {recommendation['why']}")
    if len([g for g in groups if g.real]) > 1:
        say("note: real chunks span several models; each model group must reach the gate on its own")
    say(f"filler runs: {len(runs)}")
    for run in runs:
        state = "SAFE to clean up" if run["safe"] else "blocked: " + "; ".join(run["reasons"])
        say(f"  {run['run_id']} {run['counts']} -> {state}")
    return 0


def _inject(ctx: _Context, live: LiveConfig, *, clock, sleep, now) -> int:
    args = ctx.args
    say = _say(args.json)
    if args.apply:
        url = ctx.queue_url()
        say(f"waiting for the queue depth to hold still for {args.quiet_seconds:.0f}s ...")
        wait_for_quiet(
            lambda: queue_depth(ctx.client("sqs"), url).visible,
            quiet_seconds=args.quiet_seconds,
            poll_seconds=args.poll_seconds,
            max_wait=args.max_wait,
            clock=clock,
            sleep=sleep,
        )
    url, depth, _, resolver, groups, _ = _snapshot(ctx, live)
    plan = build_plan(
        live=live,
        depth=depth,
        groups=groups,
        resolver=resolver,
        doc_code=args.doc_code,
        count=args.count,
        base_prefix=BASE_PREFIX,
    )
    say(f"run_id:       {plan.run_id if args.apply else 'assigned at --apply'}")
    say(f"count:        {plan.count}  (queue {plan.visible}, model group {plan.group_total} "
        f"of which real {plan.group_real}, min_records {plan.min_records})")
    say(f"doc_code:     {plan.doc_code}")
    say(f"model:        {plan.model_id}")
    say(f"run config:   {plan.digest}")
    say(f"blank pdf:    s3://{ctx.res.bucket}/{plan.pdf_key}")
    say(f"cost:         ~US${plan.cost_usd:.2f} (estimate)")
    if not args.apply:
        say("DRY-RUN: nothing written. Re-run with --apply after the user confirms.")
        return 0

    apply_plan(
        plan,
        s3=ctx.client("s3"),
        ddb=ctx.client("dynamodb"),
        sqs=ctx.client("sqs"),
        queue_url=url,
        bucket=ctx.res.bucket,
        table=ctx.res.table,
        now=now(),
    )
    after = queue_depth(ctx.client("sqs"), url).visible
    cleanup = ctx.command("cleanup", "--run-id", plan.run_id, "--apply")
    say(f"written: {plan.count} filler chunk(s); queue depth {plan.visible} -> {after} (approximate)")
    say(f"record this run id. Clean up ONLY after the batch job has been reconciled: {cleanup}")
    if args.json:
        print(json.dumps({
            "run_id": plan.run_id, "count": plan.count, "env": args.env, "doc_code": plan.doc_code,
            "model_id": plan.model_id, "queue_depth_before": plan.visible, "queue_depth_after": after,
            "cost_estimate_usd": plan.cost_usd, "cleanup_command": cleanup,
        }, sort_keys=True))
    return 0


def _cleanup(ctx: _Context) -> int:
    args = ctx.args
    say = _say(False)
    run_id = validate_run_id(args.run_id)
    ddb = ctx.client("dynamodb")
    rows = scan_spuria_rows(ddb, ctx.res.table, run_id)
    verdict = assess_run(
        run_id, rows, ddb, ctx.client("bedrock"), ctx.res.table, abandon_pending=args.abandon_pending
    )
    say(f"run {run_id}: {len(rows)} row(s) {verdict.counts}")
    for job, status in verdict.jobs.items():
        say(f"  job {job}: {status}")
    if not verdict.safe:
        say("blocked: " + "; ".join(verdict.reasons))
    if not args.apply:
        say("DRY-RUN: nothing deleted." + (" Safe to re-run with --apply." if verdict.safe else ""))
        return 0 if verdict.safe else 2
    deleted_rows, deleted_objects = delete_run(
        verdict, rows, ddb=ddb, s3=ctx.client("s3"), table=ctx.res.table,
        bucket=ctx.res.bucket, base_prefix=BASE_PREFIX,
    )
    say(f"deleted {deleted_rows} row(s) and {deleted_objects} S3 object(s); SQS not touched")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="padding-gate", description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env", required=True, choices=("dev", "test"))
    common.add_argument("--profile", required=True, help="AWS SSO profile; never defaulted")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", parents=[common], help="read-only snapshot (default first step)")
    status.add_argument("--json", action="store_true")

    inject = sub.add_parser("inject", parents=[common], help="plan filler; writes only with --apply")
    inject.add_argument("--apply", action="store_true")
    inject.add_argument("--json", action="store_true")
    inject.add_argument("--count", type=int, default=None, help="override the computed top-up")
    inject.add_argument("--doc-code", default=DEFAULT_DOC_CODE)
    inject.add_argument("--quiet-seconds", type=float, default=300.0)
    inject.add_argument("--poll-seconds", type=float, default=30.0)
    inject.add_argument("--max-wait", type=float, default=1800.0)

    cleanup = sub.add_parser("cleanup", parents=[common], help="remove one filler run; deletes only with --apply")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--apply", action="store_true")
    cleanup.add_argument(
        "--abandon-pending",
        action="store_true",
        help="let PENDING filler go: only for a failed inject whose rows never got a message",
    )
    return parser


def _is_expired(error: Exception) -> bool:
    if isinstance(error, (TokenRetrievalError, SSOError, UnauthorizedSSOTokenError, NoCredentialsError)):
        return True
    return isinstance(error, ClientError) and error.response.get("Error", {}).get("Code") in _EXPIRED_CODES


def main(
    argv: list[str] | None = None,
    *,
    session_factory: Callable[..., Any] = boto3.Session,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], int] = lambda: int(time.time()),
) -> int:
    args = _parser().parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    try:
        check_profile(args.profile)
        overrides = sorted(k for k in os.environ if k.startswith("AWS_ENDPOINT_URL"))
        if overrides:
            raise GuardError(f"refusing to run with endpoint overrides set: {overrides}")
        res = resources_for(args.env)
        session = session_factory(profile_name=args.profile, region_name=REGION)
        ctx = _Context(args, session, res)
        account = verify_account(ctx.client("sts"), args.env)
        live = load_live_config(ctx.client("appconfig"), res.appconfig_app, args.env)
        if args.command == "status":
            return _status(ctx, live, account)
        if args.command == "inject":
            return _inject(ctx, live, clock=clock, sleep=sleep, now=now)
        return _cleanup(ctx)
    except (GuardError, AppConfigError, InjectRefused, CleanupRefused) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except InjectFailed as error:
        print(f"FAILED: {error}", file=sys.stderr)
        print(f"filler run {error.run_id} may be partly written. Inspect with "
              f"`padding-gate cleanup --env {args.env} --profile {args.profile} --run-id {error.run_id}`; "
              "if its rows stay PENDING because no message was sent, remove them with "
              "--abandon-pending --apply (after the user confirms).", file=sys.stderr)
        if error.__cause__ is not None and _is_expired(error.__cause__):
            print(_EXPIRED_HINT, file=sys.stderr)
            return 3
        return 1
    except CleanupFailed as error:
        print(f"FAILED: {error} (deleted so far: {error.rows_deleted} row(s), "
              f"{error.objects_deleted} object(s))", file=sys.stderr)
        return 1
    except Exception as error:
        if _is_expired(error):
            print(f"{_EXPIRED_HINT} ({type(error).__name__})", file=sys.stderr)
            return 3
        raise


if __name__ == "__main__":
    sys.exit(main())

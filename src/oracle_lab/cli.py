"""The `oracle-lab` command.

    oracle-lab serve          run the web app
    oracle-lab init-db        wait for the database(s) and create the sample schema (and the app's
                              tables, with STUDY_STATE_USER) if missing, and the practice-schema
                              profile OLL_LEARNER where practice schemas are configured
    oracle-lab validate       check the study content (see `oracle-lab validate --help`)
    oracle-lab demo PATH      write a simulated study history, for screenshots
    oracle-lab healthcheck    exit 0 when the web app answers on /healthz (for Docker)
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from oracle_lab import __version__
from oracle_lab.config import ConfigurationError, Settings

log = logging.getLogger("oracle_lab")


def _serve(settings: Settings, _: argparse.Namespace) -> int:
    from oracle_lab.bootstrap import build_app
    from oracle_lab.web.server import serve

    if settings.legacy_basic_auth:
        log.warning("STUDY_AUTH_PASSWORD is set but ignored: the app now has its own login.")
    app = build_app(settings)
    databases = ", ".join(f"{key}={target}" for key, target in settings.databases.items())
    log.info("Oracle Learning Lab %s on http://%s:%d (databases: %s; data in %s)", __version__,
             settings.host, settings.port, databases, settings.state_database or settings.data_dir)
    serve(app, settings.host, settings.port)
    return 0


def _init_db(settings: Settings, _: argparse.Namespace) -> int:
    from oracle_lab import engines
    from oracle_lab.bootstrap import build_catalog
    from oracle_lab.database.connection import OracleDatabase

    for key, database in build_catalog(settings).by_key.items():
        if not engines.engine_for_key(key).ensure_sample(database, settings.init_timeout):
            return 1
    if settings.state_database is not None:
        from oracle_lab.database.app_store import ensure_app_schema

        if not ensure_app_schema(OracleDatabase(settings.state_database, settings.call_timeout_ms), settings.init_timeout):
            return 1
    _ensure_profiles(settings)
    return 0


def _ensure_profiles(settings: Settings) -> None:
    """Create the learner profile on each practice database; a failure is only a warning."""
    from oracle_lab.bootstrap import build_provisioners

    for key, provisioner in build_provisioners(settings).items():
        practice = settings.practice[key]
        try:
            provisioner.ensure_profile()
        except Exception as exc:  # noqa: BLE001 - practice schemas still work without the profile
            log.warning("could not set up the learner profile for practice target %s (%s): %s",
                        key, practice.provisioner, exc)


def _validate(settings: Settings, args: argparse.Namespace) -> int:
    from oracle_lab.bootstrap import build_catalog
    from oracle_lab.tools import validate_content

    return validate_content.run(args, build_catalog(settings).default)


def _demo(settings: Settings, args: argparse.Namespace) -> int:
    from oracle_lab.tools.demo import write_demo

    try:
        write_demo(args.path, settings.state_file)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Wrote a simulated study history to {args.path}")
    return 0


def _healthcheck(settings: Settings, args: argparse.Namespace) -> int:
    host = "127.0.0.1" if settings.host in ("0.0.0.0", "::", "") else settings.host
    url = args.url or f"http://{host}:{settings.port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as response:
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"unhealthy: {url}: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oracle-lab", description="Oracle Learning Lab: SQL certification exam practice")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("serve", help="run the web app").set_defaults(run=_serve)
    commands.add_parser("init-db", help="create the sample schema (and the app's tables) if missing").set_defaults(run=_init_db)

    validate = commands.add_parser("validate", help="check the study content (structure, then on the database)")
    validate.add_argument("--static", action="store_true", help="skip the database checks")
    validate.add_argument("--reset", action="store_true", help="reset the sample data before the database checks")
    validate.add_argument("--coverage", action="store_true", help="print item counts per objective")
    validate.add_argument("--topic", help="run the database checks for one topic only, for example t08")
    validate.add_argument("--exam", help="check one exam's items only, for example 1Z0-171")
    validate.set_defaults(run=_validate)

    demo = commands.add_parser("demo", help="write a simulated study history to PATH")
    demo.add_argument("path", type=Path)
    demo.set_defaults(run=_demo)

    health = commands.add_parser("healthcheck", help="check that the web app answers")
    health.add_argument("--url", help="default: http://<STUDY_HOST>:<STUDY_PORT>/healthz")
    health.add_argument("--timeout", type=float, default=5)
    health.set_defaults(run=_healthcheck)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    return args.run(settings, args)


if __name__ == "__main__":
    sys.exit(main())

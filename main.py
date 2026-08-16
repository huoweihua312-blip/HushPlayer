import sys
from argparse import ArgumentParser
from typing import Sequence


def parse_startup_arguments(argv: Sequence[str] | None = None):
    parser = ArgumentParser(
        prog=(list(argv)[0] if argv else None),
        description="Start HushPlayer UI V2.",
    )
    parser.add_argument(
        "--ui-v2",
        action="store_true",
        help="Compatibility switch; the formal entrypoint is already UI V2.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use isolated deterministic UI V2 data for development and acceptance.",
    )
    return parser.parse_args(list(argv)[1:] if argv is not None else None)


def run_ui_v2_from_main(
    argv: Sequence[str] | None = None,
    *,
    data_mode: str = "real",
) -> int:
    from app.ui_v2.startup import run_ui_v2_application

    try:
        return run_ui_v2_application(
            argv if argv is not None else sys.argv,
            data_mode=data_mode,
        )
    except Exception as error:
        print(f"[startup] UI V2 启动失败：{error}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_startup_arguments(argv if argv is not None else sys.argv)
    return run_ui_v2_from_main(
        argv if argv is not None else sys.argv,
        data_mode="mock" if arguments.mock else "real",
    )


if __name__ == "__main__":
    raise SystemExit(main())

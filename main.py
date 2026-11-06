import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ["--worker"]:
        from clipstudio.worker import main as worker
        return worker(args[1:])
    from clipstudio.ui.app import run
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

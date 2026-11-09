"""animetimeline 命令入口。"""
import sys

from .scraper import run

def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()

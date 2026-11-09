"""让 python -m animetimeline 可执行（CI 与打包后都用这个入口）。"""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

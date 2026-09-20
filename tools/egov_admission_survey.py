"""Checkout convenience wrapper; the shipped module contains all runtime code."""

from jlegal_okf.assurance.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())

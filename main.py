"""Ponto de entrada: python main.py [--mock] [--debug]."""
import sys

from app.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())

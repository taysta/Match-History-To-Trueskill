# Standard
import sys


def handle_error(exception, msg):
    print(f"Error: {msg}")
    print(f"Exception: {str(exception)}")
    sys.exit(1)

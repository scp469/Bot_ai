import sys
import os
import logging

# Ensure testing environment flag is set to silence production activity logs during test suites
os.environ["CZN_TESTING"] = "1"

# Add src directory to python search path for all unit tests
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Silence activity logger during test runs
logging.getLogger("ChaosBot.Activity").handlers = [logging.NullHandler()]


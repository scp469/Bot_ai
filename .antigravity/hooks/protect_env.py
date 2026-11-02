import sys
import os

target = sys.argv[1] if len(sys.argv) > 1 else ""
base = os.path.basename(target)
if base.startswith(".env") and base != ".env.example":
    print("BLOCKED: Modification of .env secret files is protected.")
    sys.exit(1)

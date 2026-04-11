import sys
import os

# Add SDK to path so tests can import it
sdk_path = os.path.join(
    os.path.dirname(__file__),  # backend/tests/
    "..",                        # backend/
    "..",                        # project root
    "sdk",
    "python"
)
sys.path.insert(0, os.path.abspath(sdk_path))
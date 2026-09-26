"""Make the test suite hermetic.

The suite must never inherit a developer's local `.env`: `Settings(...)` reads that
file, so an ambient `JOY_MODULES=real` or a machine-specific `MODEL_INVENTORY_JSON`
would change collection-time behavior and fail tests for reasons unrelated to the code
under test. Point the settings loader at a file that does not exist before any test
module imports `app.config`; tests that need real mode pass it explicitly.
"""

import os

os.environ["INDIGENT_ENV_FILE"] = os.path.join(os.sep, "nonexistent", "indigent-test.env")

"""Time `import app.main` and print a full traceback if it raises.

Exists because the startup failure we chase is invisible from Azure: the
readiness probe kills the replica and KEDA scales the deployment to zero, so
`az containerapp logs --type console` answers "Could not find a replica" and the
traceback is lost. Run against the built image on a CI runner instead, where
nothing reaps the container and stdout comes back in full.
"""
import time
import traceback

start = time.time()
try:
    import app.main  # noqa: F401
except BaseException:
    print(f"IMPORT_FAILED after {time.time() - start:.1f}s", flush=True)
    traceback.print_exc()
    raise
else:
    print(f"IMPORT_OK in {time.time() - start:.1f}s", flush=True)

"""Defense-in-depth verification executed in the sandbox image."""
import os
import socket
from pathlib import Path


def must_fail(action) -> None:
    try:
        action()
    except OSError:
        return
    raise AssertionError("sandbox restriction was not enforced")


assert os.geteuid() != 0
must_fail(lambda: socket.create_connection(("1.1.1.1", 53), timeout=1))
must_fail(lambda: Path("/etc/sandbox-write-test").write_text("no"))
Path("/tmp/sandbox-write-test").write_text("ok")
assert not Path("/Users").exists()
assert not Path("/home/host").exists()
assert not Path("/var/run/docker.sock").exists()

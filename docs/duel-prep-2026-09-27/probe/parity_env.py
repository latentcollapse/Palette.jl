"""The environment both arms' tools run in for the polyglot duel.

NeuraJL gets it through NIRA_TASK_TOOLS / NIRA_TASK_ENV (its sandbox builds the rest);
the IPython arm's kernel inherits it from the driver process, which is launched with
the host node by absolute path so the toolchain's own node does not replace it.
"""
import os, pathlib
TOOLCHAIN = pathlib.Path.home() / ".neurajl-runs/toolchains/polyglot"
HOST_NODE = "/usr/bin/node"

def task_env(path=TOOLCHAIN / "task-env"):
    env = {}
    for line in pathlib.Path(path).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            k, _, v = line.partition("="); env[k] = v
    return env

def ipython_arm_env(home, extra=None):
    """The IPython arm's process env: the same PATH head and activation NeuraJL's sandbox sets."""
    env = {"HOME": str(home), "PATH": f"{TOOLCHAIN}/bin:/usr/bin:/bin", "USER": "neura", "LOGNAME": "neura",
           "LANG": "en_US.UTF-8", "PRIME_AGENT_KERNEL_PYTHON": str(pathlib.Path.home() / ".prime/agent/kernel-venv/bin/python3")}
    env.update(task_env()); env.update(extra or {})
    return env

def neurajl_arm_env(base=None):
    """Added to the NeuraJL driver's env; the sandbox sets PATH, HOME, USER itself."""
    env = dict(base or os.environ)
    env.update({"NIRA_TASK_TOOLS": str(TOOLCHAIN), "NIRA_TASK_ENV": str(TOOLCHAIN / "task-env")})
    return env

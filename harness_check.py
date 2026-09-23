
import sys
from pathlib import Path

declared_skills = [
    "agent-message", "agent-observe", "attach-image", "compact", "edit",
    "goal", "refine", "rlm-heartbeat", "websearch",
    "linear", "notion", "prime-intellect", "skill-creator"
]

def check_skill(skill_name):
    mod_name = skill_name.replace("-", "_")
    try:
        if mod_name in sys.modules:
            return True
        else:
            __import__(mod_name)
            return True
    except ImportError:
        return False
    except Exception as e:
        return f"Error: {e}"

results = {name: check_skill(name) for name in declared_skills}
print("=== Prime Agent Harness Self-Check ===")
for skill, ok in results.items():
    status = "✅" if ok is True else "⚠️" if isinstance(ok, str) else "❌"
    print(f"{status} {skill}: {ok if not isinstance(ok, bool) else 'OK'}")

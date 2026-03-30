import sys

from qdrant_client.models import Any, Optional, Dict
if sys.path.count("../") == 0:
    sys.path.insert(0, "../")
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.config.manager import _DEFAULT_TOML
from mind.memory import Memory

global_memory = None

def set_memory(overrides: Optional[Dict[str, Any]] = None):
    global global_memory
    global_memory = Memory(None, _DEFAULT_TOML, overrides=overrides)

def set_test_memory(overrides: Optional[Dict[str, Any]] = None):
    global global_memory
    global_memory = Memory(None, _DEFAULT_TEST_TOML, overrides=overrides)

def test_extract_facts_from_message(message: str):
    Memory._extract_facts(global_memory.llm, message)

def test_extract_facts_from_file(file_path: str):
    with open(file_path, "r") as f:
        lines = f.readlines()
        for line in lines:
            test_extract_facts_from_message(line.strip())

def test_add(role: str, message: str):
    global_memory.add([{"role": role, "content": message}], user_id="test_user")
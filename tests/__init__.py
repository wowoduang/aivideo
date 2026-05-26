import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("AIVIDEO_CONFIG_FILE", str(ROOT / "config.toml"))

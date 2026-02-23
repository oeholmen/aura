
import os
import sys
from pathlib import Path

# --- PyInstaller / Frozen Handling ---
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    # PyInstaller temporary extraction folder for resources (onefile mode)
    # This is where bundle files like 'interface/static' and 'core/identity_base.txt' live
    PROJECT_ROOT = Path(sys._MEIPASS).resolve()
    # Persistent storage for memories/identity must be in user home
    # We use ~/.aura to keep it consistent across updates and prevent loss on app exit
    PERSISTENT_ROOT = Path.home() / ".aura"
else:
    # Development mode: everything is local to the source tree
    PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
    
    # Check if we have write access to the project root
    # If not (e.g. running from /Applications without being 'frozen'), 
    # we MUST use the user home directory for persistent data.
    if os.access(PROJECT_ROOT, os.W_OK):
        PERSISTENT_ROOT = PROJECT_ROOT
    else:
        PERSISTENT_ROOT = Path.home() / ".aura"

def get_path(relative_path: str) -> Path:
    """Get absolute path relative to project root (resources)."""
    return PROJECT_ROOT / relative_path

def get_user_home() -> Path:
    """Get user home directory."""
    return Path.home()

def get_desktop() -> Path:
    """Get user desktop directory."""
    return Path.home() / "Desktop"

# Common implementation directories
CORE_DIR = PROJECT_ROOT / "core"
SKILLS_DIR = PROJECT_ROOT / "skills"
INTERFACE_DIR = PROJECT_ROOT / "interface"

# DATA and LOGS must be persistent
DATA_DIR = PERSISTENT_ROOT / "data"

# Ensure persistent directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

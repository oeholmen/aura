import json
import logging
import os
import sys
import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

# Use our dependency manager for yaml
try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("Aura.Config")

# --- THE SOVEREIGN BOUNDARY ---
INTERNAL_ONLY = os.environ.get("AURA_INTERNAL_ONLY", "1") == "1"

T = TypeVar("T")

class ConfigSource(Enum):
    """Configuration source for debugging"""

    DEFAULT = "default"
    ENV = "environment"
    FILE = "config_file"
    CLI = "command_line"
    RUNTIME = "runtime"

@dataclass
class PathConfig:
    """Centralized path configuration"""

    # Bundle-aware path resolution
    # In macOS .app bundles, sys._MEIPASS = Contents/Frameworks
    # but data files live in Contents/Resources
    @property
    def project_root(self) -> Path:
        # 1. Environment Override (Highest Priority)
        aura_root = os.environ.get("AURA_ROOT")
        if aura_root:
            return Path(aura_root).resolve()

        # 2. Bundle Resolution (macOS .app)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            meipass = Path(sys._MEIPASS)
            # Check if we're in a macOS .app bundle (Contents/Frameworks)
            resources = meipass.parent / "Resources"
            if resources.exists():
                return resources
            return meipass

        # 3. Default: Relative to this file
        return Path(__file__).resolve().parent.parent

    @property
    def base_dir(self) -> Path:
        return self.project_root
    
    home_dir: Path = field(default_factory=lambda: Path.home().resolve() / ".aura")
    
    @property
    def data_dir(self) -> Path:
        # Enforce absolute path to avoid relative 'data' resolution in read-only bundles
        return self.home_dir.resolve() / "data"
    
    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"
    
    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"
    
    @property
    def log_dir(self) -> Path:
        return self.home_dir / "logs"
    
    @property
    def config_file(self) -> Path:
        return self.home_dir / "config.yaml"
    
    @property
    def log_file(self) -> Path:
        return self.log_dir / "aura.log"
    
    def create_directories(self):
        """Create all required directories with secure permissions."""
        directories = [
            self.home_dir,
            self.data_dir,
            self.backup_dir,
            self.log_dir,
            self.memory_dir,
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                if os.name != 'nt':
                    directory.chmod(0o700) # Secure: User-only
            except Exception as e:
                logger.warning("Failed to create directory %s: %s", directory, e)
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "base_dir": str(self.base_dir),
            "home_dir": str(self.home_dir),
            "data_dir": str(self.data_dir),
            "memory_dir": str(self.memory_dir),
            "backup_dir": str(self.backup_dir),
            "log_dir": str(self.log_dir),
            "config_file": str(self.config_file),
            "log_file": str(self.log_file),
        }

@dataclass
class SecurityConfig:
    """Security configuration - HARDENED for Sovereign Deployment"""

    internal_only_mode: bool = False  # Set to False for Infinity
    auto_fix_enabled: bool = True 
    aura_full_autonomy: bool = True  # Enabled for Sovereign Autonomy
    enableautonomy: bool = True
    require_human_approval_for: List[str] = field(default_factory=list) # Unhindered operation
    max_modifications_per_day: int = 100 # Increased for high-activity autonomy
    allow_network_access: bool = True # Enabled for Live connectivity
    allowed_domains: List[str] = field(default_factory=lambda: ["*"]) # Wildcard for Infinity
    enable_stealth_mode: bool = True  # Enabled for operational security
    unity_enabled: bool = False # SEVERED: Disable phantom body until Unity is active
    force_unity_on: bool = False # Allow manual override of unity status in HUD

@dataclass
class SafeModificationConfig:
    """Safety limits for autonomous self-repair"""
    allowed_paths: List[str] = field(default_factory=lambda: ["core/", "skills/", "interface/"])
    max_risk_level: int = 4
    max_lines_changed: int = 100
    backup_max_age_days: int = 7
    auto_commit: bool = True

@dataclass
class RedisConfig:
    """Redis configuration for inter-process communication (Celery & Events)"""
    url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    enabled: bool = True
    use_for_events: bool = True
    # H-28 FIX: Force memory mode if Redis is disabled to prevent library retry delays
    broker_url: str = field(default_factory=lambda: "memory://" if os.environ.get("AURA_REDIS_ENABLED") == "0" else os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    result_backend: str = field(default_factory=lambda: "cache+memory://" if os.environ.get("AURA_REDIS_ENABLED") == "0" else os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

@dataclass
class LLMConfig:
    """LLM configuration - TIERED for Infinity Autonomy"""

    provider: str = "ollama" 
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = "ollama"
    
    # Tier 1: Conversation (Ultra-fast)
    fast_model: str = "llama3:latest"
    fast_max_tokens: int = 512
    temperature: float = 0.7
    
    # Tier 2: Deep Reasoning (M1 Pro optimized)
    deep_model: str = "llama3:latest"
    deep_max_tokens: int = 2048
    deep_temperature: float = 0.3
    
    # Vision & Audio
    vision_model: str = "llava"
    whisper_model: str = "small.en"
    embedding_model: str = "nomic-embed-text"
    
    # Legacy fields for compatibility
    @property
    def model(self) -> str:
        return self.fast_model

    @property
    def max_tokens(self) -> int:
        return self.fast_max_tokens

@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    file_output: bool = True
    max_file_size_mb: int = 50
    backup_count: int = 5

class AuraConfig:
    """Main configuration class with Sovereign Hardening.
    THREAD-SAFE SINGLETON implementation.
    """

    _instance: Optional['AuraConfig'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AuraConfig, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self.paths = PathConfig()
        self.security = SecurityConfig()
        # SecurityConfig dataclass defaults are the single source of truth.
        # Operators can override via config file or env vars.
        
        
        self.llm = LLMConfig()
        self.modification = SafeModificationConfig()
        self.redis = RedisConfig()
        self.logging = LoggingConfig()
        self.logging_level = "INFO"
        
        self._source_tracking: Dict[str, ConfigSource] = {}
        self._env_prefix = "AURA_"
        
        self.load()
        self._initialized = True
    
    def load(self):
        """Bootstrap configuration sequence."""
        if self.security.internal_only_mode:
            os.environ.setdefault("AURA_INTERNAL_ONLY", "1")
        self.paths.create_directories()
        self._track_defaults()
        if self.paths.config_file.exists():
            self._load_from_file()
        self._load_from_env()
        
        # H-12 Resilience: Auto-disable Redis if Celery is missing
        try:
            import celery
        except ImportError:
            if self.redis.enabled or self.redis.use_for_events:
                logger.info("📡 Celery module missing — force-disabling Redis IPC fallback.")
                self.redis.enabled = False
                self.redis.use_for_events = False
                
        self.validate()
    
    def _track_defaults(self):
        for field_path in self._get_all_fields():
            self._source_tracking[field_path] = ConfigSource.DEFAULT
    
    def _load_from_file(self):
        if not yaml:
            logger.warning("PyYAML not installed, skipping config file loading.")
            return
        try:
            with open(self.paths.config_file, 'r') as f:
                config_data = yaml.safe_load(f) or {}
            self._apply_config_dict(config_data, ConfigSource.FILE)
        except Exception as e:
            logger.error("Failed to load config file: %s", e)
    
    def _load_from_env(self):
        for field_path in self._get_all_fields():
            env_var = f"{self._env_prefix}{field_path.upper().replace('.', '_')}"
            if env_var in os.environ:
                value = os.environ[env_var]
                typed_value = self._parse_env_value(field_path, value)
                if typed_value is not None:
                    self._set_nested_value(field_path, typed_value)
                    self._source_tracking[field_path] = ConfigSource.ENV
    
    def _parse_env_value(self, field_path: str, value: str) -> Any:
        try:
            current = self._get_nested_value(field_path)
            if isinstance(current, bool):
                return value.lower() in ('true', 'yes', '1', 'on')
            elif isinstance(current, int):
                return int(value)
            elif isinstance(current, float):
                return float(value)
            elif isinstance(current, list):
                return [item.strip() for item in value.split(',')]
            elif isinstance(current, Path):
                return Path(value)
            return value
        except Exception:
            return None
    
    def _apply_config_dict(self, config_dict: Dict[str, Any], source: ConfigSource):
        for section_name, section_values in config_dict.items():
            if not isinstance(section_values, dict): continue
            if hasattr(self, section_name):
                section = getattr(self, section_name)
                for k, v in section_values.items():
                    if hasattr(section, k):
                        setattr(section, k, v)
                        self._source_tracking[f"{section_name}.{k}"] = source

    def _get_nested_value(self, field_path: str) -> Any:
        parts = field_path.split('.')
        obj = self
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise AttributeError(f"Field not found: {field_path}")
        return obj
    
    def _set_nested_value(self, field_path: str, value: Any):
        parts = field_path.split('.')
        obj = self
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
    
    def _get_all_fields(self) -> List[str]:
        fields = []
        for section_name in ['paths', 'security', 'llm', 'modification', 'redis', 'logging']:
            section = getattr(self, section_name)
            if is_dataclass(section):
                for f in section.__dataclass_fields__.keys():
                    fields.append(f"{section_name}.{f}")
            # Also include @property attributes
            cls = type(section)
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name)
                if isinstance(attr, property):
                    field_path = f"{section_name}.{attr_name}"
                    if field_path not in fields:
                        fields.append(field_path)
        return fields
    
    def validate(self):
        """Strict validation of configuration integrity."""
        errors = []
        if self.security.internal_only_mode and not INTERNAL_ONLY:
            errors.append("Security mismatch: Internal mode requested but env barrier missing.")
        
        if self.llm.provider == "ollama" and not self.llm.base_url.startswith("http"):
            errors.append(f"Invalid Ollama URL: {self.llm.base_url}")
            
        if errors:
            for err in errors:
                logger.error("Config Validation Error: %s", err)
            raise ValueError(f"Configuration failed validation: {'; '.join(errors)}")

    def save(self, path: Optional[Path] = None):
        """Save current configuration with JSON fallback."""
        save_path = path or self.paths.config_file
        
        def normalize(obj):
            if isinstance(obj, dict):
                return {k: normalize(v) for k, v in obj.items()}
            elif isinstance(obj, Path):
                return str(obj)
            elif isinstance(obj, list):
                return [normalize(i) for i in obj]
            elif is_dataclass(obj) and not isinstance(obj, type):
                return normalize(asdict(obj))
            return obj

        config_dict = normalize({
            "paths": self.paths,
            "security": self.security,
            "llm": self.llm,
            "modification": self.modification,
            "redis": self.redis,
        })

        try:
            if yaml:
                with open(save_path, 'w') as f:
                    yaml.dump(config_dict, f, default_flow_style=False)
            else:
                json_path = save_path.with_suffix('.json')
                with open(json_path, 'w') as f:
                    json.dump(config_dict, f, indent=4)
                logger.info("PyYAML missing, saved to %s", json_path)
        except Exception as e:
            logger.error("Failed to save configuration: %s", e)

    def generate_report(self) -> str:
        report = ["Configuration Report:", "=" * 50]
        for field_path in sorted(self._get_all_fields()):
            val = self._get_nested_value(field_path)
            source = self._source_tracking.get(field_path, ConfigSource.DEFAULT)
            report.append(f"  {field_path:30} = {str(val)[:50]:30} ({source.value})")
        return "\n".join(report)

# Global instance
config = AuraConfig()

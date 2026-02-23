from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel


class BaseSkill(ABC):
    """Base class for all Aura skills.
    Enforces Pydantic input models for type safety and self-documentation.
    """

    name: str = "base_skill"
    description: str = "Base skill description"
    
    # input_model should be a Pydantic BaseModel class
    # If None, the skill takes no parameters or raw dict (legacy)
    input_model: Optional[Type[BaseModel]] = None
    
    # Metabolic Tagging (0=Core, 1=Light, 2=Medium, 3=Heavy)
    metabolic_cost: int = 1
    is_core_personality: bool = False

    @abstractmethod
    async def execute(self, params: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill.
        :param params: The parsed input model (or dict if no model)
        :param context: Execution context (agent state, etc.)
        :return: Result dictionary
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Generate JSON schema for the skill's input parameters.
        """
        if self.input_model:
            return self.input_model.model_json_schema()
        return {}

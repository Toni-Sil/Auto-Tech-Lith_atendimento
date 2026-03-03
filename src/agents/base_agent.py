from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseAgent(ABC):
    @abstractmethod
    async def process_message(self, message: str, context:  Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        pass

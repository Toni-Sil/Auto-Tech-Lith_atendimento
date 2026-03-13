from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseAgent(ABC):
    @abstractmethod
    async def process_message(self, message: str, context: Dict[str, Any]) -> str:
        """
        Processa a mensagem principal do usuário, gerencia a conversa e executa tool-calling se necessário.
        Deve retornar a string de resposta final a ser enviada ao usuário.
        """
        pass

    @abstractmethod
    async def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """
        Retorna o prompt de sistema que define a identidade, capacidades e regras do agente.
        """
        pass

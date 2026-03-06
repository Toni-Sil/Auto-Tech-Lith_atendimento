"""
Client Service
Antigravity Skill: business-logic
"""
from typing import Dict, Any, List, Optional
from app.infrastructure.database.supabase_client import SupabaseClient
from app.services.validation_service import ValidationService
from app.utils.logger import get_logger

logger = get_logger(__name__)

class ClientService:
    def __init__(self):
        self.supabase = SupabaseClient.get_client()
        self.validator = ValidationService()

    async def register_client(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registers or updates a client with validation and deduplication.
        """
        # 1. Sanitize
        clean_data = self.validator.sanitize_data(data)
        
        # 2. Validate
        # Email
        if "email" in clean_data:
            is_valid, error = self.validator.validate_email(clean_data["email"])
            if not is_valid:
                return {"status": "error", "message": f"E-mail inválido: {error}"}
                
        # Phone (Mandatory)
        if "phone" in clean_data:
            is_valid, error = self.validator.validate_phone(clean_data["phone"])
            if not is_valid:
                return {"status": "error", "message": f"Telefone inválido: {error}"}
        else:
            return {"status": "error", "message": "Telefone é obrigatório."}

        # Name
        if "name" in clean_data:
            is_valid, error = self.validator.validate_name(clean_data["name"])
            if not is_valid:
                return {"status": "error", "message": f"Nome inválido: {error}"}

        from app.config.settings import get_settings
        settings = get_settings()

        # 3. Deduplication (Find similar)
        existing = await self.find_client_by_phone(clean_data["phone"])
        
        # Prepare DB Payload
        db_payload = {
            "phone": clean_data["phone"],
            "name": clean_data.get("name"),
            "company": clean_data.get("company"),
            "email": clean_data.get("email"),
            "initial_demand": clean_data.get("niche"),
            "admin_instruction": clean_data.get("pain_point"),
            "tenant_id": settings.tenant_id,
        }
        # Remove None values to avoid overwriting existing data with null
        db_payload = {k: v for k, v in db_payload.items() if v is not None}

        try:
            if existing:
                # Update
                self.supabase.table("customers").update(db_payload).eq("id", existing["id"]).execute()
                action = "updated"
                msg = f"Dados de {clean_data.get('name', 'cliente')} atualizados."
            else:
                # Create
                self.supabase.table("customers").insert(db_payload).execute()
                action = "created"
                msg = f"Cliente {clean_data.get('name')} cadastrado com sucesso."
                
            return {"status": "success", "action": action, "message": msg, "data": clean_data}
            
        except Exception as e:
            logger.error(f"DB Error in register_client: {e}")
            return {"status": "error", "message": "Erro interno ao salvar dados."}

    async def find_client_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Finds client by phone (exact match after cleaning)."""
        clean_phone = self.validator.sanitize_data({"phone": phone})["phone"]
        try:
            res = self.supabase.table("customers").select("*").eq("phone", clean_phone).execute()
            if res.data:
                return res.data[0]
            return None
        except Exception:
            return None

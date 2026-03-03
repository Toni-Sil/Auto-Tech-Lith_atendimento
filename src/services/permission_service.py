from enum import Enum
from typing import Optional

class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

class Action(str, Enum):
    LIST = "list"
    Create = "create"
    UPDATE = "update"
    DELETE = "delete"
    SEARCH = "search"
    SCHEDULE = "schedule"
    CANCEL = "cancel"
    # Special actions
    GET_SUMMARY = "get_daily_summary"
    SAVE_NOTE = "save_note"
    GET_NOTES = "get_notes"
    MANAGE_ADMINS = "manage_admins"

class PermissionResult(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    NEEDS_CONFIRMATION = "needs_confirmation"

class PermissionService:
    @staticmethod
    def get_role_from_string(role_str: str) -> Role:
        try:
            return Role(role_str.lower())
        except ValueError:
            return Role.VIEWER # Default safe fallback

    @staticmethod
    def check_permission(role: Role, tool_name: str, action: Optional[str] = None) -> PermissionResult:
        """
        Matriz de Permissões:
        - OWNER: Tudo permitido.
        - ADMIN: Tudo permitido, mas DELETE requer confirmação.
        - OPERATOR: Leitura/Escrita permitida. DELETE proibido. Gestão de admins proibida.
        - VIEWER: Apenas leitura.
        """
        
        # 1. OWNER has god mode
        if role == Role.OWNER:
            return PermissionResult.ALLOWED
        
        # Normalize inputs
        tool = tool_name.lower()
        act = action.lower() if action else ""

        # 2. VIEWER (Read-only)
        if role == Role.VIEWER:
            if tool in ["get_daily_summary", "get_notes"]:
                return PermissionResult.ALLOWED
            if act in ["list", "search", "read"]:
                return PermissionResult.ALLOWED
            return PermissionResult.DENIED

        # 3. OPERATOR (No Delete, No Admin Management)
        if role == Role.OPERATOR:
            if tool == "manage_admins":
                return PermissionResult.DENIED
            
            if act == "delete" or act == "cancel":
                return PermissionResult.DENIED
            
            return PermissionResult.ALLOWED

        # 4. ADMIN (Restricted Deletes)
        if role == Role.ADMIN:
            # Sensitive operations require confirmation
            if act == "delete" or act == "cancel":
                return PermissionResult.NEEDS_CONFIRMATION
            
            if tool == "manage_admins" and act == "delete":
                 return PermissionResult.NEEDS_CONFIRMATION

            return PermissionResult.ALLOWED

        return PermissionResult.DENIED

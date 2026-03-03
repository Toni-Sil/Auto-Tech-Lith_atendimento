import pytest
from src.services.permission_service import PermissionService, Role, PermissionResult

def test_owner_permissions():
    assert PermissionService.check_permission(Role.OWNER, "manage_customers", "delete") == PermissionResult.ALLOWED
    assert PermissionService.check_permission(Role.OWNER, "manage_admins", "delete") == PermissionResult.ALLOWED

def test_admin_permissions():
    # Admin can list/update freely
    assert PermissionService.check_permission(Role.ADMIN, "manage_customers", "update") == PermissionResult.ALLOWED
    # Admin needs confirmation to delete
    assert PermissionService.check_permission(Role.ADMIN, "manage_customers", "delete") == PermissionResult.NEEDS_CONFIRMATION
    assert PermissionService.check_permission(Role.ADMIN, "manage_meetings", "cancel") == PermissionResult.NEEDS_CONFIRMATION
    # Admin needs confirmation to delete another admin
    assert PermissionService.check_permission(Role.ADMIN, "manage_admins", "delete") == PermissionResult.NEEDS_CONFIRMATION

def test_operator_permissions():
    # Operator can list/update
    assert PermissionService.check_permission(Role.OPERATOR, "manage_customers", "update") == PermissionResult.ALLOWED
    assert PermissionService.check_permission(Role.OPERATOR, "manage_tickets", "create") == PermissionResult.ALLOWED
    # Operator CANNOT delete
    assert PermissionService.check_permission(Role.OPERATOR, "manage_customers", "delete") == PermissionResult.DENIED
    assert PermissionService.check_permission(Role.OPERATOR, "manage_meetings", "cancel") == PermissionResult.DENIED
    # Operator CANNOT manage admins
    assert PermissionService.check_permission(Role.OPERATOR, "manage_admins", "list") == PermissionResult.DENIED
    assert PermissionService.check_permission(Role.OPERATOR, "manage_admins", "delete") == PermissionResult.DENIED

def test_viewer_permissions():
    # Viewer can read
    assert PermissionService.check_permission(Role.VIEWER, "get_daily_summary") == PermissionResult.ALLOWED
    assert PermissionService.check_permission(Role.VIEWER, "manage_customers", "search") == PermissionResult.ALLOWED
    assert PermissionService.check_permission(Role.VIEWER, "manage_customers", "list") == PermissionResult.ALLOWED
    # Viewer CANNOT update/create
    assert PermissionService.check_permission(Role.VIEWER, "manage_customers", "create") == PermissionResult.DENIED
    assert PermissionService.check_permission(Role.VIEWER, "manage_tickets", "create") == PermissionResult.DENIED

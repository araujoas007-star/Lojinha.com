from django.core.exceptions import PermissionDenied


ATENDENTE_GROUP = "Atendente"
GERENTE_GROUP = "Gerente"


def is_manager(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=GERENTE_GROUP).exists()
    ))


def can_access_store(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser
        or user.groups.filter(name__in=[ATENDENTE_GROUP, GERENTE_GROUP]).exists()
    ))


def require_manager(user):
    if not is_manager(user):
        raise PermissionDenied

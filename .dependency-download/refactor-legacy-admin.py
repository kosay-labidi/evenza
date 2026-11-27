from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from . import models
from .modules import SECTIONS

admin.site.site_header = "Administration Évenza"
admin.site.site_title = "Évenza"


class CreateUserForm(AdminUserCreationForm):
    class Meta:
        model = models.User
        fields = ("email", "name", "role")


class ChangeUserForm(UserChangeForm):
    class Meta:
        model = models.User
        fields = "__all__"


@admin.register(models.User)
class EvenzaUserAdmin(UserAdmin):
    form = ChangeUserForm
    add_form = CreateUserForm
    list_display = ("email", "name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "name")
    ordering = ("name",)
    readonly_fields = ("last_login", "created_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("name", "phone", "role", "availability", "skills")}),
        ("Accès", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "role", "password1", "password2")}),)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and obj != request.user


for section in SECTIONS.values():
    if section.model is models.User:
        continue
    options = {
        "list_display": tuple(section.columns.split()),
        "list_filter": (section.filter,),
        "search_fields": tuple(section.search.split()),
        "list_select_related": True,
    }
    admin.site.register(section.model, type(f"{section.model.__name__}Admin", (admin.ModelAdmin,), options))


@admin.register(models.Activity, models.LoginAttempt, models.Notification, models.Document)
class HistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_exclude(self, request, obj=None):
        return ("content",) if self.model is models.Document else ()


@admin.register(models.LoginAlert)
class LoginAlertAdmin(HistoryAdmin):
    list_display = ("email", "ip", "created_at")
    search_fields = ("email", "ip")


"""
Tenant + custom User.

Padrão SaaS B2B: cada User pertence a um Tenant (FK). Superuser global
pode ter tenant=NULL pra trafegar livre no admin. Users de tenant
sempre têm tenant não-nulo (validado no UserManager).

Email é o USERNAME_FIELD — sem `username` separado, simplifica.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Tenant(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"

    def __str__(self):
        return self.slug


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("email é obrigatório")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, tenant=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        if tenant is None:
            raise ValueError("user normal precisa de um tenant")
        return self._create_user(email, password, tenant=tenant, **extra)

    def create_superuser(self, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("superuser precisa is_staff=is_superuser=True")
        # superuser pode rodar sem tenant (admin global)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        help_text="NULL apenas para superuser global. Users de produto sempre têm tenant.",
    )
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "user"

    def __str__(self):
        return self.email

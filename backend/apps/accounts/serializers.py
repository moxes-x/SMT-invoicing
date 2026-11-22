from typing import Any

from django.contrib.auth import authenticate, password_validation
from rest_framework import serializers

from apps.core.validators import normalize_phone

from .models import Business, Membership, User

SMART_INVOICE_NOTICE = (
    "VAT-registered businesses must issue tax invoices for taxable supplies through ZRA Smart "
    "Invoice. Documents from this app are plain invoices, not tax invoices, but you can still use "
    "it to track who has paid."
)


class BusinessSerializer(serializers.ModelSerializer[Business]):
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    role = serializers.SerializerMethodField()
    compliance_notice = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "tpin",
            "vat_registered",
            "payment_details",
            "default_currency",
            "auto_reminders",
            "reminder_interval_days",
            "max_reminders",
            "role",
            "compliance_notice",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_role(self, obj: Business) -> str | None:
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        m = obj.memberships.filter(user=request.user).first()
        return m.role if m else None

    def get_compliance_notice(self, obj: Business) -> str | None:
        return SMART_INVOICE_NOTICE if obj.vat_registered else None

    def validate_phone(self, value: str) -> str:
        if not value:
            return value
        try:
            return normalize_phone(value)
        except Exception as exc:
            raise serializers.ValidationError("Enter a valid phone number.") from exc


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "full_name"]
        read_only_fields = ["id", "email"]


class MeSerializer(serializers.Serializer[Any]):
    user = UserSerializer()
    current_business = BusinessSerializer(allow_null=True)
    businesses = BusinessSerializer(many=True)


class SignupSerializer(serializers.Serializer[User]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        candidate = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data: dict[str, str]) -> User:
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer[User]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict[str, str]) -> dict[str, object]:
        user = authenticate(
            self.context["request"], username=attrs["email"].lower(), password=attrs["password"]
        )
        if user is None:
            raise serializers.ValidationError("Incorrect email or password.")
        return {"user": user}


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]

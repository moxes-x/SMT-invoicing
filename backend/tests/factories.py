import factory

from apps.accounts.models import Business, Membership, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    password = factory.PostGenerationMethodCall("set_password", "correct-horse-battery")

    @factory.post_generation
    def _save(obj, create, extracted, **kwargs):  # noqa: N805
        if create:
            obj.save()


class BusinessFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Business

    name = factory.Sequence(lambda n: f"Business {n}")
    email = factory.Sequence(lambda n: f"shop{n}@example.com")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    business = factory.SubFactory(BusinessFactory)
    role = Membership.Role.OWNER


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "customers.Customer"

    business = factory.SubFactory(BusinessFactory)
    name = factory.Sequence(lambda n: f"Customer {n}")
    phone = "+260971234567"
    email = factory.Sequence(lambda n: f"customer{n}@example.com")


class ItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "catalog.Item"

    business = factory.SubFactory(BusinessFactory)
    name = factory.Sequence(lambda n: f"Item {n}")
    unit_price = 10000


def make_invoice(business, *, lines=None, user=None, send=False, **fields):
    """Create an invoice through the service layer, like the API does."""
    import datetime as dt
    from decimal import Decimal

    from apps.invoices.services import create_invoice, send_invoice

    fields.setdefault("customer", CustomerFactory(business=business))
    fields.setdefault("issue_date", dt.date(2026, 11, 1))
    fields.setdefault("due_date", dt.date(2026, 11, 15))
    lines = lines or [{"description": "Haircut", "quantity": Decimal("1"), "unit_price": 50000}]
    invoice = create_invoice(business, user, lines=lines, **fields)
    if send:
        invoice = send_invoice(invoice, user)
    return invoice

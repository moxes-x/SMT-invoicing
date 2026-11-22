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

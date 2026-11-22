import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from .factories import MembershipFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner_a():
    return MembershipFactory()


@pytest.fixture
def owner_b():
    return MembershipFactory()


@pytest.fixture
def client_a(owner_a) -> APIClient:
    client = APIClient()
    client.force_login(owner_a.user)
    return client


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttling counters live in the cache
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_BASE_URL = "https://app.example.com"


@pytest.fixture
def time_machine():
    """Freeze/move time: time_machine.move_to("2026-11-15T22:00:00Z")."""
    import time_machine as tm

    class Mover:
        traveller = None

        def move_to(self, when):
            if self.traveller is not None:
                self.traveller.stop()
            self.traveller = tm.travel(when, tick=False)
            self.traveller.start()

    mover = Mover()
    yield mover
    if mover.traveller is not None:
        mover.traveller.stop()


class FakeMeta:
    """Stands in for graph.facebook.com. Records requests; fail_with makes the next send fail."""

    def __init__(self):
        self.requests = []
        self.fail_with = None  # (status_code, error_code)
        self.counter = 0

    def handler(self, request):
        import httpx

        self.requests.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-1"})
        if self.fail_with:
            status, code = self.fail_with
            return httpx.Response(status, json={"error": {"message": "boom", "code": code}})
        self.counter += 1
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{self.counter}"}]})

    def sent_payloads(self):
        import json

        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/messages")]


@pytest.fixture
def whatsapp_api(settings, monkeypatch):
    import httpx

    settings.WHATSAPP_TOKEN = "test-token"
    settings.WHATSAPP_PHONE_NUMBER_ID = "123456"
    settings.WHATSAPP_APP_SECRET = "app-secret"
    settings.WHATSAPP_VERIFY_TOKEN = "verify-me"
    fake = FakeMeta()
    real_client = httpx.Client
    monkeypatch.setattr(
        "apps.messaging.whatsapp.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(fake.handler)),
    )
    return fake


class FakeLenco:
    """Stands in for api.lenco.co. Set `collect` / `statuses[reference]` to script answers."""

    def __init__(self):
        self.requests = []
        self.collect = {"status": "pay-offline"}
        self.statuses = {}  # reference -> data dict, or an int HTTP status
        self.error = None  # (http_status, message) for the next call

    @staticmethod
    def data(reference, status, amount="500.00", **extra):
        return {
            "id": f"lenco-{reference}",
            "amount": amount,
            "fee": "5.00",
            "currency": "ZMW",
            "reference": reference,
            "lencoReference": f"LR{abs(hash(reference)) % 10**8}",
            "type": "mobile-money",
            "status": status,
            "reasonForFailure": None,
            "mobileMoneyDetails": {"country": "zm", "phone": "0961111111", "operator": "mtn"},
            **extra,
        }

    def handler(self, request):
        import json

        import httpx

        self.requests.append(request)
        if self.error:
            status, message = self.error
            self.error = None
            return httpx.Response(status, json={"status": False, "message": message})
        if request.method == "POST" and request.url.path.endswith("/collections/mobile-money"):
            body = json.loads(request.content)
            data = self.data(body["reference"], **self.collect)
            return httpx.Response(200, json={"status": True, "message": "", "data": data})
        if "/collections/status/" in request.url.path:
            reference = request.url.path.rsplit("/", 1)[-1]
            answer = self.statuses.get(reference, 404)
            if isinstance(answer, int):
                return httpx.Response(answer, json={"status": False, "message": "Not found"})
            return httpx.Response(200, json={"status": True, "message": "", "data": answer})
        return httpx.Response(404, json={"status": False, "message": "Unknown path"})

    def bodies(self):
        import json

        return [json.loads(r.content) for r in self.requests if r.method == "POST"]


@pytest.fixture
def lenco_api(monkeypatch):
    import httpx

    fake = FakeLenco()
    real_client = httpx.Client
    monkeypatch.setattr(
        "apps.payments.lenco.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(fake.handler)),
    )
    return fake


@pytest.fixture
def lenco_account(owner_a):
    from apps.payments.models import LencoAccount

    account = LencoAccount(business=owner_a.business, enabled=True, public_key="pub-test-key")
    account.secret_key = "sk-test-secret-0000"
    account.save()
    return account


class FakeVsdc:
    """Stands in for ZRA's VSDC. `fail` makes the next call to a path answer with an error."""

    def __init__(self):
        self.requests = []
        self.fail: dict[str, tuple[str, str]] = {}
        self.receipt = 100

    def handler(self, request):
        import json

        import httpx

        body = json.loads(request.content)
        path = "/" + request.url.path.split("/", 2)[-1]
        self.requests.append((path, body))
        if path in self.fail:
            code, message = self.fail.pop(path)
            return httpx.Response(200, json={"resultCd": code, "resultMsg": message})
        data = None
        if path == "/initializer/selectInitInfo":
            data = {"info": {"sdcId": "SDC0010000001", "mrcNo": "MRC-1"}}
        elif path in ("/trnsSales/saveSales", "/trnsSales/selectInvoice"):
            self.receipt += 1
            data = {
                "rcptNo": self.receipt,
                "intrlData": "INTRLDATA" + body["cisInvcNo"],
                "rcptSign": "SIGN" + body["cisInvcNo"],
                "vsdcRcptPbctDate": "20261101120000",
                "sdcId": "SDC0010000001",
                "mrcNo": "MRC-1",
                "qrCodeUrl": f"https://sandboxportal.zra.org.zm/verify?r={self.receipt}",
            }
        return httpx.Response(
            200,
            json={"resultCd": "000", "resultMsg": "It is succeeded", "resultDt": "x", "data": data},
        )

    def calls(self, path):
        return [body for p, body in self.requests if p == path]


@pytest.fixture
def vsdc_api(monkeypatch):
    import httpx

    fake = FakeVsdc()
    real_client = httpx.Client
    monkeypatch.setattr(
        "apps.fiscal.vsdc.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(fake.handler)),
    )
    return fake


@pytest.fixture
def zra_device(owner_a):
    from apps.fiscal.models import ZraDevice

    business = owner_a.business
    business.vat_registered = True
    business.tpin = "1000000000"
    business.save()
    return ZraDevice.objects.create(
        business=business,
        enabled=True,
        device_serial="20180520000000",
        item_class_code="50102518",
        sdc_id="SDC0010000001",
    )

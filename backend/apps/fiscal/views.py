from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import HasBusiness, require_business, require_manager
from apps.payments.serializers import ConnectionTestSerializer

from . import vsdc
from .models import ZraDevice
from .serializers import ZraDeviceSerializer


def _device(request: Request) -> ZraDevice:
    device, _ = ZraDevice.objects.select_related("business").get_or_create(
        business=require_business(request)
    )
    return device


@extend_schema(methods=["GET"], responses=ZraDeviceSerializer)
@extend_schema(methods=["PUT"], request=ZraDeviceSerializer, responses=ZraDeviceSerializer)
@api_view(["GET", "PUT"])
@permission_classes([HasBusiness])
def zra_device(request: Request) -> Response:
    """The business's ZRA Smart Invoice (VSDC) settings."""
    device = _device(request)
    if request.method == "PUT":
        require_manager(request)
        ser = ZraDeviceSerializer(device, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
    return Response(ZraDeviceSerializer(device).data)


@extend_schema(request=None, responses=ConnectionTestSerializer)
@api_view(["POST"])
@permission_classes([HasBusiness])
def test_zra_device(request: Request) -> Response:
    """Initialise the device on the VSDC (selectInitInfo) and keep its SDC ID and MRC number."""
    require_manager(request)
    device = _device(request)
    if not device.business.tpin or not device.device_serial:
        return Response({"ok": False, "message": "Add your TPIN and device serial first."})
    try:
        answer = vsdc.Client(device).init_info()
    except vsdc.VsdcError as exc:
        device.last_error = str(exc)[:300]
        device.save(update_fields=["last_error", "updated_at"])
        return Response({"ok": False, "message": str(exc)})
    fields = vsdc.init_fields(answer)
    device.sdc_id = fields["sdc_id"] or device.sdc_id
    device.mrc_no = fields["mrc_no"] or device.mrc_no
    device.initialized_at = timezone.now()
    device.last_error = ""
    device.save()
    sdc = f" SDC ID {device.sdc_id}." if device.sdc_id else ""
    return Response({"ok": True, "message": f"Connected to the ZRA VSDC.{sdc}"})

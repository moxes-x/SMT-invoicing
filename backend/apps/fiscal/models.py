"""ZRA Smart Invoice (VSDC) for VAT-registered businesses.

A business that fiscalises has one ZraDevice: the VSDC (Virtual Sales Data Controller) that ZRA
gives each taxpayer branch. Every invoice sent while it is on is reported to the VSDC, which
signs it; the signed answer is a FiscalReceipt. Voiding a fiscalised invoice reports a credit note,
which is a second FiscalReceipt. Only fiscalised invoices are called "Tax Invoice".
"""

from __future__ import annotations

from django.db import models

from apps.accounts.models import Business


class VatCategory(models.TextChoices):
    """ZRA VAT categories (vatCatCd). Prices are VAT-inclusive, as in ZRA's examples."""

    STANDARD = "A", "Standard rated (16%)"
    EXPORT = "C1", "Exports (0%)"
    ZERO_LPO = "C2", "Zero-rated by LPO (0%)"
    ZERO = "C3", "Zero-rated by nature (0%)"
    EXEMPT = "D", "Exempt"


class ItemType(models.TextChoices):
    """ZRA product type (itemTyCd, spec 6.2)."""

    GOODS = "2", "Goods (finished products)"
    SERVICE = "3", "Services (no stock)"


# Tax rate (percent) for each category, as the VSDC expects in taxRt*.
VAT_RATES = {"A": 16, "B": 16, "C1": 0, "C2": 0, "C3": 0, "D": 0}


class ZraDevice(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="zra")
    enabled = models.BooleanField(
        default=False, help_text="Report every sent invoice to ZRA and issue it as a tax invoice."
    )
    vsdc_url = models.URLField(
        "VSDC address",
        default="http://localhost:8080/zrasandboxvsdc",
        help_text="Where your ZRA VSDC runs, e.g. http://10.0.0.5:8080/zrasandboxvsdc",
    )
    branch_id = models.CharField("Branch ID (bhfId)", max_length=3, default="000")
    device_serial = models.CharField("Device serial (dvcSrlNo)", max_length=50, blank=True)
    item_class_code = models.CharField(
        "Item classification code",
        max_length=10,
        blank=True,
        help_text="ZRA item class code used for your items (from ZRA's code list).",
    )
    item_type = models.CharField(
        max_length=1,
        choices=ItemType.choices,
        default=ItemType.SERVICE,
        help_text="ZRA product type for your items. Goods also need stock reports to ZRA.",
    )
    default_vat_category = models.CharField(
        max_length=2, choices=VatCategory.choices, default=VatCategory.STANDARD
    )
    payment_type = models.CharField(
        max_length=2,
        default="02",
        help_text="ZRA payment method (pmtTyCd, spec 6.9). 02 is credit: invoices are paid later.",
    )
    # From the VSDC's device initialisation answer.
    sdc_id = models.CharField(max_length=50, blank=True)
    mrc_no = models.CharField(max_length=50, blank=True)
    initialized_at = models.DateTimeField(null=True, blank=True)
    registered_items = models.JSONField(
        default=dict, blank=True, help_text="{item code: VAT category} already saved on the VSDC."
    )
    last_error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"VSDC {self.business_id}/{self.branch_id}"

    @property
    def is_ready(self) -> bool:
        tpin = self.business.tpin
        return bool(
            self.enabled
            and self.business.vat_registered
            and tpin
            and self.device_serial
            and self.item_class_code
        )


class FiscalReceipt(models.Model):
    class Kind(models.TextChoices):
        SALE = "sale", "Tax invoice"
        CREDIT = "credit", "Credit note"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.PROTECT, related_name="fiscal_receipts"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SALE)
    document_number = models.CharField(
        max_length=50, help_text="Our number sent as cisInvcNo (the invoice or credit note number)"
    )
    receipt_no = models.CharField(max_length=50, blank=True)
    sdc_id = models.CharField(max_length=50, blank=True)
    mrc_no = models.CharField(max_length=50, blank=True)
    internal_data = models.CharField(max_length=200, blank=True)
    signature = models.CharField(max_length=200, blank=True)
    qr_url = models.URLField(max_length=500, blank=True)
    signed_at = models.CharField(max_length=20, blank=True, help_text="As the VSDC sent it")
    taxable_total = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    tax_total = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    vat_summary = models.JSONField(
        default=list, help_text="[{category, rate, taxable, tax}] in major units, as reported"
    )
    request = models.JSONField(default=dict)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["invoice", "kind"], name="one_fiscal_receipt_per_kind")
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.document_number} ({self.receipt_no})"

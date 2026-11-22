"""Customer-facing words in English, Bemba and Nyanja.

Used for what a customer reads: the WhatsApp/email message, and the invoice, quote and receipt
pages and PDFs. The document names (Invoice, Quote, Receipt) stay in English on purpose: they
are the words people and ZRA use. Every Bemba and Nyanja string here should be checked by a
native speaker; missing ones fall back to English.

Placeholders use str.format: "{name}".
"""

from __future__ import annotations

from django.db import models


class Language(models.TextChoices):
    ENGLISH = "en", "English"
    BEMBA = "bem", "Icibemba (Bemba)"
    NYANJA = "ny", "Chinyanja (Nyanja)"


# key: (English, Bemba, Nyanja)
STRINGS: dict[str, tuple[str, str, str]] = {
    # ---- messages (click-to-chat and email intro) ---------------------------------------------
    "hello_name": ("Hello {name},", "Mwapoleni {name},", "Muli bwanji {name},"),
    "hello": ("Hello,", "Mwapoleni,", "Muli bwanji,"),
    "msg_invoice": (
        "{greeting} here is invoice {number} from {business} for {amount}, due {due}.\n\n"
        "View and download it here: {url}",
        "{greeting} iyi e invoice {number} ukufuma ku {business} iya {amount}, iya kulipila "
        "pa {due}.\n\nIlolesheni no kuikopa apa: {url}",
        "{greeting} iyi ndi invoice {number} yochokera ku {business} ya {amount}, yolipira "
        "pa {due}.\n\nOnani ndi kuitsitsa apa: {url}",
    ),
    "msg_reminder": (
        "{greeting} this is a friendly reminder from {business} that invoice {number} has "
        "{amount} outstanding. It was due on {due}.\n\nView and download it here: {url}",
        "{greeting} ici cibukisho ukufuma ku {business}: pa invoice {number} pashala {amount} "
        "ishilalipilwa. Yali iya kulipila pa {due}.\n\nIlolesheni apa: {url}",
        "{greeting} ichi ndi chikumbutso chochokera ku {business}: pa invoice {number} patsala "
        "{amount} zosalipiridwa. Inali yolipira pa {due}.\n\nOnani apa: {url}",
    ),
    "msg_quote": (
        "{greeting} here is quote {number} from {business} for {amount}, valid until {until}."
        "\n\nView it and accept or decline here: {url}",
        "{greeting} uyu e mutengo (quote) {number} ukufuma ku {business} wa {amount}, uwa "
        "kubomfya mpaka {until}.\n\nIlolesheni, no kusumina nangu ukukaana apa: {url}",
        "{greeting} uwu ndi mtengo (quote) {number} wochokera ku {business} wa {amount}, "
        "wovomerezeka mpaka {until}.\n\nOnani, ndipo vomerani kapena kanani apa: {url}",
    ),
    "msg_receipt": (
        "Thank you{comma_name}. Receipt {receipt} for {amount} against invoice {number}: {url}",
        "Natotela{comma_name}. Risiti {receipt} iya {amount} pa invoice {number}: {url}",
        "Zikomo{comma_name}. Lisiti {receipt} ya {amount} pa invoice {number}: {url}",
    ),
    # ---- document labels ------------------------------------------------------------------------
    "from": ("From", "Ukufuma", "Kuchokera"),
    "bill_to": ("Bill to", "Kuli", "Kwa"),
    "for": ("For", "Kuli", "Kwa"),
    "issued": ("Issued", "Yalembwa", "Yalembedwa"),
    "date": ("Date", "Ubushiku", "Tsiku"),
    "due": ("Due", "Ukulipila pa", "Kulipira pa"),
    "valid_until": ("Valid until", "Ilebomba mpaka", "Ikugwira ntchito mpaka"),
    "item": ("Item", "Icintu", "Chinthu"),
    "qty": ("Qty", "Ubwingi", "Kuchuluka"),
    "price": ("Price", "Umutengo", "Mtengo"),
    "amount": ("Amount", "Indalama", "Ndalama"),
    "subtotal": ("Subtotal", "Pamo", "Pamodzi"),
    "discount": ("Discount", "Ukucefyako", "Kuchotsera"),
    "total": ("Total", "Fyonse", "Zonse"),
    "paid": ("Paid", "Ifyalipilwa", "Zolipiridwa"),
    "balance_due": ("Balance due", "Ifyashala ukulipila", "Zotsala kulipira"),
    "balance": ("Balance", "Ifyashala", "Zotsala"),
    "balance_still_due": ("Balance still due", "Ifyashala ukulipila", "Zotsala kulipira"),
    "notes": ("Notes", "Ifyalembwa", "Zolemba"),
    "receipts": ("Receipts", "Ama risiti", "Malisiti"),
    "how_to_pay": ("How to pay", "Ifya kulipilamo", "Momwe mungalipirire"),
    "use_reference": (
        "Please use {ref} as the reference.",
        "Napapata lembeni {ref} pa ca kwishibilako (reference).",
        "Chonde lembani {ref} ngati chizindikiro (reference).",
    ),
    "download_pdf": ("Download PDF", "Kopeni PDF", "Tsitsani PDF"),
    "kwacha_total": (
        "Total in Kwacha at K{rate} = 1 {currency}",
        "Fyonse mu Kwacha pa K{rate} = 1 {currency}",
        "Zonse mu Kwacha pa K{rate} = 1 {currency}",
    ),
    # pay now
    "pay_now": ("Pay {amount} now", "Lipileni {amount} nomba", "Lipirani {amount} tsopano"),
    "pay_blurb": (
        "Mobile money or card, paid straight to {business} through Lenco.",
        "Ukulipila na mobile money nangu kadi, ifilaya fye ku {business} ukupitila mu Lenco.",
        "Kulipira ndi mobile money kapena khadi, zikupita molunjika ku {business} kudzera "
        "mu Lenco.",
    ),
    "mobile_number": ("Mobile money number", "Inambala ya mobile money", "Nambala ya mobile money"),
    "pay_mobile": (
        "Pay with mobile money",
        "Lipileni na mobile money",
        "Lipirani ndi mobile money",
    ),
    "or": ("or", "nangu", "kapena"),
    "receipt_email": (
        "Email for your receipt",
        "Email iya kupokelelapo risiti",
        "Email yolandirira lisiti",
    ),
    "pay_card": ("Pay by card", "Lipileni na kadi", "Lipirani ndi khadi"),
    # receipt
    "received_from": ("Received from", "Ukufuma kuli", "Kuchokera kwa"),
    "for_invoice": ("For invoice", "Pa invoice", "Pa invoice"),
    "amount_received": ("Amount received", "Indalama ishapokelelwa", "Ndalama zolandiridwa"),
    "paid_by": ("Paid by", "Yalipilwa na", "Yalipiridwa ndi"),
    "reference": ("Reference", "Reference", "Reference"),
    "invoice_total": ("Invoice total", "Fyonse pa invoice", "Zonse pa invoice"),
    # quote
    "decline": ("Decline", "Kaana", "Kanani"),
    "accept_quote": ("Accept quote", "Sumina umutengo", "Vomerani mtengo"),
    "quote_accepted": (
        "Accepted. {business} will be in touch.",
        "Mwasumina. {business} bali no kumutumina.",
        "Mwavomera. {business} adzakulankhulani.",
    ),
    "quote_declined": (
        "You declined this quote.",
        "Mwakaana uyu mutengo.",
        "Mwakana mtengo uwu.",
    ),
    "quote_closed": (
        "This quote can no longer be accepted or declined.",
        "Uyu mutengo tamuchili ukusumina nangu ukukaana.",
        "Mtengo uwu sungavomerezedwenso kapena kukanidwa.",
    ),
    "quote_expired": (
        "This quote expired on {date}. Contact {business} for a new one.",
        "Uyu mutengo wapwile pa {date}. Ebeni {business} bamupeele umbi.",
        "Mtengo uwu unatha pa {date}. Lankhulani ndi {business} kuti akupatseni wina.",
    ),
    # statuses customers can see
    "status_draft": ("Draft", "Tacilatumwa", "Sinatumizidwe"),
    "status_sent": ("Sent", "Catumwa", "Yatumizidwa"),
    "status_unpaid": ("Unpaid", "Tacilalipilwa", "Sinalipiridwe"),
    "status_viewed": ("Viewed", "Calolwa", "Yawonedwa"),
    "status_partial": ("Partly paid", "Calipilwako panono", "Yalipiridwa pang'ono"),
    "status_paid": ("Paid", "Calipilwa", "Yalipiridwa"),
    "status_overdue": ("Overdue", "Cacelwa", "Yachedwa"),
    "status_void": ("Void", "Cafumishiwapo", "Yathetsedwa"),
    "status_accepted": ("Accepted", "Casuminwa", "Yavomerezedwa"),
    "status_declined": ("Declined", "Cakaanwa", "Yakanidwa"),
    "status_expired": ("Expired", "Capwa", "Yatha"),
    "status_converted": ("Invoiced", "Capangwa invoice", "Yapangidwa invoice"),
    "status_open": ("Open", "Cicili", "Ikadalipo"),
}

_INDEX = {Language.ENGLISH: 0, Language.BEMBA: 1, Language.NYANJA: 2}


def t(lang: str | None, key: str, **kwargs: object) -> str:
    """The string for `key` in `lang` (English if unknown or missing), formatted with kwargs."""
    row = STRINGS[key]
    text = row[_INDEX.get(lang or "en", 0)] or row[0]  # type: ignore[call-overload]
    return text.format(**kwargs) if kwargs else text


def status_label(lang: str | None, status: str, english: str) -> str:
    key = f"status_{status}"
    return t(lang, key) if key in STRINGS else english

import { PlugZap } from "lucide-react";
import { useState } from "react";

import {
  useSaveZraDevice,
  useTestZraDevice,
  useZraDevice,
  VAT_CATEGORIES,
  type ZraDevice,
} from "@/api/resources";
import { FormField } from "@/components/form-field";
import { ErrorNote } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { errorText } from "@/lib/send";

const PAYMENT_TYPES = [
  ["02", "Credit (paid later)"],
  ["01", "Cash"],
  ["06", "Mobile money"],
  ["08", "Bank transfer"],
  ["05", "Card"],
  ["03", "Cash/credit"],
  ["04", "Bank cheque"],
  ["07", "Other"],
] as const;

/** ZRA Smart Invoice: report sent invoices to the business's VSDC so they become tax invoices. */
export function ZraCard({ canEdit }: { canEdit: boolean }) {
  const { data: device } = useZraDevice();
  if (!device) return null;
  return <ZraForm device={device} canEdit={canEdit} />;
}

function ZraForm({ device, canEdit }: { device: ZraDevice; canEdit: boolean }) {
  const save = useSaveZraDevice();
  const test = useTestZraDevice();
  const [v, setV] = useState({
    enabled: device.enabled ?? false,
    vsdc_url: device.vsdc_url ?? "",
    branch_id: device.branch_id ?? "000",
    device_serial: device.device_serial ?? "",
    item_class_code: device.item_class_code ?? "",
    item_type: device.item_type ?? "3",
    default_vat_category: device.default_vat_category ?? "A",
    payment_type: device.payment_type ?? "02",
  });
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const set = <K extends keyof typeof v>(key: K, value: (typeof v)[K]) =>
    setV((old) => ({ ...old, [key]: value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);
    try {
      await save.mutateAsync({
        ...v,
        vsdc_url: v.vsdc_url.trim(),
        branch_id: v.branch_id.trim(),
        device_serial: v.device_serial.trim(),
        item_class_code: v.item_class_code.trim(),
      });
      setStatus({ ok: true, text: "Saved." });
    } catch (err) {
      setStatus({ ok: false, text: errorText(err, "Couldn't save.") });
    }
  };

  const runTest = async () => {
    setStatus(null);
    try {
      const r = await test.mutateAsync();
      setStatus({ ok: r.ok, text: r.message });
    } catch (err) {
      setStatus({ ok: false, text: errorText(err, "Couldn't reach the VSDC.") });
    }
  };

  return (
    <Card>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4" noValidate>
          <fieldset disabled={!canEdit} className="grid min-w-0 grid-cols-1 gap-4">
            <legend className="mb-1 font-semibold">ZRA Smart Invoice</legend>
            <p className="text-muted-foreground -mt-2 text-sm">
              For VAT-registered businesses. Each invoice you send is reported to your ZRA VSDC and
              becomes a <strong>Tax Invoice</strong> with ZRA's receipt number, signature and QR
              code. Voiding it sends ZRA a credit note.
            </p>
            {!device.vat_registered && (
              <p className="bg-muted rounded-md p-3 text-sm">
                Tick <strong>We are VAT-registered</strong> in your business details above before
                you switch this on. You can fill in the details below now.
              </p>
            )}
            <p className="text-sm">
              <span className="text-muted-foreground">TPIN: </span>
              {device.tpin || "add it in your business details above"}
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary size-4"
                checked={v.enabled}
                onChange={(e) => set("enabled", e.target.checked)}
              />
              Report my invoices to ZRA
            </label>
            <FormField
              id="z-url"
              label="VSDC address"
              hint="Where your VSDC runs, e.g. http://10.0.0.5:8080/zrasandboxvsdc"
            >
              <Input
                id="z-url"
                type="url"
                autoComplete="off"
                value={v.vsdc_url}
                onChange={(e) => set("vsdc_url", e.target.value)}
              />
            </FormField>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField id="z-branch" label="Branch ID" hint="3 digits. 000 is the head office.">
                <Input
                  id="z-branch"
                  inputMode="numeric"
                  maxLength={3}
                  value={v.branch_id}
                  onChange={(e) => set("branch_id", e.target.value)}
                />
              </FormField>
              <FormField id="z-serial" label="Device serial" hint="From the Smart Invoice portal.">
                <Input
                  id="z-serial"
                  autoComplete="off"
                  value={v.device_serial}
                  onChange={(e) => set("device_serial", e.target.value)}
                />
              </FormField>
              <FormField
                id="z-class"
                label="Item class code"
                hint="ZRA's code for what you sell, e.g. 50102518."
              >
                <Input
                  id="z-class"
                  inputMode="numeric"
                  autoComplete="off"
                  value={v.item_class_code}
                  onChange={(e) => set("item_class_code", e.target.value)}
                />
              </FormField>
              <FormField id="z-type" label="What you sell">
                <Select
                  id="z-type"
                  value={v.item_type}
                  onChange={(e) => set("item_type", e.target.value as typeof v.item_type)}
                >
                  <option value="3">Services</option>
                  <option value="2">Goods</option>
                </Select>
              </FormField>
              <FormField id="z-vat" label="Usual VAT category" hint="Items can override it.">
                <Select
                  id="z-vat"
                  value={v.default_vat_category}
                  onChange={(e) =>
                    set("default_vat_category", e.target.value as typeof v.default_vat_category)
                  }
                >
                  {VAT_CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField id="z-pay" label="Payment type on invoices">
                <Select
                  id="z-pay"
                  value={v.payment_type}
                  onChange={(e) => set("payment_type", e.target.value as typeof v.payment_type)}
                >
                  {PAYMENT_TYPES.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>
            {device.sdc_id && (
              <p className="text-muted-foreground text-xs [overflow-wrap:anywhere]">
                Connected device: SDC ID {device.sdc_id}
                {device.mrc_no ? `, MRC ${device.mrc_no}` : ""}
              </p>
            )}
          </fieldset>
          {status &&
            (status.ok ? (
              <p className="text-sm text-emerald-700 dark:text-emerald-400">{status.text}</p>
            ) : (
              <ErrorNote>{status.text}</ErrorNote>
            ))}
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save ZRA settings"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={runTest}
                disabled={test.isPending || !device.device_serial}
              >
                <PlugZap /> Test ZRA connection
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

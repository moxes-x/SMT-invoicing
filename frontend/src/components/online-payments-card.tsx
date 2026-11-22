import { Check, Copy, PlugZap } from "lucide-react";
import { useState } from "react";

import {
  useOnlinePayments,
  useSaveOnlinePayments,
  useTestOnlinePayments,
  type LencoAccount,
} from "@/api/resources";
import { FormField } from "@/components/form-field";
import { ErrorNote } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { errorText } from "@/lib/send";

/** Connect the business's own Lenco account so customers can tap Pay now on invoices. */
export function OnlinePaymentsCard({ canEdit }: { canEdit: boolean }) {
  const { data: account } = useOnlinePayments();
  if (!account) return null;
  return <OnlinePaymentsForm account={account} canEdit={canEdit} />;
}

function OnlinePaymentsForm({ account, canEdit }: { account: LencoAccount; canEdit: boolean }) {
  const save = useSaveOnlinePayments();
  const test = useTestOnlinePayments();
  const [enabled, setEnabled] = useState(account.enabled ?? false);
  const [environment, setEnvironment] = useState(account.environment ?? "sandbox");
  const [publicKey, setPublicKey] = useState(account.public_key ?? "");
  const [secretKey, setSecretKey] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);
    try {
      await save.mutateAsync({
        enabled,
        environment,
        public_key: publicKey.trim(),
        ...(secretKey.trim() ? { secret_key: secretKey.trim() } : {}),
      });
      setSecretKey("");
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
      setStatus({ ok: false, text: errorText(err, "Couldn't reach Lenco.") });
    }
  };

  const copy = async () => {
    await navigator.clipboard?.writeText(account.webhook_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardContent>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4" noValidate>
          <fieldset disabled={!canEdit} className="grid min-w-0 grid-cols-1 gap-4">
            <legend className="mb-1 font-semibold">Online payments (Lenco)</legend>
            <p className="text-muted-foreground -mt-2 text-sm">
              Customers tap <strong>Pay now</strong> on your invoice link and pay by MTN, Airtel,
              Zamtel or card. The money goes straight to your own{" "}
              <a
                className="text-primary underline"
                href="https://lenco.co/zm"
                target="_blank"
                rel="noreferrer"
              >
                Lenco
              </a>{" "}
              account, and the invoice is marked paid by itself.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary size-4"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Show Pay now on my invoices
            </label>
            <FormField id="l-env" label="Mode">
              <Select
                id="l-env"
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as typeof environment)}
              >
                <option value="sandbox">Sandbox (test money only)</option>
                <option value="live">Live</option>
              </Select>
            </FormField>
            <FormField id="l-pub" label="Public key">
              <Input
                id="l-pub"
                autoComplete="off"
                value={publicKey}
                onChange={(e) => setPublicKey(e.target.value)}
              />
            </FormField>
            <FormField
              id="l-secret"
              label="Secret key"
              hint={
                account.has_secret_key
                  ? `Saved (${account.secret_key_hint || "hidden"}). Leave empty to keep it.`
                  : "Stored encrypted. Never shown again after saving."
              }
            >
              <Input
                id="l-secret"
                type="password"
                autoComplete="new-password"
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
              />
            </FormField>
            <div className="grid grid-cols-1 gap-1 text-sm">
              <span className="font-medium">Webhook URL</span>
              <span className="text-muted-foreground text-xs">
                Paste this in Lenco's dashboard under Lenco Pay → Webhooks so payments show up
                instantly.
              </span>
              <div className="flex items-center gap-2">
                <code className="bg-muted min-w-0 flex-1 truncate rounded px-2 py-1.5 text-xs">
                  {account.webhook_url}
                </code>
                <Button type="button" variant="outline" size="sm" onClick={copy}>
                  {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
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
                {save.isPending ? "Saving…" : "Save online payments"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={runTest}
                disabled={test.isPending || !account.has_secret_key}
              >
                <PlugZap /> Test connection
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

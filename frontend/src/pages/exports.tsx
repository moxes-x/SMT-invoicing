import { Download } from "lucide-react";
import { useState } from "react";

import { qs } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { todayISO } from "@/lib/dates";

export function ExportsPage() {
  const today = todayISO();
  const [start, setStart] = useState(`${today.slice(0, 8)}01`);
  const [end, setEnd] = useState(today);
  return (
    <div className="grid gap-4">
      <PageHeader
        title="Export"
        description="Spreadsheet (CSV) files for your accountant or your own records. Amounts are in each invoice's currency, e.g. 1250.00, with a currency column."
      />
      <Card>
        <CardHeader>
          <CardTitle>Payments received</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <FormField id="x-start" label="From">
              <Input
                id="x-start"
                type="date"
                value={start}
                max={end}
                onChange={(e) => setStart(e.target.value)}
              />
            </FormField>
            <FormField id="x-end" label="To">
              <Input
                id="x-end"
                type="date"
                value={end}
                min={start}
                onChange={(e) => setEnd(e.target.value)}
              />
            </FormField>
          </div>
          <Button asChild>
            <a href={`/api/payments/export/${qs({ start, end })}`}>
              <Download /> Download payments CSV
            </a>
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          <p className="text-muted-foreground text-sm">
            Every invoice with its total, paid and balance. To export just some, filter the Invoices
            list and use Export there.
          </p>
          <Button asChild variant="outline">
            <a href="/api/invoices/export/">
              <Download /> Download all invoices CSV
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

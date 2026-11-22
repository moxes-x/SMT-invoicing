import { zodResolver } from "@hookform/resolvers/zod";
import { Package, Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useDeleteItem, useItems, useSaveItem, type Item } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { MoneyInput } from "@/components/money-input";
import { EmptyState, ErrorNote, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { applyApiErrors } from "@/lib/apply-errors";
import { formatMoney, parseMoney, toMoneyInput } from "@/lib/money";

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name.").max(200),
  description: z.string().optional(),
  price: z.string().refine((v) => parseMoney(v) !== null, "Enter a price like 150.00"),
  is_active: z.boolean(),
});
type Values = z.infer<typeof schema>;

function ItemForm({ item, onDone }: { item?: Item; onDone: () => void }) {
  const save = useSaveItem();
  const remove = useDeleteItem();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: item?.name ?? "",
      description: item?.description ?? "",
      price: item ? toMoneyInput(item.unit_price) : "",
      is_active: item?.is_active ?? true,
    },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ price, ...values }) => {
    setFormError(null);
    try {
      await save.mutateAsync({ ...values, unit_price: parseMoney(price)!, id: item?.id });
      onDone();
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, ["name", "description"]));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField id="i-name" label="Name" error={errors.name?.message}>
        <Input id="i-name" aria-invalid={!!errors.name} {...form.register("name")} />
      </FormField>
      <FormField id="i-price" label="Price" error={errors.price?.message}>
        <MoneyInput id="i-price" aria-invalid={!!errors.price} {...form.register("price")} />
      </FormField>
      <FormField id="i-desc" label="Description (optional)">
        <Input id="i-desc" {...form.register("description")} />
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="accent-primary size-4" {...form.register("is_active")} />
        Show when creating invoices
      </label>
      {formError && <ErrorNote>{formError}</ErrorNote>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {item ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive"
            onClick={async () => {
              if (!window.confirm(`Delete ${item.name}?`)) return;
              await remove.mutateAsync(item.id);
              onDone();
            }}
          >
            Delete
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : item ? "Save changes" : "Add item"}
        </Button>
      </div>
    </form>
  );
}

export function ItemsPage() {
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const { data, isLoading } = useItems();

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Items"
        description="Products and services you sell often. They fill in invoice lines for you."
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add
          </Button>
        }
      />
      {!isLoading && !data?.results.length ? (
        <EmptyState icon={<Package />} title="No saved items yet">
          <Button onClick={() => setEditing("new")}>Add an item</Button>
        </EmptyState>
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-y">
            {data?.results.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setEditing(item)}
                  className="hover:bg-muted/50 flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{item.name}</span>
                    {item.description && (
                      <span className="text-muted-foreground block truncate text-xs">
                        {item.description}
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-2">
                    {!item.is_active && <Badge>Hidden</Badge>}
                    <span className="font-semibold tabular-nums">
                      {formatMoney(item.unit_price)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Dialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New item" : "Edit item"}
      >
        {editing !== null && (
          <ItemForm
            key={editing === "new" ? "new" : editing.id}
            item={editing === "new" ? undefined : editing}
            onDone={() => setEditing(null)}
          />
        )}
      </Dialog>
    </div>
  );
}

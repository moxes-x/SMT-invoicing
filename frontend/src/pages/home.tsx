import { useQuery } from "@tanstack/react-query";
import { CircleCheck, LogOut, ReceiptText } from "lucide-react";
import { useNavigate } from "react-router";

import { useLogout, useMe } from "@/api/auth";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function HomePage() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<{ status: string }>("/health/"),
  });
  const business = me?.current_business;

  return (
    <div className="bg-muted/40 min-h-svh">
      <header className="bg-background/90 sticky top-0 z-10 border-b backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <div className="flex items-center gap-2 font-semibold">
            <ReceiptText className="text-primary size-5" />
            <span className="truncate">{business?.name ?? "Invoicing"}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              await logout.mutateAsync();
              navigate("/login");
            }}
          >
            <LogOut /> Log out
          </Button>
        </div>
      </header>
      <main className="mx-auto grid max-w-5xl gap-4 p-4">
        <Card>
          <CardHeader>
            <CardTitle>Hello{me?.user.full_name ? `, ${me.user.full_name}` : ""} 👋</CardTitle>
            <CardDescription>
              Your workspace for {business?.name} is ready. Customers and invoices arrive in the
              next release.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <CircleCheck
                className={health.data?.status === "ok" ? "text-primary size-4" : "size-4"}
              />
              API{" "}
              {health.isLoading
                ? "checking…"
                : health.data?.status === "ok"
                  ? "connected"
                  : "unreachable"}
            </p>
          </CardContent>
        </Card>
        {business?.compliance_notice && (
          <Card className="border-warning/60">
            <CardContent className="text-sm">{business.compliance_notice}</CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

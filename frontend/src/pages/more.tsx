import { ChevronRight, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { useLogout, useMe } from "@/api/auth";
import { MORE_NAV } from "@/components/nav";
import { PageHeader } from "@/components/page";
import { Card } from "@/components/ui/card";

export function MorePage() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <div className="grid gap-4">
      <PageHeader title="More" description={me?.current_business?.name} />
      <Card className="gap-0 py-0">
        <ul className="divide-y">
          {MORE_NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <Link to={to} className="hover:bg-muted/50 flex items-center gap-3 px-4 py-3.5">
                <Icon className="text-muted-foreground size-5" />
                <span className="flex-1 font-medium">{label}</span>
                <ChevronRight className="text-muted-foreground size-4" />
              </Link>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={async () => {
                await logout.mutateAsync();
                navigate("/login");
              }}
              className="hover:bg-muted/50 text-destructive flex w-full items-center gap-3 px-4 py-3.5 text-left"
            >
              <LogOut className="size-5" />
              <span className="font-medium">Log out</span>
            </button>
          </li>
        </ul>
      </Card>
      {me?.user && (
        <p className="text-muted-foreground text-center text-xs">Signed in as {me.user.email}</p>
      )}
    </div>
  );
}

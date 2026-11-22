import { LogOut, Menu } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { useLogout, useMe } from "@/api/auth";
import { MAIN_NAV, MORE_NAV, NAV } from "@/components/nav";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function AppLayout() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const inMore = pathname === "/more" || MORE_NAV.some((n) => pathname.startsWith(n.to));
  const signOut = async () => {
    await logout.mutateAsync();
    navigate("/login");
  };

  return (
    <div className="bg-muted/40 min-h-svh pb-20 md:pb-0 md:pl-56">
      {/* Desktop sidebar */}
      <aside className="bg-background fixed inset-y-0 left-0 hidden w-56 flex-col border-r p-3 md:flex">
        <div className="mb-4 truncate px-3 py-2 font-semibold">{me?.current_business?.name}</div>
        <nav className="grid gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  isActive && "bg-accent text-accent-foreground",
                )
              }
            >
              <Icon className="size-4" /> {label}
            </NavLink>
          ))}
        </nav>
        <Button variant="ghost" className="mt-auto justify-start" onClick={signOut}>
          <LogOut /> Log out
        </Button>
      </aside>

      {/* Mobile top bar (log out lives under More) */}
      <header className="bg-background/90 sticky top-0 z-10 flex h-14 items-center gap-2 border-b px-4 backdrop-blur md:hidden">
        <span className="truncate font-semibold">{me?.current_business?.name}</span>
      </header>

      <main className="mx-auto max-w-4xl p-4 md:p-8">
        <Outlet />
      </main>

      {/* Mobile bottom nav: thumb-reachable */}
      <nav className="bg-background fixed inset-x-0 bottom-0 z-10 grid grid-cols-5 border-t pb-[env(safe-area-inset-bottom)] md:hidden">
        {MAIN_NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "text-muted-foreground flex flex-col items-center gap-1 py-2 text-[11px] font-medium",
                isActive && "text-primary",
              )
            }
          >
            <Icon className="size-5" />
            {label}
          </NavLink>
        ))}
        <NavLink
          to="/more"
          className={cn(
            "text-muted-foreground flex flex-col items-center gap-1 py-2 text-[11px] font-medium",
            inMore && "text-primary",
          )}
        >
          <Menu className="size-5" />
          More
        </NavLink>
      </nav>
    </div>
  );
}

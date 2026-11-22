import { ChevronRight, Download, Languages, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { useLogout, useMe } from "@/api/auth";
import { MORE_NAV } from "@/components/nav";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LANGUAGES, useLang, useSetLanguage, useT } from "@/i18n";
import { useInstallPrompt } from "@/lib/install";

export function MorePage() {
  const { data: me } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const install = useInstallPrompt();
  const t = useT();
  return (
    <div className="grid gap-4">
      <PageHeader title={t("nav.more")} description={me?.current_business?.name} />
      <Card className="gap-0 py-0">
        <ul className="divide-y">
          {MORE_NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <Link to={to} className="hover:bg-muted/50 flex items-center gap-3 px-4 py-3.5">
                <Icon className="text-muted-foreground size-5" />
                <span className="flex-1 font-medium">{t(label)}</span>
                <ChevronRight className="text-muted-foreground size-4" />
              </Link>
            </li>
          ))}
          {install && (
            <li>
              <button
                type="button"
                onClick={install}
                className="hover:bg-muted/50 flex w-full items-center gap-3 px-4 py-3.5 text-left"
              >
                <Download className="text-muted-foreground size-5" />
                <span className="flex-1 font-medium">{t("action.install")}</span>
              </button>
            </li>
          )}
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
              <span className="font-medium">{t("action.logout")}</span>
            </button>
          </li>
        </ul>
      </Card>
      <LanguagePicker />
      {me?.user && (
        <p className="text-muted-foreground text-center text-xs">
          {t("more.signedInAs", { email: me.user.email })}
        </p>
      )}
    </div>
  );
}

function LanguagePicker() {
  const lang = useLang();
  const set = useSetLanguage();
  const t = useT();
  return (
    <Card className="gap-3 px-4 py-4">
      <div className="flex items-center gap-3">
        <Languages className="text-muted-foreground size-5" />
        <h2 className="font-medium">{t("lang.title")}</h2>
      </div>
      <div className="grid grid-cols-3 gap-2" role="group" aria-label={t("lang.title")}>
        {LANGUAGES.map((l) => (
          <Button
            key={l.value}
            variant={lang === l.value ? "default" : "outline"}
            aria-pressed={lang === l.value}
            disabled={set.isPending}
            onClick={() => set.mutate(l.value)}
          >
            {l.label}
          </Button>
        ))}
      </div>
      <p className="text-muted-foreground text-xs">{t("lang.hint")}</p>
    </Card>
  );
}

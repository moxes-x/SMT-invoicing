import { Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useLogout, useMe } from "@/api/auth";
import { roleLabel, useAcceptInvite, useInviteInfo } from "@/api/team";
import { AuthLayout } from "@/components/auth-layout";
import { ErrorNote } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorText } from "@/lib/send";

/** Where an emailed invite lands. Works logged out: sign up or log in, then come back here. */
export function JoinPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { data: me, isLoading: meLoading } = useMe();
  const { data: invite, isLoading, isError } = useInviteInfo(token);
  const accept = useAcceptInvite(token);
  const logout = useLogout();
  const [error, setError] = useState<string | null>(null);

  if (isLoading || meLoading) {
    return (
      <AuthLayout>
        <p className="text-muted-foreground text-center text-sm">Loading…</p>
      </AuthLayout>
    );
  }

  if (isError || !invite) {
    return (
      <AuthLayout>
        <Card>
          <CardHeader>
            <CardTitle>This invite link isn't valid</CardTitle>
            <CardDescription>Check the link, or ask for a new invite.</CardDescription>
          </CardHeader>
        </Card>
      </AuthLayout>
    );
  }

  const here = `/join/${token}`;
  const qs = `?next=${encodeURIComponent(here)}&email=${encodeURIComponent(invite.email)}`;
  const wrongUser = !!me && me.user.email.toLowerCase() !== invite.email.toLowerCase();

  const join = async () => {
    setError(null);
    try {
      await accept.mutateAsync();
      navigate("/");
    } catch (err) {
      setError(errorText(err, "Couldn't join. Please try again."));
    }
  };

  return (
    <AuthLayout>
      <Card>
        <CardHeader>
          <div className="bg-accent text-accent-foreground mb-2 flex size-10 items-center justify-center rounded-full">
            <Users className="size-5" />
          </div>
          <CardTitle>Join {invite.business}</CardTitle>
          <CardDescription className="[overflow-wrap:anywhere]">
            {invite.invited_by || "Someone"} invited {invite.email} as{" "}
            {roleLabel(invite.role).toLowerCase()}.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {!invite.is_open ? (
            <ErrorNote>This invite has expired or was already used. Ask for a new one.</ErrorNote>
          ) : !me ? (
            <>
              <Button asChild>
                <Link to={`/signup${qs}`}>Create an account</Link>
              </Button>
              <Button asChild variant="outline">
                <Link to={`/login${qs}`}>I already have an account</Link>
              </Button>
            </>
          ) : wrongUser ? (
            <>
              <ErrorNote>
                You're logged in as {me.user.email}. This invite is for {invite.email}.
              </ErrorNote>
              <Button variant="outline" onClick={() => logout.mutate()}>
                Log out and switch account
              </Button>
            </>
          ) : (
            <Button onClick={join} disabled={accept.isPending}>
              {accept.isPending ? "Joining…" : `Join ${invite.business}`}
            </Button>
          )}
          {error && <ErrorNote>{error}</ErrorNote>}
        </CardContent>
      </Card>
    </AuthLayout>
  );
}

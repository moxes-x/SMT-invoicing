import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Copy, Mail, MessageCircle, UserPlus, X } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { useAccess, useMe, type Role } from "@/api/auth";
import {
  ROLES,
  roleLabel,
  useChangeRole,
  useInvite,
  useRemoveMember,
  useRevokeInvite,
  useTeam,
  type TeamInvite,
  type TeamMember,
} from "@/api/team";
import { Section } from "@/components/document-parts";
import { FormField } from "@/components/form-field";
import { ErrorNote, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { applyApiErrors } from "@/lib/apply-errors";
import { formatDate } from "@/lib/dates";
import { errorText } from "@/lib/send";

const schema = z.object({
  email: z.email("Enter a valid email address."),
  role: z.enum(["owner", "admin", "staff", "accountant"]),
});
type Values = z.infer<typeof schema>;

export function TeamPage() {
  const { data: team, isLoading } = useTeam();
  const { role: myRole, canManage } = useAccess();
  const assignable = ROLES.filter((r) => r.value !== "owner" || myRole === "owner");

  return (
    <div className="grid grid-cols-1 gap-4">
      <PageHeader title="Team" description="Who can use this business, and what they can do." />
      {canManage && <InviteForm roles={assignable} />}
      <Section title="People">
        {isLoading || !team ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : (
          <ul className="divide-y">
            {team.members.map((m) => (
              <MemberRow
                key={m.id}
                member={m}
                canEdit={canManage && !m.is_you && (m.role !== "owner" || myRole === "owner")}
                roles={assignable}
              />
            ))}
          </ul>
        )}
      </Section>
      {team && team.invites.length > 0 && (
        <Section title="Invited">
          <ul className="divide-y">
            {team.invites.map((i) => (
              <InviteRow key={i.id} invite={i} canRevoke={canManage} />
            ))}
          </ul>
        </Section>
      )}
      <Section title="What each role can do">
        <dl className="grid gap-2 text-sm">
          {ROLES.map((r) => (
            <div key={r.value} className="grid grid-cols-[6.5rem_1fr] gap-2">
              <dt className="font-medium">{r.label}</dt>
              <dd className="text-muted-foreground">{r.help}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  );
}

function InviteForm({ roles }: { roles: typeof ROLES }) {
  const invite = useInvite();
  const [formError, setFormError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: "staff" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (v) => {
    setFormError(null);
    setSentTo(null);
    try {
      await invite.mutateAsync(v);
      setSentTo(v.email);
      form.reset({ email: "", role: v.role });
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, ["email", "role"]));
    }
  });

  return (
    <Section title="Invite someone">
      <form
        onSubmit={onSubmit}
        className="grid gap-3 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
        noValidate
      >
        <FormField id="inv-email" label="Their email" error={errors.email?.message}>
          <Input
            id="inv-email"
            type="email"
            autoComplete="off"
            aria-invalid={!!errors.email}
            {...form.register("email")}
          />
        </FormField>
        <FormField id="inv-role" label="Role" error={errors.role?.message}>
          <Select id="inv-role" {...form.register("role")}>
            {roles.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        </FormField>
        <Button type="submit" disabled={isSubmitting}>
          <UserPlus /> {isSubmitting ? "Sending…" : "Send invite"}
        </Button>
      </form>
      {sentTo && (
        <p role="status" className="text-muted-foreground mt-3 text-sm [overflow-wrap:anywhere]">
          Invite emailed to {sentTo}. You can also share the link on WhatsApp below. It works for 7
          days.
        </p>
      )}
      {formError && (
        <div className="mt-3">
          <ErrorNote>{formError}</ErrorNote>
        </div>
      )}
    </Section>
  );
}

function MemberRow({
  member,
  canEdit,
  roles,
}: {
  member: TeamMember;
  canEdit: boolean;
  roles: typeof ROLES;
}) {
  const change = useChangeRole();
  const remove = useRemoveMember();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const name = member.full_name || member.email;

  const leaveOrRemove = async () => {
    const q = member.is_you
      ? "Leave this business? You'll lose access to it."
      : `Remove ${name} from the team?`;
    if (!window.confirm(q)) return;
    setError(null);
    try {
      await remove.mutateAsync({ id: member.id, self: member.is_you });
      if (member.is_you) navigate("/");
    } catch (err) {
      setError(errorText(err, "Couldn't do that."));
    }
  };

  return (
    <li className="grid gap-2 py-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block truncate font-medium">
            {name} {member.is_you && <span className="text-muted-foreground">(you)</span>}
          </span>
          {member.full_name && (
            <span className="text-muted-foreground block truncate text-xs">{member.email}</span>
          )}
        </span>
        {canEdit ? (
          <Select
            aria-label={`Role for ${name}`}
            className="w-36 shrink-0"
            value={member.role}
            disabled={change.isPending}
            onChange={async (e) => {
              setError(null);
              try {
                await change.mutateAsync({ id: member.id, role: e.target.value as Role });
              } catch (err) {
                setError(errorText(err, "Couldn't change the role."));
              }
            }}
          >
            {roles.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        ) : (
          <Badge tone={member.role === "owner" ? "brand" : "neutral"}>
            {roleLabel(member.role)}
          </Badge>
        )}
      </div>
      {(canEdit || member.is_you) && (
        <div>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive -ml-3"
            onClick={leaveOrRemove}
            disabled={remove.isPending}
          >
            {member.is_you ? "Leave business" : "Remove"}
          </Button>
        </div>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
    </li>
  );
}

function InviteRow({ invite, canRevoke }: { invite: TeamInvite; canRevoke: boolean }) {
  const revoke = useRevokeInvite();
  const { data: me } = useMe();
  const [copied, setCopied] = useState(false);
  const text =
    `${me?.user.full_name || "I"} invited you to ${me?.current_business?.name ?? "our business"} ` +
    `on Invoicing. Join with ${invite.email} here: ${invite.link}`;

  const copy = async () => {
    await navigator.clipboard?.writeText(invite.link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <li className="flex items-center justify-between gap-2 py-2 text-sm">
      <span className="flex min-w-0 items-start gap-2">
        <Mail className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <span className="min-w-0">
          <span className="block truncate font-medium">{invite.email}</span>
          <span className="text-muted-foreground text-xs">
            {roleLabel(invite.role)} · until {formatDate(invite.expires_at)}
          </span>
        </span>
      </span>
      <span className="flex shrink-0 items-center">
        <Button asChild variant="ghost" size="icon" aria-label={`Share invite on WhatsApp`}>
          <a
            href={`https://wa.me/?text=${encodeURIComponent(text)}`}
            target="_blank"
            rel="noreferrer"
          >
            <MessageCircle />
          </a>
        </Button>
        <Button variant="ghost" size="icon" aria-label="Copy invite link" onClick={copy}>
          {copied ? <Check /> : <Copy />}
        </Button>
        {canRevoke && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Cancel invite for ${invite.email}`}
            onClick={() => revoke.mutate(invite.id)}
            disabled={revoke.isPending}
          >
            <X />
          </Button>
        )}
      </span>
    </li>
  );
}

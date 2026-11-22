import {
  ChartColumn,
  Download,
  FileSignature,
  FileText,
  LayoutDashboard,
  Package,
  Repeat,
  Settings,
  Users,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import type { Key } from "@/i18n";

export interface NavItem {
  to: string;
  label: Key;
  icon: LucideIcon;
  end?: boolean;
}

export const MAIN_NAV: NavItem[] = [
  { to: "/", label: "nav.home", icon: LayoutDashboard, end: true },
  { to: "/invoices", label: "nav.invoices", icon: FileText },
  { to: "/quotes", label: "nav.quotes", icon: FileSignature },
  { to: "/customers", label: "nav.customers", icon: Users },
];

export const MORE_NAV: NavItem[] = [
  { to: "/recurring", label: "nav.recurring", icon: Repeat },
  { to: "/items", label: "nav.items", icon: Package },
  { to: "/reports", label: "nav.reports", icon: ChartColumn },
  { to: "/exports", label: "nav.exports", icon: Download },
  { to: "/team", label: "nav.team", icon: UsersRound },
  { to: "/settings", label: "nav.settings", icon: Settings },
];

export const NAV = [...MAIN_NAV, ...MORE_NAV];

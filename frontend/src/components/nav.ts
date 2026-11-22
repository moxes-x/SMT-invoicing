import {
  FileSignature,
  FileText,
  LayoutDashboard,
  Package,
  Repeat,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export const MAIN_NAV: NavItem[] = [
  { to: "/", label: "Home", icon: LayoutDashboard, end: true },
  { to: "/invoices", label: "Invoices", icon: FileText },
  { to: "/quotes", label: "Quotes", icon: FileSignature },
  { to: "/customers", label: "Customers", icon: Users },
];

export const MORE_NAV: NavItem[] = [
  { to: "/recurring", label: "Repeating invoices", icon: Repeat },
  { to: "/items", label: "Items & services", icon: Package },
  { to: "/settings", label: "Settings", icon: Settings },
];

export const NAV = [...MAIN_NAV, ...MORE_NAV];

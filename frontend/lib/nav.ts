import {
  Activity,
  Blocks,
  FileSearch,
  History,
  LayoutDashboard,
  ListTree,
  Settings,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** The eight sections of PROJECT_PLAN §6, in the order of the product spec. */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Blocks },
  { href: "/executions", label: "Executions", icon: Activity },
  { href: "/traces", label: "Traces", icon: ListTree },
  { href: "/anomalies", label: "Anomalies", icon: TriangleAlert },
  { href: "/investigations", label: "Investigations", icon: FileSearch },
  { href: "/replays", label: "Replays", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export const isActive = (href: string, pathname: string): boolean =>
  href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

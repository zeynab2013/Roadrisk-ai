import { History, Info, LayoutDashboard, MapPinned, ShieldAlert, type LucideIcon } from "lucide-react";

export type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
};

export const navItems: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/predict", label: "Prediction", icon: ShieldAlert },
  { to: "/history", label: "History", icon: History },
  { to: "/model", label: "Model", icon: Info },
  { to: "/areas", label: "Areas", icon: MapPinned },
];

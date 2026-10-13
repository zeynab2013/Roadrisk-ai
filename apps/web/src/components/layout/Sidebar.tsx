import { NavLink } from "react-router-dom";

import { BrandLogo } from "@/components/brand/BrandLogo";
import { navItems } from "@/components/layout/navigation";
import { cn } from "@/lib/utils";

type SidebarProps = {
  onNavigate?: () => void;
  id?: string;
};

export function Sidebar({ onNavigate, id = "app-navigation" }: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-white">
      <div className="border-b border-line px-5 py-4">
        <BrandLogo />
        <p className="mt-1 text-xs text-muted">Reported collision severity</p>
      </div>
      <nav id={id} aria-label="Primary" className="flex flex-1 flex-col gap-1 p-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy",
                  isActive ? "bg-navy text-white" : "text-navy hover:bg-canvas",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
      <p className="border-t border-line px-5 py-4 text-xs leading-5 text-muted">
        Scores come from the API. This dashboard does not calculate them.
      </p>
    </div>
  );
}

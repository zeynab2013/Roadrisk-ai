import { Menu, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { BrandLogo } from "@/components/brand/BrandLogo";
import { Sidebar } from "@/components/layout/Sidebar";
import { catalogue } from "@/content/status";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const location = useLocation();
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === location.pathname;
  const menuId = useId();

  function closeMenu() {
    setOpenPath(null);
  }

  useEffect(() => {
    if (!open) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenPath(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div className="min-h-screen bg-canvas text-navy">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:outline-2 focus:outline-offset-2 focus:outline-navy"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-white px-4 py-3 md:hidden">
        <BrandLogo className="w-28" />
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpenPath(open ? null : location.pathname)}
        >
          {open ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
          <span className="sr-only">{open ? "Close navigation" : "Open navigation"}</span>
        </button>
      </header>
      <div className="md:grid md:min-h-screen md:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="hidden border-r border-line md:sticky md:top-0 md:block md:h-screen">
          <Sidebar />
        </aside>
        {open ? (
          <div className="fixed inset-0 z-40 md:hidden">
            <button
              type="button"
              className="absolute inset-0 bg-navy-dark/40"
              aria-label="Close navigation"
              onClick={closeMenu}
            />
            <div className="relative h-full w-72 max-w-[85vw] border-r border-line">
              <Sidebar id={menuId} onNavigate={closeMenu} />
            </div>
          </div>
        ) : null}
        <div className="flex min-w-0 flex-col">
          <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6 lg:px-10">
            {children}
          </main>
          <footer className="border-t border-line px-4 py-4 text-xs leading-5 text-muted sm:px-6 lg:px-10">
            {catalogue.attribution}
          </footer>
        </div>
      </div>
    </div>
  );
}

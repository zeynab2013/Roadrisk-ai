import type { LucideIcon } from "lucide-react";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  body: string;
};

export function EmptyState({ icon: Icon, title, body }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white p-6">
      <Icon className="h-5 w-5 text-navy" aria-hidden="true" />
      <h3 className="mt-4 text-base font-medium">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted">{body}</p>
    </div>
  );
}

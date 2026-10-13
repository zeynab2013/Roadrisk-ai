import { Card } from "@/components/ui/card";

type StatusCardProps = {
  title: string;
  label: string;
  summary: string;
};

export function StatusCard({ title, label, summary }: StatusCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-sm font-medium text-muted">{title}</h2>
        <span className="rounded-full border border-line px-2.5 py-0.5 text-xs font-medium text-navy">
          {label}
        </span>
      </div>
      <p className="mt-4 text-sm leading-6 text-navy">{summary}</p>
    </Card>
  );
}

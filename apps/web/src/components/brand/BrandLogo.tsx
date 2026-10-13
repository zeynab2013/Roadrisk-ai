import { cn } from "@/lib/utils";

type BrandLogoProps = {
  className?: string;
};

/** Official lockup. The artwork is square and includes its own clear space. */
export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <img
      src="/brand/roadrisk-logo.png"
      alt="RoadRisk"
      width={1024}
      height={1024}
      className={cn("h-auto w-40 max-w-full", className)}
    />
  );
}

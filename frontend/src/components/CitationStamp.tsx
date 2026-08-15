export interface CitationStampProps {
  label: string;
  variant: "verified" | "unverified";
  href?: string;
}

export function CitationStamp({ label, variant, href }: CitationStampProps) {
  const colorClasses =
    variant === "verified" ? "border-verified text-verified" : "border-unverified text-unverified";
  const className = `inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] tracking-wide ${colorClasses}`;
  const content = variant === "verified" ? `[${label}]` : label;

  if (href) {
    return (
      <a className={className} href={href} target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }
  return <span className={className}>{content}</span>;
}

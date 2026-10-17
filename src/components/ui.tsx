import type { ReactNode } from 'react';

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

export const btnPrimary =
  'inline-flex items-center justify-center gap-2 rounded-full bg-terracotta px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-terracotta-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-terracotta/40 disabled:cursor-not-allowed disabled:opacity-50';

export const btnSecondary =
  'inline-flex items-center justify-center gap-2 rounded-full border border-sand-dark bg-white px-5 py-2.5 text-sm font-semibold text-ink transition hover:bg-sand focus:outline-none focus-visible:ring-2 focus-visible:ring-ink/10 disabled:opacity-50';

export const btnGhost =
  'inline-flex items-center justify-center gap-2 rounded-full px-3 py-2 text-sm font-medium text-ink-soft transition hover:bg-sand hover:text-ink disabled:opacity-50';

export const inputBase =
  'w-full rounded-xl border border-sand-dark bg-white px-3.5 py-2.5 text-base text-ink placeholder:text-ink-soft/60 shadow-sm outline-none transition focus:border-terracotta focus:ring-2 focus:ring-terracotta/20';

export const cardBase =
  'rounded-2xl border border-sand-dark/70 bg-white shadow-[0_1px_2px_rgba(36,28,21,0.04)]';

export const labelBase = 'block text-sm font-medium text-ink-soft';

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(cardBase, 'p-5', className)}>{children}</div>;
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'terracotta' | 'olive' | 'honey';
}) {
  const tones: Record<string, string> = {
    neutral: 'bg-sand text-ink-soft',
    terracotta: 'bg-terracotta/10 text-terracotta-dark',
    olive: 'bg-olive/10 text-olive-dark',
    honey: 'bg-honey/15 text-honey',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold',
        tones[tone]
      )}
    >
      {children}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-sand-dark bg-white/60 px-6 py-10 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      {description ? <p className="mx-auto mt-1 max-w-md text-sm text-ink-soft">{description}</p> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <h2 className="text-lg font-semibold tracking-tight text-ink">{children}</h2>
      {action}
    </div>
  );
}

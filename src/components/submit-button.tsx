'use client';

import { useFormStatus } from 'react-dom';
import { cn } from './ui';

export function SubmitButton({
  children,
  className,
  pendingLabel = 'Saving…',
  variant = 'primary',
  title,
}: {
  children: React.ReactNode;
  className?: string;
  pendingLabel?: string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  title?: string;
}) {
  const { pending } = useFormStatus();
  const variants: Record<string, string> = {
    primary:
      'rounded-full bg-terracotta px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-terracotta-dark',
    secondary:
      'rounded-full border border-sand-dark bg-white px-5 py-2.5 text-sm font-semibold text-ink hover:bg-sand',
    ghost: 'rounded-full px-3 py-2 text-sm font-medium text-ink-soft hover:bg-sand hover:text-ink',
    danger:
      'rounded-full border border-terracotta/40 bg-white px-4 py-2 text-sm font-semibold text-terracotta-dark hover:bg-terracotta/10',
  };
  return (
    <button
      type="submit"
      title={title}
      disabled={pending}
      className={cn(variants[variant], 'disabled:cursor-not-allowed disabled:opacity-50', className)}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}

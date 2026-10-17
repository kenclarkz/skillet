import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { AppNav } from '@/components/app-nav';
import { SetupNotice } from '@/components/setup-notice';
import { isSupabaseConfigured } from '@/lib/supabase/env';
import { createClient, getCurrentUser } from '@/lib/supabase/server';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Skillet — your family cookbook',
  description:
    'A shared digital cookbook with recipe importing, weekly meal voting, and automatic grocery lists.',
};

export default async function RootLayout({ children }: LayoutProps<'/'>) {
  const configured = isSupabaseConfigured;

  let displayName: string | null = null;
  if (configured) {
    const user = await getCurrentUser();
    if (user) {
      try {
        const supabase = await createClient();
        const { data } = await supabase
          .from('profiles')
          .select('display_name')
          .eq('id', user.id)
          .maybeSingle();
        displayName = data?.display_name ?? user.email ?? null;
      } catch {
        displayName = user.email ?? null;
      }
    }
  }

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-cream">
        {configured ? (
          <>
            <AppNav displayName={displayName} />
            <div className="flex-1 pb-24 sm:pb-10">{children}</div>
          </>
        ) : (
          <SetupNotice />
        )}
      </body>
    </html>
  );
}

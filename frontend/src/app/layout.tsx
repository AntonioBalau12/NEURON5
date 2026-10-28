import type { Metadata } from 'next';
import { creatoDisplay, figtree } from '@/lib/fonts';
import './globals.css';
import 'lenis/dist/lenis.css';

export const metadata: Metadata = {
  title: 'AI AGENT ARENA | POWERED BY NEURON5',
  description: 'AI Agent Arena landing page powered by NEURON5 for the QA DNA challenge at nexxtai hackathon',
  icons: {
    icon: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${creatoDisplay.variable} ${figtree.variable}`}>
      <body className="antialiased selection:bg-[#d7f13b] selection:text-[#202020]">
        <div className="dot-grid" />
        {children}
      </body>
    </html>
  );
}


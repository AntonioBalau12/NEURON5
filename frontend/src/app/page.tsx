import Header from '@/components/Header';
import Studio from '@/components/Studio';
import MarketingSection from '@/components/MarketingSection';

export default function Home() {
  return (
    <>
      <div className="relative flex h-[100dvh] w-full flex-col overflow-hidden">
        <Header />
        <Studio />
      </div>
      <MarketingSection />
    </>
  );
}

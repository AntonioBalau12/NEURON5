import Header from '@/components/Header';
import Studio from '@/components/Studio';
import MarketingSection from '@/components/MarketingSection';

export default function Home() {
  return (
    <div className="relative w-full overflow-x-hidden">
      <Header />
      <Studio />
      <MarketingSection />
    </div>
  );
}

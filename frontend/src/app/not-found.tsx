import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen text-center p-6">
      <h2 className="text-2xl font-bold font-display mb-4">404 - Page Not Found</h2>
      <Link href="/" className="text-[#76910a] hover:text-[#586c07] underline text-sm font-semibold">
        Return to Home
      </Link>
    </div>
  );
}


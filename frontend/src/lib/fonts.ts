import localFont from 'next/font/local';

export const creatoDisplay = localFont({
  src: [
    {
      path: '../../public/fonts/CreatoDisplay-Regular.otf',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../../public/fonts/CreatoDisplay-Medium.otf',
      weight: '500',
      style: 'normal',
    },
    {
      path: '../../public/fonts/CreatoDisplay-Bold.otf',
      weight: '700',
      style: 'normal',
    },
    {
      path: '../../public/fonts/CreatoDisplay-Black.otf',
      weight: '900',
      style: 'normal',
    },
  ],
  variable: '--font-creato',
  display: 'swap',
});

export const figtree = localFont({
  src: '../../public/fonts/Figtree-Variable.ttf',
  variable: '--font-figtree',
  display: 'swap',
});


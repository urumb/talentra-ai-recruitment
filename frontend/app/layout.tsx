import './style.css';
import type {Metadata, Viewport} from 'next';

export const metadata: Metadata = {
  title: 'Talentra · evidence-first candidate screening',
  description: 'Rank CVs against a scorecard, with the evidence quoted from each CV.',
  icons: {icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%23202f5c'/><text x='16' y='23' font-size='20' font-family='Arial' font-weight='700' text-anchor='middle' fill='white'>t</text></svg>"},
};
export const viewport: Viewport = {width: 'device-width', initialScale: 1};

export default function Layout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}

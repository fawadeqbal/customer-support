import "./globals.css";

// Fonts load in the browser from Google Fonts (not at build time, so the build never needs the internet)
const FONTS =
  "https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700" +
  "&family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=JetBrains+Mono:wght@400;500&display=swap";

export const metadata = {
  title: "ShopEase Help | RAG support demo",
  description: "Portfolio demo: a customer-support assistant that answers from a PDF handbook using RAG",
};

// Runs before the page is drawn, so a saved theme never flashes the wrong colours
const themeScript = `try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body>{children}</body>
    </html>
  );
}

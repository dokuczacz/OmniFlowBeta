import "./globals.css";

export const metadata = {
  title: "OmniFlow Beta - Next UI Concept",
  description: "Concept UI for OmniFlow Beta chat operations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}

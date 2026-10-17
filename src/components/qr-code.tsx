import QRCode from 'qrcode';

/** Renders a QR code as inline SVG (server component). */
export async function QrCode({
  value,
  size = 220,
  className,
}: {
  value: string;
  size?: number;
  className?: string;
}) {
  const svg = await QRCode.toString(value, {
    type: 'svg',
    margin: 1,
    width: size,
    errorCorrectionLevel: 'M',
    color: { dark: '#241c15', light: '#00000000' },
  });

  return (
    <div
      className={className}
      style={{ width: size, height: size }}
      aria-label="QR code"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

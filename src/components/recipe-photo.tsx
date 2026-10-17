import Image from 'next/image';

/**
 * Recipe photo with a graceful placeholder. Supabase Storage images are
 * optimized by next/image; other remote hosts are served unoptimized.
 */
export function RecipePhoto({
  src,
  alt,
  sizes = '(max-width: 640px) 80vw, 320px',
  priority = false,
  className,
}: {
  src: string | null | undefined;
  alt: string;
  sizes?: string;
  priority?: boolean;
  className?: string;
}) {
  if (!src) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-sand via-sand to-honey/30 text-4xl">
        <span aria-hidden>🍽️</span>
      </div>
    );
  }
  const isStorage = src.includes('/storage/v1/object/public/');
  return (
    <Image
      src={src}
      alt={alt}
      fill
      sizes={sizes}
      priority={priority}
      unoptimized={!isStorage}
      className={className ?? 'object-cover'}
    />
  );
}

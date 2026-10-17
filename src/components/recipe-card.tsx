import Link from 'next/link';
import type { Recipe } from '@/lib/types';
import { publicPhotoUrl } from '@/lib/supabase/env';
import { RecipePhoto } from './recipe-photo';
import { cn } from './ui';

function totalTime(recipe: Recipe): string | null {
  const total = (recipe.prep_minutes ?? 0) + (recipe.cook_minutes ?? 0);
  if (total <= 0) return null;
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  return mins ? `${hours} hr ${mins} min` : `${hours} hr`;
}

export function RecipeCard({
  recipe,
  className,
  priority,
}: {
  recipe: Recipe;
  className?: string;
  priority?: boolean;
}) {
  const photo = recipe.photo_url ?? publicPhotoUrl(recipe.photo_path);
  const time = totalTime(recipe);
  return (
    <Link
      href={`/recipes/${recipe.id}`}
      className={cn(
        'group block shrink-0 overflow-hidden rounded-3xl border border-sand-dark/70 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md',
        className ?? 'w-64 snap-center'
      )}
    >
      <div className="relative h-40 w-full overflow-hidden bg-sand">
        <RecipePhoto
          src={photo}
          alt={recipe.title}
          priority={priority}
          sizes="(max-width: 640px) 70vw, 280px"
          className="object-cover transition duration-300 group-hover:scale-[1.03]"
        />
        {time ? (
          <span className="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur">
            {time}
          </span>
        ) : null}
      </div>
      <div className="p-4">
        <p className="line-clamp-2 text-base font-semibold leading-snug text-ink">{recipe.title}</p>
        {recipe.description ? (
          <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{recipe.description}</p>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="rounded-full bg-sand px-2 py-0.5 text-[11px] font-medium text-ink-soft">
            Serves {recipe.servings}
          </span>
          {recipe.tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-olive/10 px-2 py-0.5 text-[11px] font-medium text-olive-dark"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </Link>
  );
}

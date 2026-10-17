'use client';

import Link from 'next/link';
import { useState } from 'react';
import { saveRecipe } from '@/app/actions/recipes';
import type { Ingredient, Recipe } from '@/lib/types';
import { parseIngredientText } from '@/lib/ingredients';
import { PhotoUpload } from './photo-upload';
import { SubmitButton } from './submit-button';
import { btnGhost, inputBase, labelBase } from './ui';

export interface RecipeDraft {
  title?: string;
  description?: string | null;
  photo_path?: string | null;
  photo_url?: string | null;
  prep_minutes?: number | null;
  cook_minutes?: number | null;
  servings?: number;
  source_url?: string | null;
  tags?: string[];
  ingredients?: Ingredient[] | string[];
  instructions?: string[];
}

function ingredientsToText(ingredients: RecipeDraft['ingredients']): string {
  if (!ingredients) return '';
  return ingredients
    .map((ing) => {
      if (typeof ing === 'string') return ing;
      if (ing.note && !ing.note.startsWith('(')) {
        return [ing.qty, ing.unit, ing.name].filter(Boolean).join(' ') + `, ${ing.note}`;
      }
      const base = [ing.qty, ing.unit, ing.name].filter(Boolean).join(' ');
      return ing.note ? `${base} ${ing.note}`.trim() : base;
    })
    .join('\n');
}

export function RecipeForm({
  cookbookId,
  cookbookOptions,
  recipe,
  draft,
  importMethod,
}: {
  cookbookId?: string;
  cookbookOptions?: { id: string; name: string }[];
  recipe?: Recipe;
  draft?: RecipeDraft;
  importMethod?: string;
}) {
  const initial = recipe ?? draft ?? {};
  const [ingredientsText, setIngredientsText] = useState(
    recipe ? ingredientsToText(recipe.ingredients) : ingredientsToText(initial.ingredients)
  );
  const [instructionsText, setInstructionsText] = useState(
    (recipe?.instructions ?? initial.instructions ?? []).join('\n')
  );
  const [selectedCookbook, setSelectedCookbook] = useState(cookbookId ?? cookbookOptions?.[0]?.id ?? '');

  const parsedCount = parseIngredientText(ingredientsText).length;

  return (
    <form action={saveRecipe} className="space-y-6">
      {recipe ? <input type="hidden" name="id" value={recipe.id} /> : null}
      {cookbookOptions && !recipe ? (
        <div>
          <label className={labelBase} htmlFor="cookbook_id">
            Cookbook
          </label>
          <select
            id="cookbook_id"
            name="cookbook_id"
            required
            className={inputBase}
            value={selectedCookbook}
            onChange={(e) => setSelectedCookbook(e.target.value)}
          >
            {cookbookOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <input type="hidden" name="cookbook_id" value={selectedCookbook} />
      )}

      {importMethod ? (
        <p className="rounded-xl bg-olive/10 px-3 py-2 text-sm text-olive-dark">
          Imported via {importMethod.replace('-', ' ')}. Review and edit anything below before saving.
        </p>
      ) : null}

      <div className="grid gap-4">
        <div>
          <label className={labelBase} htmlFor="title">
            Recipe title
          </label>
          <input
            id="title"
            name="title"
            required
            defaultValue={recipe?.title ?? initial.title ?? ''}
            placeholder="Grandma's lasagna"
            className={inputBase}
          />
        </div>

        <div>
          <label className={labelBase} htmlFor="description">
            Short description
          </label>
          <textarea
            id="description"
            name="description"
            rows={2}
            defaultValue={recipe?.description ?? initial.description ?? ''}
            placeholder="Why this dish is special"
            className={inputBase}
          />
        </div>

        <div>
          <span className={labelBase}>Photo</span>
          <div className="mt-1">
            <PhotoUpload
              cookbookId={selectedCookbook}
              initialUrl={initial.photo_url ?? null}
              initialPath={recipe?.photo_path ?? draft?.photo_path ?? draft?.photo_url ?? ''}
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className={labelBase} htmlFor="prep_minutes">
              Prep (min)
            </label>
            <input
              id="prep_minutes"
              name="prep_minutes"
              type="number"
              min={0}
              inputMode="numeric"
              defaultValue={recipe?.prep_minutes ?? initial.prep_minutes ?? ''}
              className={inputBase}
            />
          </div>
          <div>
            <label className={labelBase} htmlFor="cook_minutes">
              Cook (min)
            </label>
            <input
              id="cook_minutes"
              name="cook_minutes"
              type="number"
              min={0}
              inputMode="numeric"
              defaultValue={recipe?.cook_minutes ?? initial.cook_minutes ?? ''}
              className={inputBase}
            />
          </div>
          <div>
            <label className={labelBase} htmlFor="servings">
              Servings
            </label>
            <input
              id="servings"
              name="servings"
              type="number"
              min={1}
              max={100}
              inputMode="numeric"
              defaultValue={recipe?.servings ?? initial.servings ?? 4}
              className={inputBase}
            />
          </div>
        </div>

        <div>
          <label className={labelBase} htmlFor="tags">
            Tags
          </label>
          <input
            id="tags"
            name="tags"
            defaultValue={(recipe?.tags ?? initial.tags ?? []).join(', ')}
            placeholder="dinner, vegetarian, quick"
            className={inputBase}
          />
        </div>

        <div>
          <label className={labelBase} htmlFor="ingredients_text">
            Ingredients <span className="text-ink-soft/70">(one per line)</span>
          </label>
          <textarea
            id="ingredients_text"
            name="ingredients_text"
            rows={8}
            required
            value={ingredientsText}
            onChange={(e) => setIngredientsText(e.target.value)}
            placeholder={'1 1/2 cups all-purpose flour\n2 large eggs\nSalt to taste'}
            className={`${inputBase} font-mono text-sm`}
          />
          <p className="mt-1 text-xs text-ink-soft">
            {parsedCount} ingredient{parsedCount === 1 ? '' : 's'} detected. Quantities and units are
            parsed automatically for grocery lists.
          </p>
        </div>

        <div>
          <label className={labelBase} htmlFor="instructions_text">
            Instructions <span className="text-ink-soft/70">(one step per line)</span>
          </label>
          <textarea
            id="instructions_text"
            name="instructions_text"
            rows={8}
            value={instructionsText}
            onChange={(e) => setInstructionsText(e.target.value)}
            placeholder={'Preheat oven to 375°F.\nMix the dry ingredients.'}
            className={`${inputBase} text-sm`}
          />
        </div>

        <div>
          <label className={labelBase} htmlFor="source_url">
            Source URL
          </label>
          <input
            id="source_url"
            name="source_url"
            type="url"
            defaultValue={recipe?.source_url ?? initial.source_url ?? ''}
            placeholder="https://…"
            className={inputBase}
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <SubmitButton>{recipe ? 'Save changes' : 'Add to cookbook'}</SubmitButton>
        <Link href={recipe ? `/recipes/${recipe.id}` : `/cookbooks/${selectedCookbook}`} className={btnGhost}>
          Cancel
        </Link>
      </div>
    </form>
  );
}

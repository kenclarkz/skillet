import { describe, expect, it } from 'vitest';
import { asAnon, asUser, createTestDb, createUser } from './helpers/db';
import { aggregateGroceries, type AggregatedGroceryItem } from '@/lib/grocery/aggregate';
import { generateVoterKey } from '@/lib/guest';
import type { Ingredient } from '@/lib/types';

interface PlanFixture {
  db: Awaited<ReturnType<typeof createTestDb>>;
  alice: string;
  cookbookId: string;
  planId: string;
  recipeIds: string[];
}

async function seedPlan(): Promise<PlanFixture> {
  const db = await createTestDb();
  const alice = await createUser(db, 'alice@example.com', 'Alice');

  const cookbook = await db.query<{ id: string }>(
    'select id from cookbooks where owner_id = $1',
    [alice]
  );
  const cookbookId = cookbook.rows[0].id;

  const recipeA: Ingredient[] = [
    { qty: '2', unit: 'cup', name: 'all-purpose flour', note: null },
    { qty: '1', unit: 'tsp', name: 'Salt', note: null },
    { qty: '3', unit: 'tbsp', name: 'olive oil', note: null },
  ];
  const recipeB: Ingredient[] = [
    { qty: '1', unit: 'cup', name: 'All Purpose Flour', note: null },
    { qty: null, unit: null, name: 'salt', note: 'to taste' },
    { qty: '2', unit: 'clove', name: 'garlic', note: null },
  ];

  const recipeIds: string[] = [];
  for (const [title, ingredients] of [
    ['Focaccia', recipeA],
    ['Garlic Bread', recipeB],
  ] as const) {
    const res = await asUser(db, alice, () =>
      db.query<{ id: string }>(
        `insert into recipes (cookbook_id, created_by, title, servings, ingredients, instructions)
         values ($1, $2, $3, 4, $4::jsonb, array['Mix', 'Bake'])
         returning id`,
        [cookbookId, alice, title, JSON.stringify(ingredients)]
      )
    );
    recipeIds.push(res.rows[0].id);
  }

  const plan = await asUser(db, alice, () =>
    db.query<{ id: string }>(
      `insert into weekly_plans (cookbook_id, week_start, title)
       values ($1, date_trunc('week', now())::date, 'This week')
       returning id`,
      [cookbookId]
    )
  );
  const planId = plan.rows[0].id;

  for (const recipeId of recipeIds) {
    await asUser(db, alice, () =>
      db.query(
        `insert into plan_recipes (plan_id, recipe_id, added_by, selected)
         values ($1, $2, $3, true)`,
        [planId, recipeId, alice]
      )
    );
  }

  return { db, alice, cookbookId, planId, recipeIds };
}

describe('plan -> grocery flow', () => {
  it('aggregates selected recipes, merges units, and skips pantry staples', async () => {
    const { db, alice, planId } = await seedPlan();

    const rows = await asUser(db, alice, () =>
      db.query<{
        title: string;
        id: string;
        ingredients: Ingredient[];
      }>(
        `select r.id, r.title, r.ingredients
         from plan_recipes pr
         join recipes r on r.id = pr.recipe_id
         where pr.plan_id = $1 and pr.selected = true`,
        [planId]
      )
    );
    expect(rows.rows).toHaveLength(2);

    const source = rows.rows.flatMap((recipe) =>
      recipe.ingredients.map((ing) => ({
        ...ing,
        recipeId: recipe.id,
        recipeTitle: recipe.title,
      }))
    );

    const items = aggregateGroceries(source, { pantry: new Set(['salt']) });
    const byName = new Map(items.map((item) => [item.normalized_name, item]));

    const flour = byName.get('all purpose flour') as AggregatedGroceryItem;
    expect(flour).toBeTruthy();
    // 2 cups + 1 cup across two recipes.
    expect(flour.qty).toBe(3);
    expect(flour.unit).toBe('cup');
    expect(flour.recipe_ids).toHaveLength(2);

    const salt = byName.get('salt') as AggregatedGroceryItem;
    expect(salt.in_pantry).toBe(true);

    const garlic = byName.get('garlic') as AggregatedGroceryItem;
    expect(garlic.qty).toBe(2);
    expect(garlic.in_pantry).toBe(false);

    // Pantry items are excluded from what we shop for; the rest are included.
    const shoppable = items.filter((item) => !item.in_pantry);
    expect(shoppable.map((item) => item.normalized_name).sort()).toEqual([
      'all purpose flour',
      'garlic',
      'olive oil',
    ]);

    await db.close();
  });

  it('persists grocery items, honours checkboxes, and filters excluded rows for shopping', async () => {
    const { db, alice, cookbookId, planId } = await seedPlan();

    const rows = await asUser(db, alice, () =>
      db.query<{ title: string; id: string; ingredients: Ingredient[] }>(
        `select r.id, r.title, r.ingredients
         from plan_recipes pr join recipes r on r.id = pr.recipe_id
         where pr.plan_id = $1 and pr.selected = true`,
        [planId]
      )
    );
    const source = rows.rows.flatMap((recipe) =>
      recipe.ingredients.map((ing) => ({ ...ing, recipeId: recipe.id, recipeTitle: recipe.title }))
    );
    const items = aggregateGroceries(source, { pantry: new Set(['salt']) });

    const list = await asUser(db, alice, () =>
      db.query<{ id: string }>(
        `insert into grocery_lists (plan_id, created_by) values ($1, $2) returning id`,
        [planId, alice]
      )
    );
    const listId = list.rows[0].id;

    for (const item of items) {
      await asUser(db, alice, () =>
        db.query(
          `insert into grocery_items
             (list_id, name, normalized_name, qty, unit, recipe_ids, in_pantry, excluded)
           values ($1, $2, $3, $4, $5, $6::uuid[], $7, $8)`,
          [
            listId,
            item.name,
            item.normalized_name,
            item.qty,
            item.unit,
            item.recipe_ids,
            item.in_pantry,
            item.in_pantry,
          ]
        )
      );
    }

    const stored = await asUser(db, alice, () =>
      db.query<{ name: string; in_pantry: boolean; excluded: boolean; checked: boolean }>(
        'select name, in_pantry, excluded, checked from grocery_items where list_id = $1 order by name',
        [listId]
      )
    );
    expect(stored.rows).toHaveLength(items.length);
    expect(stored.rows.find((r) => r.name.toLowerCase() === 'salt')?.excluded).toBe(true);

    await asUser(db, alice, () =>
      db.query(
        `update grocery_items set checked = true
         where list_id = $1 and normalized_name = 'garlic'`,
        [listId]
      )
    );

    const shoppable = await asUser(db, alice, () =>
      db.query<{ name: string }>(
        'select name from grocery_items where list_id = $1 and excluded = false order by name',
        [listId]
      )
    );
    expect(shoppable.rows.map((r) => r.name.toLowerCase())).toEqual([
      'all-purpose flour',
      'garlic',
      'olive oil',
    ]);

    // Ensure the cookbook link survives for RLS-scoped reads.
    const link = await db.query<{ cookbook_id: string }>(
      'select cookbook_id from weekly_plans where id = $1',
      [planId]
    );
    expect(link.rows[0].cookbook_id).toBe(cookbookId);

    await db.close();
  });
});

describe('guest voting flow', () => {
  it('lets an anonymous guest vote through a vote invite and reflects tallies', async () => {
    const { db, alice, cookbookId, planId, recipeIds } = await seedPlan();

    const invite = await asUser(db, alice, () =>
      db.query<{ token: string }>(
        `insert into invites (cookbook_id, kind, plan_id, created_by)
         values ($1, 'vote', $2, $3)
         returning token`,
        [cookbookId, planId, alice]
      )
    );
    const token = invite.rows[0].token;

    const voterKey = 'guest:test-device';
    await asAnon(db, () =>
      db.query('select public.cast_vote($1, $2, $3, $4, $5, $6)', [
        planId,
        recipeIds[0],
        voterKey,
        'Jordan',
        1,
        token,
      ])
    );

    await asAnon(db, () =>
      db.query('select public.cast_vote($1, $2, $3, $4, $5, $6)', [
        planId,
        recipeIds[1],
        voterKey,
        'Jordan',
        -1,
        token,
      ])
    );

    const ballot = await asAnon(db, () =>
      db.query<{ ballot: { tallies: Record<string, { up: number; down: number }>; my_votes: Record<string, number> } }>(
        'select public.get_vote_ballot($1, $2) as ballot',
        [token, voterKey]
      )
    );

    const data = ballot.rows[0].ballot;
    expect(data.tallies[recipeIds[0]].up).toBe(1);
    expect(data.tallies[recipeIds[1]].down).toBe(1);
    expect(data.my_votes[recipeIds[0]]).toBe(1);
    expect(data.my_votes[recipeIds[1]]).toBe(-1);

    // Changing a vote updates rather than duplicating.
    await asAnon(db, () =>
      db.query('select public.cast_vote($1, $2, $3, $4, $5, $6)', [
        planId,
        recipeIds[1],
        voterKey,
        'Jordan',
        1,
        token,
      ])
    );
    const count = await db.query<{ count: number }>(
      'select count(*)::int as count from votes where plan_id = $1 and voter_key = $2',
      [planId, voterKey]
    );
    expect(count.rows[0].count).toBe(2);

    await db.close();
  });

  it('rejects guest votes without a valid invite', async () => {
    const { db, planId, recipeIds } = await seedPlan();

    await expect(
      asAnon(db, () =>
        db.query('select public.cast_vote($1, $2, $3, $4, $5, $6)', [
          planId,
          recipeIds[0],
          'guest:evil',
          'Mallory',
          1,
          'not-a-real-token',
        ])
      )
    ).rejects.toThrow();

    await db.close();
  });

  it('lets a signed-in user join a shared cookbook with a member invite', async () => {
    const { db, alice, cookbookId } = await seedPlan();
    const bob = await createUser(db, 'bob@example.com', 'Bob');

    const invite = await asUser(db, alice, () =>
      db.query<{ token: string }>(
        `insert into invites (cookbook_id, kind, role, created_by)
         values ($1, 'member', 'editor', $2)
         returning token`,
        [cookbookId, alice]
      )
    );

    const joined = await asUser(db, bob, () =>
      db.query<{ cookbook_id: string }>('select public.join_cookbook($1) as cookbook_id', [
        invite.rows[0].token,
      ])
    );
    expect(joined.rows[0].cookbook_id).toBe(cookbookId);

    const membership = await db.query<{ role: string }>(
      'select role from cookbook_members where cookbook_id = $1 and user_id = $2',
      [cookbookId, bob]
    );
    expect(membership.rows[0].role).toBe('editor');

    await db.close();
  });
});

describe('voter key helper', () => {
  it('produces stable, prefixed guest keys', () => {
    const key = generateVoterKey();
    expect(key.startsWith('guest:')).toBe(true);
    expect(generateVoterKey()).not.toBe(key);
  });
});

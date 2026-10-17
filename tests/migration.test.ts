import { describe, expect, it } from 'vitest';
import { asAnon, asUser, createTestDb, createUser } from './helpers/db';

describe('migration + RLS', () => {
  it('creates a profile and a default cookbook for new users', async () => {
    const db = await createTestDb();
    const userId = await createUser(db, 'alice@example.com', 'Alice');

    const profile = await db.query<{ display_name: string }>(
      'select display_name from profiles where id = $1',
      [userId]
    );
    expect(profile.rows[0].display_name).toBe('Alice');

    const books = await db.query<{ name: string }>(
      'select name from cookbooks where owner_id = $1',
      [userId]
    );
    expect(books.rows).toHaveLength(1);
    expect(books.rows[0].name).toContain('Alice');
  });

  it('lets an owner create recipes but hides private cookbooks from other users', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const bob = await createUser(db, 'bob@example.com', 'Bob');

    const book = await db.query<{ id: string }>(
      'select id from cookbooks where owner_id = $1',
      [alice]
    );
    const cookbookId = book.rows[0].id;

    const recipe = await asUser(db, alice, () =>
      db.query<{ id: string }>(
        `insert into recipes (cookbook_id, created_by, title, servings, ingredients, instructions)
         values ($1, $2, 'Chili', 4, '[]'::jsonb, array['Simmer'])
         returning id`,
        [cookbookId, alice]
      )
    );
    expect(recipe.rows[0].id).toBeTruthy();

    const bobSees = await asUser(db, bob, () =>
      db.query('select * from recipes where id = $1', [recipe.rows[0].id])
    );
    expect(bobSees.rows).toHaveLength(0);

    const ownerSees = await asUser(db, alice, () =>
      db.query('select * from recipes where id = $1', [recipe.rows[0].id])
    );
    expect(ownerSees.rows).toHaveLength(1);
  });

  it('lets a viewer read but not write, and an editor write', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const viewer = await createUser(db, 'viewer@example.com', 'Vera');
    const editor = await createUser(db, 'editor@example.com', 'Evan');

    const book = await asUser(db, alice, () =>
      db.query<{ id: string }>('select id from cookbooks where owner_id = $1', [alice])
    );
    const cookbookId = book.rows[0].id;

    await asUser(db, alice, () =>
      db.query(
        `insert into cookbook_members (cookbook_id, user_id, role) values
         ($1, $2, 'viewer'), ($1, $3, 'editor')`,
        [cookbookId, viewer, editor]
      )
    );

    const ownerRecipe = await asUser(db, alice, () =>
      db.query<{ id: string }>(
        `insert into recipes (cookbook_id, title) values ($1, 'Soup') returning id`,
        [cookbookId]
      )
    );

    // viewer can read
    const viewerRead = await asUser(db, viewer, () =>
      db.query('select id from recipes where id = $1', [ownerRecipe.rows[0].id])
    );
    expect(viewerRead.rows).toHaveLength(1);

    // viewer cannot write
    await expect(
      asUser(db, viewer, () =>
        db.query(`insert into recipes (cookbook_id, title) values ($1, 'Nope')`, [cookbookId])
      )
    ).rejects.toThrow();

    // editor can write
    const editorWrite = await asUser(db, editor, () =>
      db.query<{ id: string }>(
        `insert into recipes (cookbook_id, title) values ($1, 'Bread') returning id`,
        [cookbookId]
      )
    );
    expect(editorWrite.rows[0].id).toBeTruthy();
  });

  it('supports guest voting through a vote invite token', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const cookbookId = (
      await db.query<{ id: string }>('select id from cookbooks where owner_id = $1', [alice])
    ).rows[0].id;

    const recipeId = (
      await asUser(db, alice, () =>
        db.query<{ id: string }>(
          `insert into recipes (cookbook_id, title) values ($1, 'Tacos') returning id`,
          [cookbookId]
        )
      )
    ).rows[0].id;

    const planId = (
      await asUser(db, alice, () =>
        db.query<{ id: string }>(
          `insert into weekly_plans (cookbook_id, week_start, created_by)
           values ($1, current_date, $2) returning id`,
          [cookbookId, alice]
        )
      )
    ).rows[0].id;

    await asUser(db, alice, () =>
      db.query('insert into plan_recipes (plan_id, recipe_id) values ($1, $2)', [
        planId,
        recipeId,
      ])
    );

    const token = (
      await asUser(db, alice, () =>
        db.query<{ token: string }>(
          `insert into invites (cookbook_id, kind, plan_id, created_by)
           values ($1, 'vote', $2, $3) returning token`,
          [cookbookId, planId, alice]
        )
      )
    ).rows[0].token;

    // Guest (anon) can fetch the ballot...
    const ballot = await asAnon(db, () =>
      db.query<{ get_vote_ballot: { recipes: unknown[]; plan: { id: string } } }>(
        `select get_vote_ballot($1, $2)`,
        [token, 'guest:abc']
      )
    );
    expect(ballot.rows[0].get_vote_ballot.plan.id).toBe(planId);
    expect(ballot.rows[0].get_vote_ballot.recipes).toHaveLength(1);

    // ...and vote without an account.
    await asAnon(db, () =>
      db.query(`select cast_vote($1, $2, $3, $4, $5, $6)`, [
        planId,
        recipeId,
        'guest:abc',
        'Grandma',
        1,
        token,
      ])
    );

    const tally = await db.query<{ value: number; voter_name: string }>(
      'select value, voter_name from votes where plan_id = $1',
      [planId]
    );
    expect(tally.rows).toHaveLength(1);
    expect(tally.rows[0].voter_name).toBe('Grandma');
    expect(Number(tally.rows[0].value)).toBe(1);
  });

  it('rejects guest votes without a valid token', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const cookbookId = (
      await db.query<{ id: string }>('select id from cookbooks where owner_id = $1', [alice])
    ).rows[0].id;
    const recipeId = (
      await asUser(db, alice, () =>
        db.query<{ id: string }>(
          `insert into recipes (cookbook_id, title) values ($1, 'Pizza') returning id`,
          [cookbookId]
        )
      )
    ).rows[0].id;
    const planId = (
      await asUser(db, alice, () =>
        db.query<{ id: string }>(
          `insert into weekly_plans (cookbook_id, week_start) values ($1, current_date) returning id`,
          [cookbookId]
        )
      )
    ).rows[0].id;

    await expect(
      asAnon(db, () =>
        db.query(`select cast_vote($1, $2, $3, $4, $5, $6)`, [
          planId,
          recipeId,
          'guest:xyz',
          'Intruder',
          1,
          'not-a-real-token',
        ])
      )
    ).rejects.toThrow(/not authorized/);
  });

  it('joins a cookbook with a member invite', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const bob = await createUser(db, 'bob@example.com', 'Bob');
    const cookbookId = (
      await db.query<{ id: string }>('select id from cookbooks where owner_id = $1', [alice])
    ).rows[0].id;

    const token = (
      await asUser(db, alice, () =>
        db.query<{ token: string }>(
          `insert into invites (cookbook_id, kind, role, created_by)
           values ($1, 'member', 'editor', $2) returning token`,
          [cookbookId, alice]
        )
      )
    ).rows[0].token;

    const joined = await asUser(db, bob, () =>
      db.query<{ join_cookbook: string }>('select join_cookbook($1)', [token])
    );
    expect(joined.rows[0].join_cookbook).toBe(cookbookId);

    const role = await asUser(db, bob, () =>
      db.query<{ cookbook_role: string }>('select cookbook_role($1)', [cookbookId])
    );
    expect(role.rows[0].cookbook_role).toBe('editor');
  });

  it('isolates pantry items and grocery lists per user/cookbook', async () => {
    const db = await createTestDb();
    const alice = await createUser(db, 'alice@example.com', 'Alice');
    const bob = await createUser(db, 'bob@example.com', 'Bob');

    await asUser(db, alice, () =>
      db.query(`insert into pantry_items (user_id, name, normalized_name) values ($1, 'Salt', 'salt')`, [alice])
    );
    await asUser(db, alice, () =>
      db.query(`insert into pantry_items (user_id, name, normalized_name) values ($1, 'Pepper', 'pepper')`, [alice])
    );

    const bobPantry = await asUser(db, bob, () => db.query('select * from pantry_items'));
    expect(bobPantry.rows).toHaveLength(0);

    const alicePantry = await asUser(db, alice, () => db.query('select * from pantry_items'));
    expect(alicePantry.rows).toHaveLength(2);
  });
});

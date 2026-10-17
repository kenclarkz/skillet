-- Digital cookbook app: schema, RLS, triggers, RPCs
-- Requires Supabase (provides auth + storage schemas). Uses only core SQL
-- functions (pgcrypto is not required).

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default 'Chef',
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.cookbooks (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  description text,
  is_private boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index cookbooks_owner_idx on public.cookbooks(owner_id);

create table public.cookbook_members (
  cookbook_id uuid not null references public.cookbooks(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('editor', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (cookbook_id, user_id)
);
create index cookbook_members_user_idx on public.cookbook_members(user_id);

create table public.invites (
  id uuid primary key default gen_random_uuid(),
  cookbook_id uuid not null references public.cookbooks(id) on delete cascade,
  token text not null unique default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  kind text not null check (kind in ('vote', 'member')),
  role text check (role in ('editor', 'viewer')),
  plan_id uuid,
  created_by uuid references auth.users(id) on delete set null,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
create index invites_cookbook_idx on public.invites(cookbook_id);

create table public.weekly_plans (
  id uuid primary key default gen_random_uuid(),
  cookbook_id uuid not null references public.cookbooks(id) on delete cascade,
  week_start date not null,
  title text,
  status text not null default 'open' check (status in ('open', 'closed')),
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (cookbook_id, week_start)
);
create index weekly_plans_cookbook_idx on public.weekly_plans(cookbook_id);

alter table public.invites
  add constraint invites_plan_fk
  foreign key (plan_id) references public.weekly_plans(id) on delete cascade;

create table public.recipes (
  id uuid primary key default gen_random_uuid(),
  cookbook_id uuid not null references public.cookbooks(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  title text not null check (char_length(title) between 1 and 200),
  description text,
  photo_path text,
  prep_minutes integer check (prep_minutes >= 0),
  cook_minutes integer check (cook_minutes >= 0),
  servings integer not null default 4 check (servings between 1 and 100),
  source_url text,
  tags text[] not null default '{}',
  ingredients jsonb not null default '[]'::jsonb,
  instructions text[] not null default '{}',
  status text not null default 'published' check (status in ('published', 'draft')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index recipes_cookbook_idx on public.recipes(cookbook_id);

create table public.plan_recipes (
  plan_id uuid not null references public.weekly_plans(id) on delete cascade,
  recipe_id uuid not null references public.recipes(id) on delete cascade,
  added_by uuid references auth.users(id) on delete set null,
  selected boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (plan_id, recipe_id)
);
create index plan_recipes_recipe_idx on public.plan_recipes(recipe_id);

create table public.votes (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.weekly_plans(id) on delete cascade,
  recipe_id uuid not null references public.recipes(id) on delete cascade,
  voter_key text not null check (char_length(voter_key) between 1 and 80),
  voter_name text not null check (char_length(voter_name) between 1 and 60),
  value smallint not null check (value between -1 and 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (plan_id, recipe_id, voter_key)
);
create index votes_plan_idx on public.votes(plan_id);

create table public.pantry_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  normalized_name text not null,
  created_at timestamptz not null default now(),
  unique (user_id, normalized_name)
);

create table public.grocery_lists (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null unique references public.weekly_plans(id) on delete cascade,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.grocery_items (
  id uuid primary key default gen_random_uuid(),
  list_id uuid not null references public.grocery_lists(id) on delete cascade,
  name text not null,
  normalized_name text not null,
  qty numeric,
  unit text not null default '',
  recipe_ids uuid[] not null default '{}',
  checked boolean not null default false,
  excluded boolean not null default false,
  in_pantry boolean not null default false,
  sort_key text not null default '',
  created_at timestamptz not null default now()
);
create index grocery_items_list_idx on public.grocery_items(list_id);

-- ---------------------------------------------------------------------------
-- Access helpers (defined after tables because SQL bodies are validated)
-- ---------------------------------------------------------------------------

-- Role of the current user in a cookbook: 'owner' | 'editor' | 'viewer' | null
create or replace function public.cookbook_role(cookbook_id uuid)
returns text
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select case
    when c.owner_id = auth.uid() then 'owner'
    else (select m.role from cookbook_members m
          where m.cookbook_id = c.id and m.user_id = auth.uid())
  end
  from cookbooks c
  where c.id = cookbook_id;
$$;

revoke all on function public.cookbook_role(uuid) from public;
grant execute on function public.cookbook_role(uuid) to anon, authenticated;

create or replace function public.can_view_cookbook(cookbook_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1 from cookbooks c
    where c.id = cookbook_id
      and (
        c.owner_id = auth.uid()
        or (not c.is_private and auth.uid() is not null)
        or exists (select 1 from cookbook_members m
                   where m.cookbook_id = c.id and m.user_id = auth.uid())
      )
  );
$$;

revoke all on function public.can_view_cookbook(uuid) from public;
grant execute on function public.can_view_cookbook(uuid) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();
create trigger cookbooks_updated_at before update on public.cookbooks
  for each row execute function public.set_updated_at();
create trigger recipes_updated_at before update on public.recipes
  for each row execute function public.set_updated_at();
create trigger weekly_plans_updated_at before update on public.weekly_plans
  for each row execute function public.set_updated_at();
create trigger votes_updated_at before update on public.votes
  for each row execute function public.set_updated_at();
create trigger grocery_lists_updated_at before update on public.grocery_lists
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- New-user bootstrap: profile + default cookbook
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_name text;
  v_cookbook_id uuid;
begin
  v_name := coalesce(
    nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''),
    nullif(trim(new.raw_user_meta_data ->> 'full_name'), ''),
    split_part(coalesce(new.email, 'Chef'), '@', 1)
  );

  insert into public.profiles (id, display_name) values (new.id, v_name);

  insert into public.cookbooks (owner_id, name, is_private)
  values (new.id, v_name || '''s Cookbook', true)
  returning id into v_cookbook_id;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.cookbooks enable row level security;
alter table public.cookbook_members enable row level security;
alter table public.invites enable row level security;
alter table public.weekly_plans enable row level security;
alter table public.plan_recipes enable row level security;
alter table public.recipes enable row level security;
alter table public.votes enable row level security;
alter table public.pantry_items enable row level security;
alter table public.grocery_lists enable row level security;
alter table public.grocery_items enable row level security;

-- profiles
create policy "profiles are viewable by authenticated users"
  on public.profiles for select to authenticated using (true);
create policy "users can update own profile"
  on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
create policy "users can insert own profile"
  on public.profiles for insert to authenticated with check (id = auth.uid());

-- cookbooks
create policy "cookbooks visible to owner, members, or public"
  on public.cookbooks for select to authenticated
  using (
    owner_id = auth.uid()
    or not is_private
    or exists (select 1 from public.cookbook_members m
               where m.cookbook_id = cookbooks.id and m.user_id = auth.uid())
  );
create policy "users can create cookbooks"
  on public.cookbooks for insert to authenticated
  with check (owner_id = auth.uid());
create policy "owners can update cookbooks"
  on public.cookbooks for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "owners can delete cookbooks"
  on public.cookbooks for delete to authenticated
  using (owner_id = auth.uid());

-- cookbook_members
create policy "members and owner can view membership"
  on public.cookbook_members for select to authenticated
  using (
    user_id = auth.uid()
    or public.cookbook_role(cookbook_id) = 'owner'
  );
create policy "owner manages members"
  on public.cookbook_members for insert to authenticated
  with check (public.cookbook_role(cookbook_id) = 'owner');
create policy "owner updates members"
  on public.cookbook_members for update to authenticated
  using (public.cookbook_role(cookbook_id) = 'owner')
  with check (public.cookbook_role(cookbook_id) = 'owner');
create policy "owner removes members"
  on public.cookbook_members for delete to authenticated
  using (public.cookbook_role(cookbook_id) = 'owner' or user_id = auth.uid());

-- invites
create policy "invites visible to cookbook owner"
  on public.invites for select to authenticated
  using (public.cookbook_role(cookbook_id) = 'owner');
create policy "owner creates invites"
  on public.invites for insert to authenticated
  with check (public.cookbook_role(cookbook_id) = 'owner' and created_by = auth.uid());
create policy "owner updates invites"
  on public.invites for update to authenticated
  using (public.cookbook_role(cookbook_id) = 'owner');
create policy "owner deletes invites"
  on public.invites for delete to authenticated
  using (public.cookbook_role(cookbook_id) = 'owner');

-- weekly_plans
create policy "plans visible with cookbook"
  on public.weekly_plans for select to authenticated
  using (public.can_view_cookbook(cookbook_id));
create policy "editors create plans"
  on public.weekly_plans for insert to authenticated
  with check (public.cookbook_role(cookbook_id) in ('owner', 'editor'));
create policy "editors update plans"
  on public.weekly_plans for update to authenticated
  using (public.cookbook_role(cookbook_id) in ('owner', 'editor'));
create policy "editors delete plans"
  on public.weekly_plans for delete to authenticated
  using (public.cookbook_role(cookbook_id) in ('owner', 'editor'));

-- recipes
create policy "recipes visible with cookbook"
  on public.recipes for select to authenticated
  using (public.can_view_cookbook(cookbook_id));
create policy "editors create recipes"
  on public.recipes for insert to authenticated
  with check (public.cookbook_role(cookbook_id) in ('owner', 'editor'));
create policy "editors update recipes"
  on public.recipes for update to authenticated
  using (public.cookbook_role(cookbook_id) in ('owner', 'editor'));
create policy "editors delete recipes"
  on public.recipes for delete to authenticated
  using (public.cookbook_role(cookbook_id) in ('owner', 'editor'));

-- plan_recipes
create policy "plan recipes visible with plan"
  on public.plan_recipes for select to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.can_view_cookbook(p.cookbook_id)
  ));
create policy "editors manage plan recipes"
  on public.plan_recipes for insert to authenticated
  with check (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
  ));
create policy "editors update plan recipes"
  on public.plan_recipes for update to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
  ));
create policy "editors delete plan recipes"
  on public.plan_recipes for delete to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
  ));

-- votes (authenticated members vote directly; guests use cast_vote RPC)
create policy "votes visible with plan"
  on public.votes for select to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.can_view_cookbook(p.cookbook_id)
  ));
create policy "members vote as themselves"
  on public.votes for insert to authenticated
  with check (
    voter_key = 'user:' || auth.uid()::text
    and exists (
      select 1 from public.weekly_plans p where p.id = plan_id
        and public.can_view_cookbook(p.cookbook_id)
    )
  );
create policy "members update own votes"
  on public.votes for update to authenticated
  using (voter_key = 'user:' || auth.uid()::text)
  with check (voter_key = 'user:' || auth.uid()::text);
create policy "members delete own votes"
  on public.votes for delete to authenticated
  using (voter_key = 'user:' || auth.uid()::text);

-- pantry_items
create policy "own pantry"
  on public.pantry_items for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- grocery_lists
create policy "list visible with plan cookbook"
  on public.grocery_lists for select to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.can_view_cookbook(p.cookbook_id)
  ));
create policy "editors create list"
  on public.grocery_lists for insert to authenticated
  with check (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
  ) and created_by = auth.uid());
create policy "editors update list"
  on public.grocery_lists for update to authenticated
  using (exists (
    select 1 from public.weekly_plans p where p.id = plan_id
      and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
  ));

-- grocery_items
create policy "items visible with list"
  on public.grocery_items for select to authenticated
  using (exists (
    select 1 from public.grocery_lists l where l.id = list_id
      and exists (
        select 1 from public.weekly_plans p where p.id = l.plan_id
          and public.can_view_cookbook(p.cookbook_id)
      )
  ));
create policy "editors manage items"
  on public.grocery_items for insert to authenticated
  with check (exists (
    select 1 from public.grocery_lists l where l.id = list_id
      and exists (
        select 1 from public.weekly_plans p where p.id = l.plan_id
          and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
      )
  ));
create policy "editors update items"
  on public.grocery_items for update to authenticated
  using (exists (
    select 1 from public.grocery_lists l where l.id = list_id
      and exists (
        select 1 from public.weekly_plans p where p.id = l.plan_id
          and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
      )
  ));
create policy "editors delete items"
  on public.grocery_items for delete to authenticated
  using (exists (
    select 1 from public.grocery_lists l where l.id = list_id
      and exists (
        select 1 from public.weekly_plans p where p.id = l.plan_id
          and public.cookbook_role(p.cookbook_id) in ('owner', 'editor')
      )
  ));

-- ---------------------------------------------------------------------------
-- RPCs (SECURITY DEFINER so guests/invited users can act with a token)
-- ---------------------------------------------------------------------------

-- Vote (member or guest with invite token). voter_key: 'user:<id>' or 'guest:<id>'.
create or replace function public.cast_vote(
  p_plan_id uuid,
  p_recipe_id uuid,
  p_voter_key text,
  p_voter_name text,
  p_value smallint,
  p_invite_token text default null
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_cookbook_id uuid;
  v_is_member boolean;
  v_invite_ok boolean;
begin
  if p_value not in (-1, 0, 1) then
    raise exception 'invalid vote value';
  end if;

  select cookbook_id into v_cookbook_id from weekly_plans where id = p_plan_id;
  if v_cookbook_id is null then
    raise exception 'plan not found';
  end if;

  if not exists (select 1 from recipes where id = p_recipe_id and cookbook_id = v_cookbook_id) then
    raise exception 'recipe not in plan cookbook';
  end if;

  v_is_member := public.cookbook_role(v_cookbook_id) is not null;

  v_invite_ok := false;
  if p_invite_token is not null then
    select exists (
      select 1 from invites i
      where i.token = p_invite_token
        and i.kind = 'vote'
        and i.cookbook_id = v_cookbook_id
        and (i.plan_id is null or i.plan_id = p_plan_id)
        and i.revoked_at is null
        and (i.expires_at is null or i.expires_at > now())
    ) into v_invite_ok;
  end if;

  if not v_is_member and not v_invite_ok then
    raise exception 'not authorized to vote';
  end if;

  if p_voter_key like 'user:%' then
    if not v_is_member then
      raise exception 'member vote requires membership';
    end if;
  elsif not v_invite_ok then
    raise exception 'valid invite required';
  end if;

  insert into votes (plan_id, recipe_id, voter_key, voter_name, value)
  values (p_plan_id, p_recipe_id, p_voter_key, p_voter_name, p_value)
  on conflict (plan_id, recipe_id, voter_key)
  do update set value = excluded.value, voter_name = excluded.voter_name, updated_at = now();
end;
$$;

revoke all on function public.cast_vote(uuid, uuid, text, text, smallint, text) from public;
grant execute on function public.cast_vote(uuid, uuid, text, text, smallint, text) to anon, authenticated;

-- Ballot for a guest (or member) using a vote invite token. No account needed.
create or replace function public.get_vote_ballot(
  p_invite_token text,
  p_voter_key text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_invite invites%rowtype;
  v_result jsonb;
begin
  select * into v_invite from invites
  where token = p_invite_token
    and kind = 'vote'
    and revoked_at is null
    and (expires_at is null or expires_at > now());

  if not found then
    raise exception 'invalid or expired invite';
  end if;

  select jsonb_build_object(
    'cookbook', (
      select jsonb_build_object('id', c.id, 'name', c.name)
      from cookbooks c where c.id = v_invite.cookbook_id
    ),
    'plan', (
      select jsonb_build_object(
        'id', p.id, 'week_start', p.week_start, 'title', p.title,
        'status', p.status, 'cookbook_id', p.cookbook_id
      )
      from weekly_plans p
      where p.id = coalesce(v_invite.plan_id, (
        select p2.id from weekly_plans p2
        where p2.cookbook_id = v_invite.cookbook_id
        order by p2.week_start desc limit 1
      ))
    ),
    'recipes', coalesce((
      select jsonb_agg(jsonb_build_object(
        'id', r.id,
        'title', r.title,
        'description', r.description,
        'photo_path', r.photo_path,
        'tags', r.tags,
        'prep_minutes', r.prep_minutes,
        'cook_minutes', r.cook_minutes,
        'servings', r.servings
      ) order by r.title)
      from plan_recipes pr
      join recipes r on r.id = pr.recipe_id
      where pr.plan_id = coalesce(v_invite.plan_id, (
        select p2.id from weekly_plans p2
        where p2.cookbook_id = v_invite.cookbook_id
        order by p2.week_start desc limit 1
      ))
    ), '[]'::jsonb),
    'tallies', coalesce((
      select jsonb_object_agg(t.recipe_id, t.data)
      from (
        select v.recipe_id,
          jsonb_build_object(
            'up', count(*) filter (where v.value = 1),
            'down', count(*) filter (where v.value = -1),
            'names', jsonb_agg(distinct v.voter_name)
          ) as data
        from votes v
        where v.plan_id = coalesce(v_invite.plan_id, (
          select p2.id from weekly_plans p2
          where p2.cookbook_id = v_invite.cookbook_id
          order by p2.week_start desc limit 1
        ))
        group by v.recipe_id
      ) t
    ), '{}'::jsonb),
    'my_votes', coalesce((
      select jsonb_object_agg(v.recipe_id, v.value)
      from votes v
      where p_voter_key is not null
        and v.voter_key = p_voter_key
        and v.plan_id = coalesce(v_invite.plan_id, (
          select p2.id from weekly_plans p2
          where p2.cookbook_id = v_invite.cookbook_id
          order by p2.week_start desc limit 1
        ))
    ), '{}'::jsonb)
  ) into v_result;

  return v_result;
end;
$$;

revoke all on function public.get_vote_ballot(text, text) from public;
grant execute on function public.get_vote_ballot(text, text) to anon, authenticated;

-- Join a cookbook with a member invite token (authenticated users only).
create or replace function public.join_cookbook(p_invite_token text)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_invite invites%rowtype;
begin
  if auth.uid() is null then
    raise exception 'sign in required';
  end if;

  select * into v_invite from invites
  where token = p_invite_token
    and kind = 'member'
    and revoked_at is null
    and (expires_at is null or expires_at > now());

  if not found then
    raise exception 'invalid or expired invite';
  end if;

  insert into cookbook_members (cookbook_id, user_id, role)
  values (v_invite.cookbook_id, auth.uid(), coalesce(v_invite.role, 'viewer'))
  on conflict (cookbook_id, user_id) do nothing;

  return v_invite.cookbook_id;
end;
$$;

revoke all on function public.join_cookbook(text) from public;
grant execute on function public.join_cookbook(text) to authenticated;

-- ---------------------------------------------------------------------------
-- Storage bucket for recipe photos
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('recipe-photos', 'recipe-photos', true)
on conflict (id) do nothing;

create policy "recipe photos readable"
  on storage.objects for select
  using (bucket_id = 'recipe-photos');

create policy "cookbook editors upload photos"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'recipe-photos'
    and public.cookbook_role(((storage.foldername(name))[1])::uuid) in ('owner', 'editor')
  );

create policy "cookbook editors update photos"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'recipe-photos'
    and public.cookbook_role(((storage.foldername(name))[1])::uuid) in ('owner', 'editor')
  );

create policy "cookbook editors delete photos"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'recipe-photos'
    and public.cookbook_role(((storage.foldername(name))[1])::uuid) in ('owner', 'editor')
  );

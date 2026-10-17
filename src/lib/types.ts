// Shared domain types for the digital cookbook app.

export type CookbookRole = 'owner' | 'editor' | 'viewer';

export interface Profile {
  id: string;
  display_name: string;
  avatar_url: string | null;
}

export interface Cookbook {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  is_private: boolean;
  created_at: string;
}

export interface CookbookMember {
  cookbook_id: string;
  user_id: string;
  role: 'editor' | 'viewer';
  created_at: string;
  profile?: Profile | null;
}

export interface Ingredient {
  /** Free-form quantity text as authored, e.g. "1 1/2" or "2" or "to taste". */
  qty: string | null;
  /** Unit, e.g. "cup", "tbsp", "clove". Null for countable items. */
  unit: string | null;
  /** Ingredient name, e.g. "all-purpose flour". */
  name: string;
  note: string | null;
}

export interface Recipe {
  id: string;
  cookbook_id: string;
  created_by: string | null;
  title: string;
  description: string | null;
  photo_path: string | null;
  prep_minutes: number | null;
  cook_minutes: number | null;
  servings: number;
  source_url: string | null;
  tags: string[];
  ingredients: Ingredient[];
  instructions: string[];
  status: 'published' | 'draft';
  created_at: string;
  updated_at: string;
  photo_url?: string | null;
}

export interface WeeklyPlan {
  id: string;
  cookbook_id: string;
  week_start: string;
  title: string | null;
  status: 'open' | 'closed';
  created_at: string;
}

export interface PlanRecipe {
  plan_id: string;
  recipe_id: string;
  selected: boolean;
  recipe?: Recipe | null;
}

export type VoteValue = -1 | 0 | 1;

export interface Vote {
  id: string;
  plan_id: string;
  recipe_id: string;
  voter_key: string;
  voter_name: string;
  value: VoteValue;
  updated_at: string;
}

export interface Invite {
  id: string;
  cookbook_id: string;
  token: string;
  kind: 'vote' | 'member';
  role: 'editor' | 'viewer' | null;
  plan_id: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface PantryItem {
  id: string;
  user_id: string;
  name: string;
  normalized_name: string;
}

export interface GroceryList {
  id: string;
  plan_id: string;
  created_at: string;
}

export interface GroceryItem {
  id: string;
  list_id: string;
  name: string;
  normalized_name: string;
  qty: number | null;
  unit: string | null;
  recipe_ids: string[];
  checked: boolean;
  excluded: boolean;
  in_pantry: boolean;
  recipes?: { id: string; title: string }[];
}

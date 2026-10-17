import { notFound } from 'next/navigation';
import { createInvite, removeMember, revokeInvite, updateMemberRole } from '@/app/actions/cookbooks';
import { CopyLink } from '@/components/copy-link';
import { QrCode } from '@/components/qr-code';
import { SubmitButton } from '@/components/submit-button';
import { Badge, Card, EmptyState, inputBase, labelBase } from '@/components/ui';
import { getRole, requireUser } from '@/lib/auth';
import { getCookbook, getInvites, getMembers } from '@/lib/queries';

export const dynamic = 'force-dynamic';

function appUrl(): string {
  return process.env.NEXT_PUBLIC_APP_URL?.replace(/\/$/, '') ?? '';
}

export default async function MembersPage({ params }: PageProps<'/cookbooks/[id]/members'>) {
  const { id } = await params;
  const { supabase, user } = await requireUser();

  const cookbook = await getCookbook(supabase, id);
  if (!cookbook) notFound();

  const role = await getRole(supabase, id);
  if (!role) notFound();
  const isOwner = role === 'owner';

  const [members, invites] = await Promise.all([getMembers(supabase, id), getInvites(supabase, id)]);

  const activeInvites = invites.filter(
    (invite) =>
      !invite.revoked_at && (!invite.expires_at || new Date(invite.expires_at) > new Date())
  );

  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8">
      <h1 className="text-2xl font-bold tracking-tight text-ink">Sharing “{cookbook.name}”</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Invite people to cook with you. Editors can add and change recipes; viewers can browse and vote.
      </p>

      <section className="mt-8">
        <h2 className="mb-3 text-lg font-semibold text-ink">People ({members.length + 1})</h2>
        <Card className="divide-y divide-sand-dark/60 p-0">
          <div className="flex items-center justify-between gap-3 p-4">
            <div>
              <p className="font-medium text-ink">
                {cookbook.owner_id === user.id ? 'You' : 'Cookbook owner'}
              </p>
              <p className="text-xs text-ink-soft">Owner</p>
            </div>
            <Badge tone="terracotta">owner</Badge>
          </div>

          {members.map((member) => (
            <div key={member.user_id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <p className="font-medium text-ink">
                  {member.profile?.display_name ?? 'Member'}
                  {member.user_id === user.id ? ' (you)' : ''}
                </p>
                <p className="text-xs text-ink-soft">
                  Joined {new Date(member.created_at).toLocaleDateString()}
                </p>
              </div>

              {isOwner ? (
                <div className="flex items-center gap-2">
                  <form action={updateMemberRole} className="flex items-center gap-2">
                    <input type="hidden" name="cookbook_id" value={id} />
                    <input type="hidden" name="user_id" value={member.user_id} />
                    <select
                      name="role"
                      defaultValue={member.role}
                      className="rounded-xl border border-sand-dark bg-white px-3 py-2 text-sm"
                    >
                      <option value="viewer">Viewer</option>
                      <option value="editor">Editor</option>
                    </select>
                    <SubmitButton variant="secondary" pendingLabel="…">
                      Save
                    </SubmitButton>
                  </form>
                  {member.user_id !== user.id ? (
                    <form action={removeMember}>
                      <input type="hidden" name="cookbook_id" value={id} />
                      <input type="hidden" name="user_id" value={member.user_id} />
                      <SubmitButton variant="danger" pendingLabel="…">
                        Remove
                      </SubmitButton>
                    </form>
                  ) : null}
                </div>
              ) : (
                <Badge tone={member.role === 'editor' ? 'olive' : 'neutral'}>{member.role}</Badge>
              )}
            </div>
          ))}
        </Card>
      </section>

      {isOwner ? (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-semibold text-ink">Invite someone</h2>
          <Card>
            <form action={createInvite} className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
              <input type="hidden" name="cookbook_id" value={id} />
              <input type="hidden" name="kind" value="member" />
              <div>
                <label className={labelBase} htmlFor="role">
                  Access level
                </label>
                <select id="role" name="role" defaultValue="viewer" className={`${inputBase} sm:w-40`}>
                  <option value="viewer">Viewer</option>
                  <option value="editor">Editor</option>
                </select>
              </div>
              <div>
                <label className={labelBase} htmlFor="expires_days">
                  Expires (days)
                </label>
                <input
                  id="expires_days"
                  name="expires_days"
                  type="number"
                  min={0}
                  defaultValue={14}
                  className={`${inputBase} sm:w-28`}
                />
              </div>
              <SubmitButton pendingLabel="Creating…">Create invite link</SubmitButton>
            </form>
          </Card>

          <h3 className="mb-3 mt-6 text-base font-semibold text-ink">Active invite links</h3>
          {activeInvites.length === 0 ? (
            <EmptyState title="No active invites" description="Create a link above and share it." />
          ) : (
            <ul className="space-y-3">
              {activeInvites.map((invite) => {
                const path = invite.kind === 'vote' ? `/vote/${invite.token}` : `/invite/${invite.token}`;
                const url = `${appUrl()}${path}`;
                return (
                  <li key={invite.id}>
                    <Card className="space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Badge tone={invite.kind === 'vote' ? 'honey' : 'olive'}>{invite.kind}</Badge>
                          {invite.role ? <span className="text-xs text-ink-soft">{invite.role}</span> : null}
                          <span className="text-xs text-ink-soft">
                            {invite.expires_at
                              ? `expires ${new Date(invite.expires_at).toLocaleDateString()}`
                              : 'no expiry'}
                          </span>
                        </div>
                        <form action={revokeInvite}>
                          <input type="hidden" name="id" value={invite.id} />
                          <input type="hidden" name="cookbook_id" value={id} />
                          <SubmitButton variant="danger" pendingLabel="…">
                            Revoke
                          </SubmitButton>
                        </form>
                      </div>

                      <CopyLink url={url} />

                      {invite.kind === 'vote' ? (
                        <div className="flex justify-center pt-1">
                          <QrCode value={url} size={160} />
                        </div>
                      ) : (
                        <p className="text-xs text-ink-soft">
                          Send this link to someone with an account. They&apos;ll be added as{' '}
                          {invite.role ?? 'viewer'} when they open it.
                        </p>
                      )}
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ) : null}
    </main>
  );
}

export default function SettingsPage() {
  return (
    <div className="py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Settings</h1>
      <p className="mt-2 text-neutral-600">Workspace, account, and billing settings.</p>
      <div className="mt-8 space-y-4">
        <div className="rounded-xl border border-neutral-200 bg-white p-6">
          <h2 className="font-semibold text-neutral-900">Workspace</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Member management and roles arrive with the workspace UI in Milestone 2+.
          </p>
        </div>
        <div className="rounded-xl border border-neutral-200 bg-white p-6">
          <h2 className="font-semibold text-neutral-900">Billing</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Stripe checkout and the customer portal land in Milestone 10.
          </p>
        </div>
      </div>
    </div>
  );
}

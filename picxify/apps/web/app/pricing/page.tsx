const plans = [
  {
    name: "Free",
    price: "$0",
    features: ["3 dashboards/month", "Small uploads", "Public share links with watermark"],
  },
  {
    name: "Creator",
    price: "$19/mo",
    features: [
      "50 dashboards/month",
      "Private share links",
      "Exports",
      "Editable assumptions",
      "Unlimited viewers",
    ],
  },
  {
    name: "Team",
    price: "$49/editor/mo",
    features: [
      "Shared workspace",
      "Brand themes",
      "Comments and permissions",
      "300 generations/editor/month",
    ],
  },
  {
    name: "Business",
    price: "from $299/mo",
    features: [
      "3 editors included",
      "White label + custom domain",
      "Retention controls",
      "API and scheduled refresh",
    ],
  },
];

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-16">
      <h1 className="text-3xl font-bold tracking-tight text-neutral-900">Pricing</h1>
      <p className="mt-2 text-neutral-600">Viewers are always free. Creators and editors pay.</p>
      <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {plans.map((plan) => (
          <div key={plan.name} className="rounded-xl border border-neutral-200 bg-white p-6">
            <h2 className="font-semibold text-neutral-900">{plan.name}</h2>
            <p className="mt-1 text-2xl font-bold text-neutral-900">{plan.price}</p>
            <ul className="mt-4 space-y-2 text-sm text-neutral-600">
              {plan.features.map((feature) => (
                <li key={feature}>• {feature}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

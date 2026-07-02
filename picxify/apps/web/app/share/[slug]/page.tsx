import { ShareView } from "@/components/dashboard/share-view";

export default async function SharePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <ShareView slug={slug} />;
}

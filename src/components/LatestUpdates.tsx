import { Plus, Pencil } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const updates = [
  {
    title: "Holiday Schedule and Office Closures",
    category: "General",
    status: "Draft",
    excerpt: "Please note that our offices will be closed on December 24th, 25th, and January 1st in observance of the holidays. We wish everyone a safe and joyful holiday season!",
  },
  {
    title: "Q1 Town Hall Meeting Scheduled",
    category: "Events",
    status: "Published",
    excerpt: "Join us on January 15th for the quarterly town hall. Topics include 2026 strategic goals and community improvements.",
  },
];

const LatestUpdates = () => {
  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-4">
        <CardTitle className="text-lg font-heading text-primary">Latest Updates</CardTitle>
        <button className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-muted transition-colors text-muted-foreground">
          <Plus className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent className="space-y-5">
        {updates.map((update) => (
          <div key={update.title} className="border-b border-border pb-4 last:border-0 last:pb-0">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="font-semibold text-sm text-foreground">{update.title}</h3>
              <div className="flex items-center gap-2 shrink-0">
                <Badge variant="secondary" className="text-xs">{update.category}</Badge>
                <Badge variant={update.status === "Draft" ? "outline" : "default"} className="text-xs">
                  {update.status}
                </Badge>
                <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">{update.excerpt}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default LatestUpdates;

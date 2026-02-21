import { Users, Monitor, Heart, Building2, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const departments = [
  { name: "Human Resources", desc: "Benefits, policies, training", icon: Users, color: "text-pink-500 bg-pink-50" },
  { name: "Information Technology", desc: "Support, systems, security", icon: Monitor, color: "text-blue-500 bg-blue-50" },
  { name: "Health & Wellness", desc: "Clinical programs, compliance", icon: Heart, color: "text-rose-500 bg-rose-50" },
  { name: "Facilities", desc: "Maintenance, operations", icon: Building2, color: "text-primary bg-secondary" },
];

const DepartmentsList = () => {
  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg font-heading text-primary">Departments</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {departments.map((dept) => (
          <a
            key={dept.name}
            href="#"
            className="flex items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-muted group"
          >
            <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 ${dept.color}`}>
              <dept.icon className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground">{dept.name}</p>
              <p className="text-xs text-muted-foreground">{dept.desc}</p>
            </div>
            <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
        ))}
      </CardContent>
    </Card>
  );
};

export default DepartmentsList;

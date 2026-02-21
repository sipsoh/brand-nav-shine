import { AlertCircle } from "lucide-react";

const AnnouncementBanner = () => {
  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 -mt-6 relative z-20">
      <div className="rounded-lg border border-accent/30 bg-accent/10 px-5 py-3.5 flex items-start gap-3 shadow-sm">
        <AlertCircle className="h-5 w-5 text-accent mt-0.5 shrink-0" />
        <p className="text-sm text-foreground">
          <span className="font-semibold">Important:</span> Annual compliance training due by December 31st. Please complete all required modules in the Learning Management System.
        </p>
      </div>
    </div>
  );
};

export default AnnouncementBanner;

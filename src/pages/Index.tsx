import Navbar from "@/components/Navbar";
import HeroHeader from "@/components/HeroHeader";
import AnnouncementBanner from "@/components/AnnouncementBanner";
import LatestUpdates from "@/components/LatestUpdates";
import DepartmentsList from "@/components/DepartmentsList";

const Index = () => {
  return (
    <div className="min-h-screen bg-background font-body">
      <Navbar />
      <HeroHeader />
      <AnnouncementBanner />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3">
            <LatestUpdates />
          </div>
          <div className="lg:col-span-2">
            <DepartmentsList />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Index;

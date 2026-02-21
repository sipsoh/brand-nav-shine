import { useState, useRef } from "react";
import { Home, Building2, Users, Briefcase, Search, ChevronDown, ChevronRight, Menu, X, Bell, Wrench, BookOpen, MapPin, Shield, Heart, DollarSign, Laptop, FileText, GraduationCap, FolderOpen } from "lucide-react";
import logo from "@/assets/logo.png";

type SubPage = { title: string; href: string };
type MegaItem = { title: string; description: string; icon: any; href: string; subPages?: SubPage[] };

const megaMenus: Record<string, MegaItem[]> = {
  Facilities: [
    { title: "All Facilities", description: "Browse all managed properties", icon: Building2, href: "/facilities" },
  ],
  Departments: [
    {
      title: "Human Resources", description: "Benefits, policies & onboarding", icon: Heart, href: "/departments/hr",
      subPages: [
        { title: "Policies", href: "/departments/hr/policies" },
        { title: "Documents", href: "/departments/hr/documents" },
        { title: "Trainings", href: "/departments/hr/trainings" },
      ],
    },
    {
      title: "Finance", description: "Budgets, invoices & reporting", icon: DollarSign, href: "/departments/finance",
      subPages: [
        { title: "Invoices", href: "/departments/finance/invoices" },
        { title: "Budgets", href: "/departments/finance/budgets" },
        { title: "Reports", href: "/departments/finance/reports" },
      ],
    },
    {
      title: "IT Support", description: "Tech help & system access", icon: Laptop, href: "/departments/it",
      subPages: [
        { title: "Help Desk", href: "/departments/it/helpdesk" },
        { title: "System Access", href: "/departments/it/access" },
      ],
    },
    {
      title: "Compliance", description: "Regulations & safety standards", icon: Shield, href: "/departments/compliance",
      subPages: [
        { title: "Regulations", href: "/departments/compliance/regulations" },
        { title: "Safety Standards", href: "/departments/compliance/safety" },
        { title: "Audit Reports", href: "/departments/compliance/audits" },
      ],
    },
  ],
};

const navItems = [
  { label: "Home", icon: Home, href: "/" },
  { label: "Facilities", icon: Building2, href: "/facilities", hasMega: true },
  { label: "Company Directory", icon: Users, href: "/directory" },
  { label: "Departments", icon: Briefcase, href: "/departments", hasMega: true },
];

const Navbar = () => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeMega, setActiveMega] = useState<string | null>(null);
  const [activeSubItem, setActiveSubItem] = useState<string | null>(null);
  const megaTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const subTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const enterMega = (label: string) => {
    if (megaTimeout.current) clearTimeout(megaTimeout.current);
    setActiveMega(label);
  };
  const leaveMega = () => {
    megaTimeout.current = setTimeout(() => {
      setActiveMega(null);
      setActiveSubItem(null);
    }, 150);
  };
  const enterSub = (title: string) => {
    if (subTimeout.current) clearTimeout(subTimeout.current);
    setActiveSubItem(title);
  };
  const leaveSub = () => {
    subTimeout.current = setTimeout(() => setActiveSubItem(null), 100);
  };

  return (
    <nav className="sticky top-0 z-50 bg-white text-foreground shadow-sm border-b border-border">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <a href="/" className="flex items-center gap-2">
            <img src={logo} alt="Evergreen Management" className="h-10" />
          </a>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <div
                key={item.label}
                className="relative"
                onMouseEnter={() => item.hasMega && enterMega(item.label)}
                onMouseLeave={leaveMega}
              >
                <a
                  href={item.href}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                  {item.hasMega && (
                    <ChevronDown className={`h-3 w-3 transition-transform ${activeMega === item.label ? "rotate-180" : ""}`} />
                  )}
                </a>

                {/* Mega Menu */}
                {item.hasMega && activeMega === item.label && (
                  <div
                    className="absolute left-1/2 -translate-x-1/2 top-full pt-2 z-50"
                    onMouseEnter={() => enterMega(item.label)}
                    onMouseLeave={leaveMega}
                  >
                    <div className="relative flex w-[280px] rounded-lg border border-border bg-card shadow-lg">
                      {/* Primary items */}
                      <div className="w-full p-2 space-y-0.5">
                        {megaMenus[item.label]?.map((sub) => (
                          <div
                            key={sub.title}
                            className="relative"
                            onMouseEnter={() => sub.subPages && enterSub(sub.title)}
                            onMouseLeave={leaveSub}
                          >
                            <a
                              href={sub.href}
                              className={`flex items-center gap-3 rounded-md p-3 transition-colors group ${
                                activeSubItem === sub.title ? "bg-muted" : "hover:bg-muted"
                              }`}
                            >
                              <div className="flex-1 min-w-0">
                                <span className="text-sm font-semibold text-foreground">{sub.title}</span>
                                <p className="text-xs text-muted-foreground mt-0.5 truncate">{sub.description}</p>
                              </div>
                              {sub.subPages && (
                                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                              )}
                            </a>

                            {/* Side panel */}
                            {sub.subPages && activeSubItem === sub.title && (
                              <div
                                className="absolute left-full top-0 pl-1.5 z-50"
                                onMouseEnter={() => enterSub(sub.title)}
                                onMouseLeave={leaveSub}
                              >
                                <div className="w-48 rounded-lg border border-border bg-card shadow-lg p-2">
                                  <p className="px-3 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                    {sub.title}
                                  </p>
                                  {sub.subPages.map((sp) => (
                                    <a
                                      key={sp.title}
                                      href={sp.href}
                                      className="block rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                                    >
                                      {sp.title}
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-2">
            {searchOpen ? (
              <div className="hidden md:flex items-center bg-muted rounded-md px-3 py-1.5">
                <Search className="h-4 w-4 text-muted-foreground mr-2" />
                <input
                  autoFocus
                  placeholder="Search this site..."
                  className="bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none w-48"
                  onBlur={() => setSearchOpen(false)}
                />
              </div>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                className="hidden md:flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <Search className="h-4 w-4" />
              </button>
            )}
            <button className="hidden md:flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors relative">
              <Bell className="h-4 w-4" />
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-accent" />
            </button>
            <div className="hidden md:flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
              JD
            </div>

            <button
              className="md:hidden h-9 w-9 flex items-center justify-center rounded-md hover:bg-muted"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Nav */}
      {mobileOpen && (
        <div className="md:hidden border-t border-border px-4 pb-4 pt-2 space-y-1 bg-white">
          {navItems.map((item) => (
            <div key={item.label}>
              <a
                href={item.href}
                className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </a>
              {item.hasMega && megaMenus[item.label] && (
                <div className="ml-10 space-y-0.5">
                  {megaMenus[item.label].map((sub) => (
                    <div key={sub.title}>
                      <a href={sub.href} className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground font-medium">
                        {sub.title}
                      </a>
                      {sub.subPages && (
                        <div className="ml-4 space-y-0.5">
                          {sub.subPages.map((sp) => (
                            <a key={sp.title} href={sp.href} className="block rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
                              {sp.title}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </nav>
  );
};

export default Navbar;

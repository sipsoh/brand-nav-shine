import { useState, useRef } from "react";
import { Home, Building2, Users, Briefcase, Search, ChevronDown, Menu, X, Bell, FileText, Phone, MapPin, Shield, Heart, DollarSign, Wrench, Laptop, BookOpen } from "lucide-react";
import logo from "@/assets/logo.png";

const megaMenus: Record<string, { title: string; description: string; icon: any; href: string }[]> = {
  Facilities: [
    { title: "Property Listings", description: "Browse all managed properties", icon: Building2, href: "/facilities/properties" },
    { title: "Maintenance Requests", description: "Submit and track work orders", icon: Wrench, href: "/facilities/maintenance" },
    { title: "Reservations", description: "Book amenities and common areas", icon: BookOpen, href: "/facilities/reservations" },
    { title: "Site Maps", description: "Interactive property layouts", icon: MapPin, href: "/facilities/maps" },
  ],
  Departments: [
    { title: "Human Resources", description: "Benefits, policies & onboarding", icon: Heart, href: "/departments/hr" },
    { title: "Finance", description: "Budgets, invoices & reporting", icon: DollarSign, href: "/departments/finance" },
    { title: "IT Support", description: "Tech help & system access", icon: Laptop, href: "/departments/it" },
    { title: "Compliance", description: "Regulations & safety standards", icon: Shield, href: "/departments/compliance" },
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
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleEnter = (label: string) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setActiveMega(label);
  };

  const handleLeave = () => {
    timeoutRef.current = setTimeout(() => setActiveMega(null), 150);
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
                onMouseEnter={() => item.hasMega && handleEnter(item.label)}
                onMouseLeave={handleLeave}
              >
                <a
                  href={item.href}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                  {item.hasMega && <ChevronDown className={`h-3 w-3 transition-transform ${activeMega === item.label ? "rotate-180" : ""}`} />}
                </a>

                {/* Mega Menu */}
                {item.hasMega && activeMega === item.label && (
                  <div
                    className="absolute left-1/2 -translate-x-1/2 top-full pt-2 z-50"
                    onMouseEnter={() => handleEnter(item.label)}
                    onMouseLeave={handleLeave}
                  >
                    <div className="w-[480px] rounded-lg border border-border bg-card shadow-lg p-4 grid grid-cols-2 gap-2">
                      {megaMenus[item.label]?.map((sub) => (
                        <a
                          key={sub.title}
                          href={sub.href}
                          className="flex items-start gap-3 rounded-md p-3 transition-colors hover:bg-muted group"
                        >
                          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                            <sub.icon className="h-4 w-4" />
                          </div>
                          <div>
                            <span className="text-sm font-semibold text-foreground">{sub.title}</span>
                            <p className="text-xs text-muted-foreground mt-0.5">{sub.description}</p>
                          </div>
                        </a>
                      ))}
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

            {/* Mobile toggle */}
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
                <div className="ml-10 space-y-1">
                  {megaMenus[item.label].map((sub) => (
                    <a key={sub.title} href={sub.href} className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
                      {sub.title}
                    </a>
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

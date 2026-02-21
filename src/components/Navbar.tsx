import { useState } from "react";
import { Home, Building2, Users, Briefcase, Search, ChevronDown, Menu, X, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";

const navItems = [
  { label: "Home", icon: Home, href: "/" },
  { label: "Facilities", icon: Building2, href: "/facilities", hasDropdown: true },
  { label: "Company Directory", icon: Users, href: "/directory" },
  { label: "Departments", icon: Briefcase, href: "/departments", hasDropdown: true },
];

const Navbar = () => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="sticky top-0 z-50 bg-primary text-primary-foreground shadow-lg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-primary-foreground/30 bg-primary-foreground/10">
              <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden>
                <path d="M12 2C8 2 5 5 5 9c0 3 2.5 6 7 13 4.5-7 7-10 7-13 0-4-3-7-7-7zm0 3a2.5 2.5 0 011.8 4.2L12 12l-1.8-2.8A2.5 2.5 0 0112 5z" />
              </svg>
            </div>
            <div className="leading-tight">
              <span className="text-lg font-bold tracking-wide font-heading">EVERGREEN</span>
              <span className="block text-[10px] uppercase tracking-[0.2em] opacity-70">Management</span>
            </div>
          </div>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-primary-foreground/85 transition-colors hover:bg-primary-foreground/10 hover:text-primary-foreground"
              >
                <item.icon className="h-4 w-4" />
                {item.label}
                {item.hasDropdown && <ChevronDown className="h-3 w-3 opacity-60" />}
              </a>
            ))}
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-2">
            {searchOpen ? (
              <div className="hidden md:flex items-center bg-primary-foreground/10 rounded-md px-3 py-1.5">
                <Search className="h-4 w-4 opacity-60 mr-2" />
                <input
                  autoFocus
                  placeholder="Search this site..."
                  className="bg-transparent text-sm text-primary-foreground placeholder:text-primary-foreground/50 outline-none w-48"
                  onBlur={() => setSearchOpen(false)}
                />
              </div>
            ) : (
              <button
                onClick={() => setSearchOpen(true)}
                className="hidden md:flex h-9 w-9 items-center justify-center rounded-md text-primary-foreground/70 hover:bg-primary-foreground/10 hover:text-primary-foreground transition-colors"
              >
                <Search className="h-4 w-4" />
              </button>
            )}
            <button className="hidden md:flex h-9 w-9 items-center justify-center rounded-md text-primary-foreground/70 hover:bg-primary-foreground/10 hover:text-primary-foreground transition-colors relative">
              <Bell className="h-4 w-4" />
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-accent" />
            </button>
            <div className="hidden md:flex h-8 w-8 items-center justify-center rounded-full bg-primary-foreground/20 text-xs font-semibold">
              JD
            </div>

            {/* Mobile toggle */}
            <button
              className="md:hidden h-9 w-9 flex items-center justify-center rounded-md hover:bg-primary-foreground/10"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Nav */}
      {mobileOpen && (
        <div className="md:hidden border-t border-primary-foreground/10 px-4 pb-4 pt-2 space-y-1">
          {navItems.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-primary-foreground/85 hover:bg-primary-foreground/10"
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </a>
          ))}
        </div>
      )}
    </nav>
  );
};

export default Navbar;

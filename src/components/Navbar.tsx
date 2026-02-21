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
    <nav className="sticky top-0 z-50 bg-white text-foreground shadow-sm border-b border-border">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-primary/30 bg-primary/10 text-primary">
              <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden>
                <path d="M12 2C8 2 5 5 5 9c0 3 2.5 6 7 13 4.5-7 7-10 7-13 0-4-3-7-7-7zm0 3a2.5 2.5 0 011.8 4.2L12 12l-1.8-2.8A2.5 2.5 0 0112 5z" />
              </svg>
            </div>
            <div className="leading-tight">
              <span className="text-lg font-bold tracking-wide font-heading text-foreground">EVERGREEN</span>
              <span className="block text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Management</span>
            </div>
          </div>

          {/* Desktop Nav */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
        <div className="md:hidden border-t border-border px-4 pb-4 pt-2 space-y-1">
          {navItems.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
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

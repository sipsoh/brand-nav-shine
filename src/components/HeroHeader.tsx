import heroImage from "@/assets/hero-building.jpg";

const HeroHeader = () => {
  return (
    <section className="relative h-72 md:h-80 overflow-hidden">
      <img
        src={heroImage}
        alt="Evergreen Management community building"
        className="absolute inset-0 h-full w-full object-cover"
      />
      <div className="absolute inset-0 bg-gradient-to-r from-[hsl(var(--hero-overlay)/0.85)] via-[hsl(var(--hero-overlay)/0.6)] to-transparent" />
      <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex flex-col justify-end h-full pb-10">
        <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white font-heading leading-tight mb-2">
          Welcome to Evergreen Management
        </h1>
        <p className="text-white/80 text-base md:text-lg max-w-xl font-body">
          Your central hub for news, resources, and collaboration across all our communities.
        </p>
      </div>
    </section>
  );
};

export default HeroHeader;

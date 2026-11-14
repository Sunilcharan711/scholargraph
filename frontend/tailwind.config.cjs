module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  corePlugins: {preflight:false},
  theme: {extend:{colors:{card:"var(--panel)", "card-foreground":"var(--text)", "muted-foreground":"var(--muted)"}}},
};

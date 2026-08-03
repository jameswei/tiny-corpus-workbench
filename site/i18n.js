(() => {
  const supportedLocales = ["en", "zh-CN"];
  const resourcePaths = {
    en: "locales/en.json",
    "zh-CN": "locales/zh-CN.json"
  };
  const languageToggle = document.getElementById("lang-toggle");
  const localeCache = new Map();

  function normalizeLocale(locale) {
    return String(locale || "").toLowerCase().startsWith("zh") ? "zh-CN" : "en";
  }

  async function loadLocale(locale) {
    if (localeCache.has(locale)) return localeCache.get(locale);
    const response = await fetch(resourcePaths[locale]);
    if (!response.ok) throw new Error(`Could not load locale resource: ${locale}`);
    const resource = await response.json();
    localeCache.set(locale, resource);
    return resource;
  }

  async function applyLocale(locale) {
    const normalizedLocale = supportedLocales.includes(locale) ? locale : normalizeLocale(locale);
    const resource = await loadLocale(normalizedLocale);
    document.documentElement.lang = normalizedLocale;
    document.title = resource[document.body.dataset.i18nTitle];
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const key = element.dataset.i18n;
      if (resource[key] !== undefined) element.textContent = resource[key];
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      const key = element.dataset.i18nAriaLabel;
      if (resource[key] !== undefined) element.setAttribute("aria-label", resource[key]);
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
      const key = element.dataset.i18nAlt;
      if (resource[key] !== undefined) element.setAttribute("alt", resource[key]);
    });
    document.querySelectorAll("[data-i18n-content]").forEach((element) => {
      const key = element.dataset.i18nContent;
      if (resource[key] !== undefined) element.setAttribute("content", resource[key]);
    });

    const nextLocale = normalizedLocale === "zh-CN" ? "en" : "zh-CN";
    const nextLabelKey = nextLocale === "zh-CN" ? "language.switch_to_zh_cn" : "language.switch_to_en";
    const nextShortKey = nextLocale === "zh-CN" ? "language.short_zh_cn" : "language.short_en";
    languageToggle.textContent = resource[nextShortKey];
    languageToggle.setAttribute("aria-label", resource[nextLabelKey]);
    languageToggle.dataset.nextLocale = nextLocale;
    try { localStorage.setItem("tcw-landing-language", normalizedLocale); } catch { /* The preview works without persistence. */ }
  }

  languageToggle.addEventListener("click", () => {
    applyLocale(languageToggle.dataset.nextLocale).catch((error) => console.error(error));
  });

  const storedLocale = (() => {
    try { return localStorage.getItem("tcw-landing-language"); } catch { return null; }
  })();
  applyLocale(storedLocale || navigator.language).catch((error) => console.error(error));
})();

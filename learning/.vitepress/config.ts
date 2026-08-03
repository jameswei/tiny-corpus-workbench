import { defineConfig } from "vitepress";

type Lesson = { text: string; slug: string };

const englishLessons: Lesson[] = [
  { text: "1. Prepare Documents for a Corpus", slug: "prepare-documents" },
  { text: "2. Capture and Extract", slug: "capture-and-extract" },
  { text: "3. Inspect and Diagnose", slug: "inspect-and-diagnose" },
  { text: "4. Decide and Revise", slug: "decide-and-revise" },
  { text: "5. Inspect a Corpus", slug: "inspect-a-corpus" },
  { text: "6. Practice the Complete Lifecycle", slug: "complete-lifecycle" },
];

const chineseLessons: Lesson[] = [
  { text: "1. 为语料库准备文档", slug: "prepare-documents" },
  { text: "2. 捕获并提取", slug: "capture-and-extract" },
  { text: "3. 检查并诊断", slug: "inspect-and-diagnose" },
  { text: "4. 决策并修订", slug: "decide-and-revise" },
  { text: "5. 检查语料库", slug: "inspect-a-corpus" },
  { text: "6. 演练完整生命周期", slug: "complete-lifecycle" },
];

function englishSidebar() {
  const prefix = "/en/";
  return {
    [prefix]: [
      {
        text: "Learning path",
        items: [
          { text: "Start here", link: `${prefix}index.html` },
          ...englishLessons.map((lesson) => ({ text: lesson.text, link: `${prefix}${lesson.slug}.html` })),
        ],
      },
    ],
  };
}

function chineseSidebar() {
  const prefix = "/zh/";
  return {
    [prefix]: [
      {
        text: "学习路径",
        items: [
          { text: "从这里开始", link: `${prefix}index.html` },
          ...chineseLessons.map((lesson) => ({ text: lesson.text, link: `${prefix}${lesson.slug}.html` })),
        ],
      },
    ],
  };
}

export default defineConfig({
  base: "/tiny-corpus-workbench/learn/",
  cleanUrls: false,
  appearance: false,
  title: "tiny-corpus-workbench Learning Guides",
  description: "Hands-on guides for preparing documents for a corpus.",
  head: [["link", { rel: "icon", type: "image/svg+xml", href: "/tiny-corpus-workbench/assets/favicon.svg" }]],
  locales: {
    en: {
      label: "English",
      lang: "en",
      link: "/en/",
      title: "tiny-corpus-workbench Learning Guides",
      description: "Hands-on guides for preparing documents for a corpus.",
      themeConfig: {
        siteTitle: "Learning Guides",
        nav: [
          { text: "Learning path", link: "/en/index.html" },
        ],
        sidebar: englishSidebar(),
        outline: { label: "On this page", level: "deep" },
        docFooter: { prev: "Previous lesson", next: "Next lesson" },
        langMenuLabel: "Change language",
        sidebarMenuLabel: "Learning menu",
        returnToTopLabel: "Return to top",
      },
    },
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      link: "/zh/",
      title: "tiny-corpus-workbench 学习指南",
      description: "通过动手实践学习如何为语料库准备文档。",
      themeConfig: {
        siteTitle: "学习指南",
        nav: [
          { text: "学习路径", link: "/zh/index.html" },
        ],
        sidebar: chineseSidebar(),
        outline: { label: "本页内容", level: "deep" },
        docFooter: { prev: "上一篇", next: "下一篇" },
        langMenuLabel: "切换语言",
        sidebarMenuLabel: "学习目录",
        returnToTopLabel: "返回顶部",
      },
    },
  },
  themeConfig: {
    i18nRouting: true,
    search: {
      provider: "local",
      options: {
        locales: {
          zh: {
            translations: {
              button: { buttonText: "搜索", buttonAriaLabel: "搜索学习指南" },
              modal: {
                displayDetails: "显示详细列表",
                resetButtonTitle: "清除搜索",
                backButtonTitle: "关闭搜索",
                noResultsText: "没有找到结果",
                footer: {
                  selectText: "选择",
                  selectKeyAriaLabel: "回车",
                  navigateText: "导航",
                  navigateUpKeyAriaLabel: "上箭头",
                  navigateDownKeyAriaLabel: "下箭头",
                  closeText: "关闭",
                  closeKeyAriaLabel: "Esc",
                },
              },
            },
          },
        },
      },
    },
    socialLinks: [{ icon: "github", link: "https://github.com/jameswei/tiny-corpus-workbench", ariaLabel: "tiny-corpus-workbench on GitHub" }],
  },
});

<script setup lang="ts">
import { onMounted } from "vue";

const languageKey = "tcw-learning-language";

function target(language: "en" | "zh") {
  return `./${language}/`;
}

function choose(language: "en" | "zh") {
  window.localStorage.setItem(languageKey, language);
}

onMounted(() => {
  const saved = window.localStorage.getItem(languageKey);
  const detected = window.navigator.languages.some((item) => item.toLowerCase().startsWith("zh")) ? "zh" : "en";
  const language = saved === "en" || saved === "zh" ? saved : detected;
  window.location.replace(target(language));
});
</script>

<template>
  <main class="language-entry">
    <p class="entry-kicker">tiny-corpus-workbench</p>
    <h1>Learning Guides · 学习指南</h1>
    <p>Learn how to prepare a document for a corpus. Choose a language to begin. 学习如何为语料库准备文档。请选择语言开始阅读。</p>
    <div class="language-choices">
      <a :href="target('en')" @click="choose('en')">English</a>
      <a :href="target('zh')" @click="choose('zh')">简体中文</a>
    </div>
  </main>
</template>

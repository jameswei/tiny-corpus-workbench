<script setup lang="ts">
import { inBrowser, useData, useRoute } from "vitepress";
import DefaultTheme from "vitepress/theme";
import { computed, watchEffect } from "vue";

const { lang } = useData();
const route = useRoute();
const isChinese = computed(() => lang.value.startsWith("zh"));

function projectHome() {
  const marker = "/learn/";
  const path = window.location.pathname;
  const markerIndex = path.indexOf(marker);
  const destination = markerIndex === -1 ? "/" : path.slice(0, markerIndex + 1);
  window.location.assign(`${window.location.origin}${destination}`);
}

watchEffect(() => {
  if (!inBrowser || route.path === "/") return;
  window.localStorage.setItem("tcw-learning-language", lang.value.startsWith("zh") ? "zh" : "en");
});
</script>

<template>
  <DefaultTheme.Layout>
    <template #layout-bottom>
      <footer class="learning-footer">
        <div>
          <strong>tiny-corpus-workbench</strong>
        </div>
        <div>
          <a href="../" @click.prevent="projectHome">{{ isChinese ? "返回项目主页" : "Back to project" }}</a>
          <a href="https://github.com/jameswei/tiny-corpus-workbench">GitHub</a>
        </div>
      </footer>
    </template>
  </DefaultTheme.Layout>
</template>

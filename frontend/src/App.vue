<template>
  <div id="app">
    <router-view />
  </div>
</template>

<script setup lang="ts">
// 主應用程式組件
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
  line-height: 1.6;
  color: #333;
  background: #f5f5f5;
}

#app {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

/* 全域按鈕樣式 */
button {
  font-family: inherit;
  cursor: pointer;
  transition: all 0.3s ease;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* 全域輸入框樣式 */
input, textarea, select {
  font-family: inherit;
  transition: all 0.3s ease;
}

input:focus, textarea:focus, select:focus {
  outline: none;
}

/* 滾動條樣式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>

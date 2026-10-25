<template>
  <main class="home">
    <header class="home-header">
      <div class="logo">🌍</div>
      <h1>多語言即時翻譯</h1>
      <p>選擇要使用的功能</p>
    </header>

    <nav class="choices">
      <router-link to="/translator" class="choice">
        <span class="choice-icon">🗣️</span>
        <span class="choice-text">
          <strong>雙向翻譯機</strong>
          <small>一支手機放中間，兩個人面對面對話</small>
        </span>
      </router-link>

      <router-link to="/room" class="choice">
        <span class="choice-icon">👥</span>
        <span class="choice-text">
          <strong>多人連線翻譯／白板</strong>
          <small>建立或加入房間，每個人用自己的手機看翻譯</small>
        </span>
      </router-link>
    </nav>
  </main>
</template>

<style scoped>
.home {
  min-height: 100vh;
  min-height: 100dvh;
  background: linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 1rem 2rem;
  box-sizing: border-box;
}

.home-header {
  text-align: center;
  color: white;
  padding: 3rem 1rem 2rem;
}

.logo {
  font-size: 3.5rem;
  margin-bottom: 0.5rem;
}

h1 {
  font-size: 1.9rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
}

.home-header p {
  color: rgba(255, 255, 255, 0.55);
  font-size: 0.95rem;
  margin: 0;
}

.choices {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.choice {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.4rem 1.25rem;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  color: white;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s;
}

.choice:hover,
.choice:focus-visible {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(167, 139, 250, 0.6);
}

.choice-icon {
  font-size: 2.2rem;
  flex-shrink: 0;
}

.choice-text {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.choice-text strong {
  font-size: 1.15rem;
}

.choice-text small {
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85rem;
  line-height: 1.4;
}
</style>

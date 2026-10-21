<script setup>
import { ref } from 'vue'

const input = ref('')        // 입력창에 쓴 글자
const messages = ref([])     // 대화 목록 [{ role: 'user', text: '...' }, ...]

async function send() {
  const text = input.value.trim()
  if (!text) return
  messages.value.push({ role: 'user', text })
  input.value = ''

  const res = await fetch('http://localhost:8000/chat', {
    method: 'POST',                                   // 본문을 보내니까 POST
    headers: { 'Content-Type': 'application/json' },  // 본문이 JSON이라고 알려줌
    body: JSON.stringify({ message: text }),           // ChatRequest 모양에 맞춰서
  })
  const data = await res.json()
  messages.value.push({ role: 'bot', text: data.reply, sources: data.sources })
}
</script>

<template>
  <main>
    <h1>청년정책 안내</h1>
    <div v-for="(m, i) in messages" :key="i" :class="m.role">
      {{ m.text }}
      <small v-if="m.sources"><br />출처: {{ [...new Set(m.sources)].join(', ') }}</small>
    </div>
    <form @submit.prevent="send">
      <input v-model="input" placeholder="질문을 입력하세요" />
      <button>보내기</button>
    </form>
  </main>
</template>
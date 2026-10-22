<script setup>
import { nextTick, ref } from 'vue'

const API = 'http://localhost:8000'
const input = ref('')
const messages = ref([])     // { role: 'user' | 'bot' | 'error', text, sources?, meta? }
const sending = ref(false)   // 답을 기다리는 중이면 true → 보내기 버튼 잠금 + "작성 중" 표시
const logEl = ref(null)

async function scrollDown() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'user', text })
  input.value = ''
  sending.value = true
  scrollDown()
  try {
    const res = await fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    if (!res.ok) throw new Error(`서버 응답 ${res.status}`)
    const data = await res.json()
    messages.value.push({
      role: data.ok ? 'bot' : 'error',
      text: data.reply,
      sources: [...new Set(data.sources || [])],
      meta: data.path?.length
        ? `경로: ${data.path.join(' → ')} · LLM ${data.llm_calls}회 · ${data.elapsed_sec}초`
        : '',
    })
  } catch (e) {
    // 서버가 꺼져 있거나 CORS·네트워크 문제 → 화면이 멈추지 않게 안내 문구로
    messages.value.push({ role: 'error', text: '서버에 연결할 수 없어요. 백엔드 서버가 켜져 있는지 확인해 주세요.' })
    console.error(e)
  } finally {
    sending.value = false
    scrollDown()
  }
}
</script>

<template>
  <main class="chat">
    <h1>청년정책 안내</h1>
    <p class="hint">예) "2002년생 전주 사는데 월세 지원 받을 수 있어?"</p>
    <section ref="logEl" class="log">
      <div v-for="(m, i) in messages" :key="i" :class="['bubble', m.role]">
        <div class="text">{{ m.text }}</div>
        <div v-if="m.sources?.length" class="sources">출처: {{ m.sources.join(', ') }}</div>
        <div v-if="m.meta" class="meta">{{ m.meta }}</div>
      </div>
      <div v-if="sending" class="bubble bot waiting">답변 작성 중… (로컬 모델은 30~80초 걸릴 수 있어요)</div>
    </section>
    <form @submit.prevent="send">
      <input v-model="input" placeholder="질문을 입력하세요" :disabled="sending" />
      <button :disabled="sending || !input.trim()">{{ sending ? '기다리는 중' : '보내기' }}</button>
    </form>
  </main>
</template>

<style scoped>
.chat { max-width: 760px; margin: 0 auto; padding: 16px; text-align: left; display: flex; flex-direction: column; height: 100vh; box-sizing: border-box; }
h1 { font-size: 24px; margin: 0 0 4px; }
.hint { color: #888; font-size: 14px; margin: 0 0 12px; }
.log { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding: 8px 0; }
.bubble { max-width: 85%; padding: 10px 14px; border-radius: 12px; line-height: 1.55; font-size: 15px; }
.text { white-space: pre-wrap; word-break: keep-all; }   /* 답변의 줄바꿈을 살린다 */
.user { align-self: flex-end; background: #4f6bed; color: #fff; }
.bot { align-self: flex-start; background: #f1f2f6; color: #222; }
.error { align-self: flex-start; background: #fdecec; color: #a12; }
.waiting { color: #666; font-style: italic; }
.sources, .meta { margin-top: 6px; font-size: 12px; color: #777; }
form { display: flex; gap: 8px; padding-top: 8px; }
input { flex: 1; padding: 10px; font-size: 15px; border: 1px solid #ccc; border-radius: 8px; }
button { padding: 10px 16px; font-size: 15px; border-radius: 8px; border: none; background: #4f6bed; color: #fff; cursor: pointer; }
button:disabled { background: #aab; cursor: default; }
</style>

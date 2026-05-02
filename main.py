from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
import httpx
import uvicorn

app = FastAPI(title="Gemini Proxy")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini Proxy</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; }
        .chat-container { scrollbar-width: thin; }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-100">
    <div class="flex h-screen">
        <!-- 侧边栏 -->
        <div class="w-80 bg-zinc-900 border-r border-zinc-800 p-6 flex flex-col">
            <div class="flex items-center gap-3 mb-10">
                <div class="w-10 h-10 bg-blue-600 rounded-2xl flex items-center justify-center text-2xl font-bold">G</div>
                <h1 class="text-3xl font-semibold">Gemini Proxy</h1>
            </div>
            
            <div class="space-y-6">
                <div>
                    <label class="block text-sm text-zinc-400 mb-2">API Key</label>
                    <input id="apiKey" type="password" 
                           class="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 focus:outline-none focus:border-blue-500"
                           placeholder="输入你的 Gemini API Key">
                </div>

                <div>
                    <label class="block text-sm text-zinc-400 mb-2">模型</label>
                    <select id="model" class="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3">
                        <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro (推荐)</option>
                        <option value="gemini-3-flash">Gemini 3 Flash (快速)</option>
                    </select>
                </div>
            </div>

            <button onclick="clearChat()" 
                    class="mt-auto flex items-center gap-2 text-zinc-400 hover:text-white">
                <i class="fas fa-trash"></i> 清空对话
            </button>
        </div>

        <!-- 主聊天区 -->
        <div class="flex-1 flex flex-col">
            <div class="border-b border-zinc-800 p-5 text-lg font-medium flex items-center gap-3">
                <i class="fas fa-robot text-blue-500"></i>
                Gemini 3.1 中转平台
            </div>
            
            <div id="chat" class="flex-1 p-6 overflow-y-auto chat-container space-y-8"></div>

            <div class="p-6 border-t border-zinc-800 bg-zinc-900">
                <div class="max-w-4xl mx-auto flex gap-3">
                    <input id="prompt" type="text" 
                           class="flex-1 bg-zinc-800 border border-zinc-700 rounded-2xl px-6 py-4 focus:outline-none focus:border-blue-500 text-base"
                           placeholder="输入问题... (支持 Markdown)"
                           onkeypress="if(event.key === 'Enter') sendMessage()">
                    <button onclick="sendMessage()" 
                            class="bg-blue-600 hover:bg-blue-700 px-10 rounded-2xl">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
                <p class="text-center text-xs text-zinc-500 mt-4">最大输出 Token 已提升 • 请求由本域名中转</p>
            </div>
        </div>
    </div>

    <script>
        function addMessage(role, content) {
            const chat = document.getElementById('chat');
            const div = document.createElement('div');
            div.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'}`;
            
            if (role === 'assistant') {
                div.innerHTML = `
                    <div class="max-w-3xl bg-zinc-800 rounded-3xl px-6 py-5">
                        <div class="prose prose-invert max-w-none">${marked.parse(content)}</div>
                    </div>`;
            } else {
                div.innerHTML = `
                    <div class="max-w-3xl bg-blue-600 rounded-3xl px-6 py-5">
                        ${content}
                    </div>`;
            }
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function sendMessage() {
            const apiKey = document.getElementById('apiKey').value.trim();
            const model = document.getElementById('model').value;
            const prompt = document.getElementById('prompt').value.trim();

            if (!apiKey) return alert("请输入 API Key");
            if (!prompt) return;

            addMessage('user', prompt);
            document.getElementById('prompt').value = '';

            try {
                const formData = new URLSearchParams();
                formData.append('api_key', apiKey);
                formData.append('model', model);
                formData.append('prompt', prompt);

                const res = await fetch('/api/gemini', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: formData
                });

                const data = await res.json();

                if (data.error) {
                    addMessage('assistant', '错误: ' + JSON.stringify(data.error));
                } else {
                    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || '没有返回内容';
                    addMessage('assistant', text);
                }
            } catch (e) {
                addMessage('assistant', '请求失败，请检查网络或 API Key');
            }
        }

        function clearChat() {
            if (confirm('确定清空所有对话？')) {
                document.getElementById('chat').innerHTML = '';
            }
        }
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML_TEMPLATE

@app.post("/api/gemini")
async def gemini_proxy(
    api_key: str = Form(...),
    model: str = Form(...),
    prompt: str = Form(...)
):
    if not api_key or not prompt:
        return JSONResponse({"error": "缺少 API Key 或提示词"}, status_code=400)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 32768,     # 已大幅提高
            "responseMimeType": "text/markdown"
        }
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, json=payload)
        
        try:
            return response.json()
        except:
            return JSONResponse({"error": response.text}, status_code=response.status_code)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
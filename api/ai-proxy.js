// ARIA RichLife · 服务端代理
// 作用：① 解决国内浏览器直连第三方 API 的 CORS 跨域问题；② 让 API Key 只留在服务器环境变量，不进浏览器/备份文件。
// 部署：把本文件放到仓库的 api/ai-proxy.js 即可（Vercel 自动识别为 Serverless Function，地址 /api/ai-proxy）。
// 设置环境变量（在托管平台后台，仅填你实际要用的供应商）：
//   GEMINI_API_KEY  /  DEEPSEEK_API_KEY  /  ZHIPU_API_KEY  /  TONGYI_API_KEY  /  OPENAI_API_KEY  /  CUSTOM_API_KEY
// 前端「开发者」里把调用方式切到「服务端代理」、选对应服务商即可，无需在 App 里填 Key。

const PROVIDERS = {
  gemini:   { keyEnv: 'GEMINI_API_KEY',   base: 'https://generativelanguage.googleapis.com/v1beta/models' },
  deepseek: { keyEnv: 'DEEPSEEK_API_KEY', base: 'https://api.deepseek.com/v1/chat/completions' },
  zhipu:    { keyEnv: 'ZHIPU_API_KEY',    base: 'https://open.bigmodel.cn/api/paas/v4/chat/completions' },
  tongyi:   { keyEnv: 'TONGYI_API_KEY',   base: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions' },
  openai:   { keyEnv: 'OPENAI_API_KEY',   base: 'https://api.openai.com/v1/chat/completions' },
  custom:   { keyEnv: 'CUSTOM_API_KEY',   base: null }
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', c => { data += c; });
    req.on('end', () => {
      try { resolve(data ? JSON.parse(data) : {}); }
      catch (e) { reject(new Error('请求体不是合法 JSON')); }
    });
    req.on('error', reject);
  });
}

function send(res, code, obj) {
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  });
  res.end(JSON.stringify(obj));
}

export default async function handler(req, res) {
  if (req.method === 'OPTIONS') return send(res, 204, {});
  if (req.method !== 'POST') return send(res, 405, { error: '仅支持 POST' });

  let body;
  try { body = await readBody(req); }
  catch (e) { return send(res, 400, { error: e.message }); }

  const { provider = 'deepseek', model, baseUrl, messages } = body || {};
  const prov = PROVIDERS[provider] || PROVIDERS.custom;
  const apiKey = process.env[prov.keyEnv];
  if (!apiKey) return send(res, 400, { error: '服务端未配置环境变量 ' + prov.keyEnv + '，请在托管平台后台添加' });

  const isGemini = provider === 'gemini';
  try {
    let upstream, headers, payload;
    if (isGemini) {
      const m = model || 'gemini-1.5-flash';
      const base = (baseUrl && baseUrl.trim()) || prov.base;
      upstream = `${base.replace(/\/$/, '')}/${encodeURIComponent(m)}:generateContent?key=${encodeURIComponent(apiKey)}`;
      const parts = (messages || []).map(x => ({
        role: (x.role === 'assistant') ? 'model' : 'user',
        parts: [{ text: x.content || '' }]
      }));
      payload = { contents: parts, generationConfig: { responseMimeType: 'application/json' } };
      headers = { 'Content-Type': 'application/json' };
    } else {
      const base = (baseUrl && baseUrl.trim()) || prov.base;
      if (!base) return send(res, 400, { error: 'custom 模式需在请求中提供 baseUrl' });
      upstream = base;
      headers = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey };
      payload = { model: model || 'deepseek-chat', messages: messages || [], temperature: 0.3 };
    }

    const r = await fetch(upstream, { method: 'POST', headers, body: JSON.stringify(payload) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return send(res, r.status, { error: (j.error && j.error.message) || ('上游错误 ' + r.status) });

    let text = '';
    if (isGemini) text = (j.candidates && j.candidates[0] && j.candidates[0].content && j.candidates[0].content.parts && j.candidates[0].content.parts[0] && j.candidates[0].content.parts[0].text) || '';
    else text = (j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '';

    if (!text) return send(res, 502, { error: '上游未返回文本内容', raw: JSON.stringify(j).slice(0, 200) });
    return send(res, 200, { text });
  } catch (e) {
    return send(res, 500, { error: e.message || '代理内部错误' });
  }
}

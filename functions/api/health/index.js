// 部署自检：/api/health。只返回“有没有配好”，不返回任何口令或数据内容。
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
export async function onRequest({ env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  const tok = (env && env.ADMIN_TOKEN) || globalThis.ADMIN_TOKEN || '';
  let kvOk = false, kvErr = '';
  if (kv) {
    try { await kv.get('c_start'); kvOk = true; } catch (e) { kvErr = String(e && e.message || e).slice(0, 120); }
  } else kvErr = 'kv_not_bound';
  const g = (k) => (env && env[k]) || globalThis[k] || '';
  const cos = !!(g('COS_SECRET_ID') && g('COS_SECRET_KEY') && g('COS_BUCKET') && g('COS_REGION'));
  return new Response(JSON.stringify({
    ok: kvOk && tok.length >= 12,
    kv: kvOk, kv_err: kvErr || undefined,
    admin_token: tok.length >= 12,
    cos, // 小梨 Studio：COS 四个环境变量都填了
    worker_token: g('WORKER_TOKEN').length >= 16,
    time: new Date().toISOString(),
  }), { headers: H });
}

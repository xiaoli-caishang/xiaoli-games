// 导出原始记录（仅管理员）：/api/export?token=你的口令&cursor=
// 口令在 EdgeOne Pages 控制台「环境变量」里设置 ADMIN_TOKEN
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  const tok = (env && env.ADMIN_TOKEN) || globalThis.ADMIN_TOKEN || '';
  const u = new URL(request.url);
  if (!tok || tok.length < 12 || u.searchParams.get('token') !== tok) return new Response('{"ok":false}', { status: 403, headers: H });
  if (!kv) return new Response('{"ok":false,"err":"kv_not_bound"}', { headers: H });
  const prefix = (u.searchParams.get('prefix') || 'r_').replace(/[^\w]/g, '');
  const opt = { prefix, limit: 256 };
  const cursor = u.searchParams.get('cursor'); if (cursor) opt.cursor = cursor;
  const page = await kv.list(opt);
  const keys = (page && page.keys) || [];
  const items = (await Promise.all(keys.map(k => kv.get(k.key, { type: 'json' }).catch(() => null)))).filter(Boolean);
  return new Response(JSON.stringify({ ok: true, items, cursor: page.cursor || (keys.length ? keys[keys.length - 1].key : ''), complete: !!page.complete || keys.length === 0 }), { headers: H });
}

// 返回挑战人数（游戏开场展示用）
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'public, max-age=60' };
export async function onRequest({ env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  if (!kv) return new Response(JSON.stringify({ starts: 0 }), { headers: H });
  const starts = Number(await kv.get('c_start').catch(() => 0)) || 0;
  const agg = await kv.get('agg_v1', { type: 'json' }).catch(() => null);
  return new Response(JSON.stringify({ starts, finished: agg ? agg.n : 0 }), { headers: H });
}

// 接收游戏的匿名统计数据，写入 KV（变量名 xl_kv）。不记录 IP、不记录任何个人信息。
const H = { 'content-type': 'application/json; charset=UTF-8', 'cache-control': 'no-store' };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });
const day8 = ms => new Date(ms + 8 * 3600e3).toISOString().slice(0, 10).replace(/-/g, '');
const str = (v, n, re) => String(v == null ? '' : v).replace(re || /[^\w.\-]/g, '').slice(0, n);
const num = (v, lo, hi) => { const x = Number(v); return Number.isFinite(x) ? Math.min(hi, Math.max(lo, x)) : null; };
const BINS = 80, LO = -0.10, HI = 0.10; // 年化超额分桶：-10% ~ +10%，每 0.25% 一档

export async function onRequest({ request, env }) {
  const kv = globalThis.xl_kv || (env && env.xl_kv);
  if (request.method !== 'POST') return J({ ok: false }, 405);
  if (!kv) return J({ ok: false, err: 'kv_not_bound' });
  const txt = await request.text();
  if (txt.length > 4000) return J({ ok: false }, 413);
  let d; try { d = JSON.parse(txt); } catch (e) { return J({ ok: false }, 400); }
  const id = str(d.id, 16, /[^a-z0-9]/g);
  if (id.length < 8) return J({ ok: false }, 400);
  const ev = ['start', 'year', 'dead', 'end', 'quit'].includes(d.ev) ? d.ev : null;
  if (!ev) return J({ ok: false }, 400);
  const now = Date.now();
  const t0 = Math.abs(Number(d.t0) - now) < 2 * 86400e3 ? Number(d.t0) : now;
  const key = 'r_' + day8(t0) + '_' + id;

  const old = (await kv.get(key, { type: 'json' }).catch(() => null)) || {};
  const prevEv = old.ev;
  if (prevEv === 'end' && ev !== 'end') return J({ ok: true }); // 已完成的局不再被覆盖
  const rec = Object.assign(old, {
    id, ev, v: str(d.v, 8), t0, ts: now, day: day8(t0),
    run: num(d.run, 0, 9999), src: str(d.src, 20), ref: str(d.ref, 60), dev: str(d.dev, 1),
    ch: str(d.ch, 10, /[^ABC]/g), yt: Array.isArray(d.yt) ? d.yt.slice(0, 10).map(x => num(x, 0, 36000)) : [],
    pro: d.pro ? 1 : 0, dur: num(d.dur, 0, 864000),
  });
  if (ev === 'end') Object.assign(rec, {
    y: num(d.y, 0, 10), dead: d.dead ? 1 : 0, ann: num(d.ann, -1, 1), aunt: num(d.aunt, 0, 1000),
    rank: num(d.rank, 1, 59049), beat: num(d.beat, 0, 1), code: str(d.code, 4, /[^TCADLQOM]/g), adv: str(d.adv, 8, /[^a-z]/g),
  });
  if (ev === 'year' || ev === 'dead') rec.y = num(d.y, 0, 10);
  await kv.put(key, JSON.stringify(rec));

  // 汇总（只用于游戏里展示人数和排名；精确分析请用导出的原始记录）
  if (ev === 'start') {
    const c = Number(await kv.get('c_start').catch(() => 0)) || 0;
    await kv.put('c_start', String(c + 1));
    return J({ ok: true, starts: c + 1 });
  }
  if (ev === 'end' && prevEv !== 'end') {
    const agg = (await kv.get('agg_v1', { type: 'json' }).catch(() => null)) || { n: 0, dead: 0, bins: new Array(BINS).fill(0) };
    let below = agg.dead, same = 0, b = -1;
    if (rec.dead) { below = 0; same = agg.dead; }
    else {
      b = Math.max(0, Math.min(BINS - 1, Math.floor((rec.ann - LO) / (HI - LO) * BINS)));
      for (let i = 0; i < b; i++) below += agg.bins[i];
      same = agg.bins[b];
    }
    const beat = agg.n ? (below + same / 2) / agg.n : 0.5;
    agg.n += 1; if (rec.dead) agg.dead += 1; else agg.bins[b] += 1;
    await kv.put('agg_v1', JSON.stringify(agg));
    return J({ ok: true, n: agg.n, beat });
  }
  return J({ ok: true });
}

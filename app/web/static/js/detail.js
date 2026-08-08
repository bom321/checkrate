// detail.js — วาดกราฟแนวโน้มเป็น SVG เอง (ตาม design 10b ไม่พึ่ง Chart.js/CDN)
//
// โครง 10b: กราฟหลักซ้าย "แสดงเฉพาะอัตราที่เลือก" + แผงขวาสำหรับกรอง/เรียง/ติ๊กเลือกเส้น
// ชิปช่วงเวลาอยู่ใต้กราฟ เริ่มต้นที่ "ปีปัจจุบัน" (YTD)
//
// พิกัด SVG เป็น "พิกเซลจริง" (viewBox ตั้งตามขนาดกล่องที่วัดได้ ไม่ fix ไว้ในเทมเพลต) เพราะ 10b
// ล็อกความสูงคอลัมน์กราฟไว้ ถ้าใช้ viewBox ตายตัวแบบเดิม (1500×260) ตัวหนังสือจะย่อ/ยืดตามความกว้าง
// ของจอ — ผลพลอยได้คือขนาดฟอนต์ในกราฟตรงกับ CSS ที่เหลือของหน้าโดยตรง
(function () {
  // ตัวกรองเดือน — ต้องอยู่ก่อน guard ของกราฟ เพราะธนาคารที่ยังไม่มีข้อมูลก็ไม่มีกราฟ
  const monthSel = document.getElementById('month-select');
  if (monthSel) {
    monthSel.addEventListener('change', () => {
      if (monthSel.value) location.href = '/bank/' + monthSel.dataset.code + '?month=' + monthSel.value;
    });
  }

  // (สรุปผลการรัน + reload หลังรันเสร็จ อยู่ใน run.js — ผูกกับ #run-notice ใช้ร่วมกับหน้า overview)

  const dataEl = document.getElementById('chart-data');
  const svg = document.getElementById('trend');
  const plotBox = document.querySelector('.bd-trend-body');
  // กราฟไม่มีใน design บนมือถือ — .bd-trend{display:none} ข้ามการวาดไปเลย
  if (!dataEl || !svg || !plotBox || svg.offsetParent === null) return;

  const payload = JSON.parse(dataEl.textContent);
  const allLabels = payload.labels || [];
  const allDates = payload.dates || [];
  // ผลิตภัณฑ์ที่ไม่มีค่าเลยสักครั้งในประวัติทั้งหมด วาดไม่ได้ (เส้นว่าง) — ตัดออกก่อน ไม่งั้นกิน list/สีไปเปล่า ๆ
  // idx เป็น "อัตลักษณ์สี/การเลือกแสดง" ที่คงที่ตลอด — ผูกกับตำแหน่งในอาร์เรย์นี้ ไม่ใช่ตำแหน่งหลังกรอง/เรียง
  // (คนละอาร์เรย์กันหลัง computeView ตัดตาม range เพราะ series ที่ไม่มีข้อมูลในช่วงนั้นจะหลุดออกไป)
  const allSeries = (payload.datasets || [])
    .filter((d) => d.data.some((v) => v !== null))
    .map((d, idx) => ({ ...d, idx }));
  if (!allLabels.length || !allSeries.length) return;

  // สีเส้นตามลำดับคงที่ (สีที่ i เป็นของผลิตภัณฑ์ที่ i เสมอ) — 3 สีแรกมาจาก design
  // ที่เหลือต่อด้วยชุดสีที่ผ่านการตรวจตาบอดสี (protan/deuteran) เผื่อธนาคารที่ติดตามเกิน 3 รายการ
  const PALETTE = ['#1E8E5A', '#B7791F', '#9B9EA4', '#2B6CB0', '#C2410C', '#7C5CA8', '#00897B', '#B5427E'];
  const colorOf = (idx) => PALETTE[idx % PALETTE.length];

  // เส้นที่เลือกไว้ตอนเปิดหน้าแรก — 3 รายการแรกตาม 7a–7d (ตรงกับ 3 รายการแรกใน rate_targets ของทุก
  // ธนาคารจริงพอดี) 10b เพิ่มแผงขวาให้ติ๊กเพิ่ม/เอาออกได้เอง และเลือกให้เหลือ 0 เส้นก็ได้ (กราฟขึ้น
  // ข้อความว่าง ๆ แทน) — ต่างจากเดิมที่บังคับให้เหลืออย่างน้อย 1 เส้นเสมอ
  const visible = new Set(allSeries.slice(0, 3).map((s) => s.idx));

  const SVGNS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs, text) => {
    const n = document.createElementNS(SVGNS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const add = (parent, name, attrs, text) => parent.appendChild(el(name, attrs, text));

  // ── ตัวช่วยวันที่: บวก/ลบเดือนแบบปฏิทิน (ไม่สนวันที่ในเดือน) ──
  const addMonths = (iso, delta) => {
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(Date.UTC(y, m - 1 + delta, d));
    const pad = (n) => String(n).padStart(2, '0');
    return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
  };
  // ต่างกันกี่เดือนตามปฏิทิน (ปี×12 + เดือน) — สูตรนี้ให้ผลตรงกับตัวเลขในดีไซน์ (เทียบ 26 ส.ค.68→06 ก.ค.69 = ~11)
  const monthsBetween = (iso1, iso2) => {
    const [y1, m1] = iso1.split('-').map(Number);
    const [y2, m2] = iso2.split('-').map(Number);
    return (y2 - y1) * 12 + (m2 - m1);
  };

  // ── ตัดข้อมูลตามช่วงเวลาที่เลือก ──
  // spec: 'all' = ทั้งหมด · 'ytd' = ตั้งแต่ 1 ม.ค. ของปีที่ประกาศล่าสุดอยู่ · ตัวเลข = ย้อนหลังกี่เดือน
  // .idx ของแต่ละ series ยังติดไปด้วยเสมอ
  const computeView = (spec) => {
    if (spec === 'all') return { labels: allLabels, dates: allDates, series: allSeries };
    const lastDate = allDates[allDates.length - 1];
    const cutoff = spec === 'ytd' ? lastDate.slice(0, 4) + '-01-01' : addMonths(lastDate, -spec);
    let startIdx = allDates.findIndex((d) => d >= cutoff);
    if (startIdx === -1) startIdx = allDates.length - 1;
    return {
      labels: allLabels.slice(startIdx),
      dates: allDates.slice(startIdx),
      series: allSeries
        .map((s) => ({ ...s, data: s.data.slice(startIdx) }))
        .filter((s) => s.data.some((v) => v !== null)),
    };
  };

  // ── ตัวช่วยอ่านค่าจาก series ──
  const lastOf = (data) => data.reduce((acc, v) => (v === null ? acc : v), null);
  // ลำดับของประกาศล่าสุดที่ทำให้อัตรานี้ขยับ (-1 = ไม่เคยขยับในช่วงนี้) — ใช้เรียง "เปลี่ยนแปลงล่าสุด"
  // ไล่ถอยหลังโดยจำ "ค่าที่อยู่ถัดไป + ตำแหน่งของมัน" ไว้ ค่าที่ต่างกันคู่แรกที่เจอ = ตำแหน่งที่ขยับล่าสุด
  const lastChangeAt = (data) => {
    let nextV = null, nextI = -1;
    for (let i = data.length - 1; i >= 0; i--) {
      if (data[i] === null) continue;
      if (nextV !== null && Math.abs(data[i] - nextV) > 1e-9) return nextI;
      nextV = data[i]; nextI = i;
    }
    return -1;
  };
  // แยกชื่อผลิตภัณฑ์ออกจาก alias แบบ "3 เดือน / วงเงิน 1 ล้านบาท / บุคคลธรรมดา" ตาม 10a
  // (ส่วนที่ซ้ำกับ pill ประเภทผู้ฝากตัดทิ้ง — alias ที่ไม่มี "/" ก็ยังใช้ได้ แค่ไม่มีบรรทัดรอง)
  const splitLabel = (s) => {
    const parts = String(s.label || '').split('/').map((p) => p.trim()).filter(Boolean);
    const depLabel = s.dep && s.dep.label ? s.dep.label : '';
    return {
      name: parts.length ? parts[0] : String(s.label || ''),
      sub: parts.slice(1).filter((p) => p !== depLabel).join(' · '),
    };
  };

  // ── สถานะของแผงขวา ──
  let depFilter = 'all';      // 'all' หรือ dep.slug
  let sortMode = 'tenor';
  let currentView = null;

  const listEl = document.getElementById('trend-list');
  const filterEl = document.getElementById('trend-filter');
  const clearBtn = document.getElementById('trend-clear');
  const sortSel = document.getElementById('trend-sort');
  const emptyEl = document.getElementById('trend-empty');
  const badge = document.getElementById('trend-badge');
  // ต้องอยู่ก่อน renderSide() เพราะปุ่มดาวน์โหลดถูก disable/enable ที่นั่นตามจำนวนเส้นที่เลือก
  // (ย้ายขึ้นมาจากตอนท้ายไฟล์ที่เดิมประกาศไว้เฉพาะจุดที่ผูก handler ดาวน์โหลด)
  const dlBtn = document.getElementById('trend-download');
  document.getElementById('trend-all-count').textContent = allSeries.length;

  // ── แผงขวา: ชิปกรองประเภทผู้ฝาก + รายการอัตรา ──
  const renderSide = () => {
    const series = currentView.series;

    // ชิปกรอง — นับจาก series ที่มีข้อมูลในช่วงเวลาที่เลือกอยู่ (ประเภทที่ไม่เหลือเลยไม่ต้องโชว์ชิป)
    const groups = [];
    series.forEach((s) => {
      const slug = (s.dep && s.dep.slug) || 'other';
      const label = (s.dep && s.dep.label) || 'อื่น ๆ';
      const g = groups.find((x) => x.slug === slug);
      if (g) g.n += 1; else groups.push({ slug, label, n: 1 });
    });
    // ประเภทที่หายไปจากช่วงนี้ ต้องไม่ค้างเป็นตัวกรองที่กรองจนไม่เหลืออะไร
    if (depFilter !== 'all' && !groups.some((g) => g.slug === depFilter)) depFilter = 'all';

    filterEl.textContent = '';
    const chip = (slug, label, n) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = (depFilter === slug ? 'on' : (slug === 'all' ? '' : 'dep-' + slug));
      b.setAttribute('aria-pressed', String(depFilter === slug));
      b.textContent = `${label} ${n}`;
      b.addEventListener('click', () => { depFilter = slug; renderSide(); });
      filterEl.appendChild(b);
    };
    chip('all', 'ทั้งหมด', series.length);
    if (groups.length > 1) groups.forEach((g) => chip(g.slug, g.label, g.n));

    // เรียงตามที่เลือก — "สถานะเลือก" มาก่อนเสมอ (รายการที่ติ๊กไว้ลอยขึ้นบนสุด ตามดีไซน์ 10b ใหม่)
    // แล้วค่อยตามคีย์ของ dropdown เดิม · tie-break ด้วย idx เสมอ ให้ลำดับนิ่งไม่สลับไปมาเมื่อค่าเท่ากัน
    const shownRows = series.filter((s) => depFilter === 'all' || ((s.dep && s.dep.slug) || 'other') === depFilter);
    const keyOf = {
      tenor: (s) => (s.tenor === null || s.tenor === undefined ? 0 : s.tenor),
      recent: (s) => -lastChangeAt(s.data),
      rate: (s) => -(lastOf(s.data) ?? -Infinity),
    }[sortMode];
    const selRank = (s) => (visible.has(s.idx) ? 0 : 1);
    shownRows.sort((a, b) => (selRank(a) - selRank(b)) || (keyOf(a) - keyOf(b)) || (a.idx - b.idx));

    listEl.textContent = '';
    if (!shownRows.length) {
      const p = document.createElement('div');
      p.className = 'bd-side-empty';
      p.textContent = 'ไม่มีอัตราในตัวกรองนี้';
      listEl.appendChild(p);
    }

    // แถวไม่โชว์ตัวเลขอัตรา/ส่วนต่างอีกแล้ว (ดีไซน์ Rate Trend Chart) — แผงนี้เป็น "ตัวเลือกเส้น" ล้วน ๆ
    // ไม่ใช่ตารางย่อยที่แข่งกับกราฟ ดูค่าจริงได้จากกราฟ/tooltip แทน
    shownRows.forEach((s) => {
      const on = visible.has(s.idx);
      const { name, sub } = splitLabel(s);

      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'bd-side-item ' + (on ? 'on' : 'off');
      row.setAttribute('aria-pressed', String(on));

      // เลือกอยู่ → จุดทึบสีเส้น · ไม่เลือก → ปล่อยว่างให้ CSS ใส่กรอบกลวงเอง (.off .bd-side-dot)
      const dot = document.createElement('span');
      dot.className = 'bd-side-dot';
      if (on) dot.style.background = colorOf(s.idx);

      const main = document.createElement('span');
      main.className = 'bd-side-main';

      const top = document.createElement('span');
      top.className = 'bd-side-top';
      const nm = document.createElement('span');
      nm.className = 'bd-side-name';
      nm.textContent = name;
      top.appendChild(nm);
      if (s.dep && s.dep.label) {
        const dep = document.createElement('span');
        dep.className = 'pill-dep dep-' + s.dep.slug;
        dep.textContent = s.dep.label;
        top.appendChild(dep);
      }
      main.appendChild(top);

      if (sub) {
        const sb = document.createElement('span');
        sb.className = 'bd-side-sub';
        sb.textContent = sub;
        main.appendChild(sb);
      }

      row.append(dot, main);
      row.addEventListener('click', () => {
        if (visible.has(s.idx)) visible.delete(s.idx); else visible.add(s.idx);
        renderSide();
        renderChart();
      });
      listEl.appendChild(row);
    });

    // ตัวนับ (n/ทั้งหมด) นับจาก "ที่เลือกไว้ทั้งหมด" ไม่ใช่แค่ที่มีข้อมูลในช่วงนี้ — สอดคล้องกับ /8 ท้ายตัวนับ
    document.getElementById('trend-on-count').textContent = visible.size;
    clearBtn.disabled = visible.size === 0;
    // ดาวน์โหลดส่งออกเฉพาะเส้นที่ติ๊กไว้ (ดูตัวจัดการดาวน์โหลดท้ายไฟล์) — ไม่มีเส้นเลยก็ไม่มีอะไรให้ export
    if (dlBtn) {
      dlBtn.disabled = visible.size === 0;
      dlBtn.title = visible.size === 0
        ? 'เลือกอัตราอย่างน้อย 1 รายการจากแผงด้านขวาก่อนดาวน์โหลด'
        : 'ดาวน์โหลดข้อมูลกราฟของเส้นที่เลือกไว้เป็นไฟล์ CSV';
    }
  };

  // ── กราฟ ──
  const renderChart = () => {
    const { labels, dates, series } = currentView;
    // เส้นที่ต้องวาดจริง = ที่ผู้ใช้เลือกไว้ ∩ ที่มีข้อมูลในช่วงเวลานี้
    const shown = series.filter((s) => visible.has(s.idx));

    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (badge) { badge.hidden = true; badge.textContent = ''; badge.className = 'bd-trend-badge'; }

    document.getElementById('trend-count').textContent = labels.length;
    const spanEl = document.getElementById('trend-span');
    if (spanEl) {
      const months = labels.length > 1 ? monthsBetween(dates[0], dates[dates.length - 1]) : 0;
      spanEl.textContent = `~${months} เดือนย้อนหลัง`;
    }

    const values = shown.flatMap((d) => d.data.filter((v) => v !== null));
    if (emptyEl) {
      emptyEl.hidden = values.length > 0;
      if (!visible.size) emptyEl.textContent = 'ยังไม่ได้เลือกอัตรา — เลือกจากแผงด้านขวาเพื่อแสดงกราฟ';
      else if (!values.length) emptyEl.textContent = 'อัตราที่เลือกไม่มีข้อมูลในช่วงเวลานี้';
    }
    if (!labels.length || !values.length) return;

    // ── กรอบกราฟ: viewBox = ขนาดจริงของกล่องเป็นพิกเซล ──
    const W = Math.max(320, Math.round(plotBox.clientWidth));
    const H = Math.max(180, Math.round(plotBox.clientHeight));
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

    // ── บันไดขนาดตัวอักษรของกราฟ: อ่านจาก CSS ตอน render แทนเขียน breakpoint ซ้ำใน JS ──
    // CSS (style.css ~1063, @media ≤1080px) เป็น source of truth เดียวเรื่องขนาด — ย่อ
    // --bd-fs-body/--bd-fs-micro ลงหนึ่งขั้นที่จอแคบกว่า 1080px ที่นี่แค่ "ตาม" ค่านั้น ไม่ตัดสินใจเอง
    // เรียกทุกครั้งที่ renderChart ทำงาน (รวมตอน ResizeObserver สั่งวาดใหม่) จึงตามทันตอนข้ามช่วงจอ
    // fallback เป็นค่าเดสก์ท็อปเดิมถ้า parse ไม่ได้/ตัวแปรว่าง กันหน้าพังถ้า CSS เปลี่ยนโครงในอนาคต
    const BODY_BASE = 12.5;   // --bd-fs-body ที่เดสก์ท็อป (>1080px) — ตัวเลข hardcode เดิมทั้งหมดอิงค่านี้
    const MICRO_BASE = 11;    // --bd-fs-micro ที่เดสก์ท็อป
    const readFs = (name, fallback) => {
      const raw = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
      return Number.isFinite(raw) && raw > 0 ? raw : fallback;
    };
    const bodyPx = readFs('--bd-fs-body', BODY_BASE);
    const microPx = readFs('--bd-fs-micro', MICRO_BASE);
    // อัตราส่วนต่อค่าฐาน — คูณกับตัวเลข hardcode เดิมทุกจุดข้างล่าง ที่เดสก์ท็อป (bodyPx===BODY_BASE)
    // อัตราส่วน = 1 พอดี ผลลัพธ์จึงเท่าค่าคงที่เดิมเป๊ะเสมอ (ข้อ 4 ของสเปก) ส่วนจอแคบกว่าค่อยย่อจริง
    const bodyScale = bodyPx / BODY_BASE;
    const microScale = microPx / MICRO_BASE;
    const fs = (n) => Math.round(n * 10) / 10;   // ปัดทศนิยม 1 ตำแหน่งกันเลข font-size ยาวไม่จำเป็น

    const FS_AXIS = fs(11 * microScale);      // ป้ายแกน X/Y + tooltip วันที่ (เดิม 11 คงที่ทุกจุด)
    const FS_TAIL = fs(12.5 * bodyScale);     // ป้ายค่าล่าสุดท้ายเส้น (เดิม 12.5)
    const FS_NAME = fs(12 * bodyScale);       // tooltip ชื่อ + ส่วนต่าง (เดิม 12 เท่ากันทั้งคู่ในดีไซน์เดิม)
    const FS_VAL = Math.round(bodyPx * 1.52); // tooltip ค่า — ตัวเด่นสุด (เดิม 19 = 12.5×1.52) ปัดเป็น
                                               // จำนวนเต็มเพราะเป็นตัวเลขที่ผู้ใช้อ่านเป็นหลัก ไม่ใช่ป้ายกำกับ
    const valScale = FS_VAL / 19;             // อัตราส่วนของ "แถวค่า" ในกล่อง tooltip ไว้ขยับระยะรอบมันด้วย

    const X0 = Math.round(44 * microScale);   // เว้นที่ป้ายแกน Y — กว้างตามฟอนต์ป้าย (เดิม 44 คงที่)
    // เว้นที่ป้ายค่าล่าสุดท้ายเส้น — ต้อง ≥ 7 (ระยะห่างจากเส้น) + กว้างกล่อง (สเกลตาม FS_TAIL) + ขอบเหลือ ๆ
    // เดิม 58 พอสำหรับข้อความลอย แต่กล่องตามดีไซน์ล้นขอบ viewBox ไป 3px แล้วโดน SVG ตัดขอบขวาหายไปทั้งเส้น
    // ต้องคำนวณ TAIL_W/TAIL_MARGIN (ขนาดกล่องป้ายท้ายเส้น) ไว้ก่อนตรงนี้ เพราะ X1 ใช้ต่อ —
    // ตัวกล่องจริง (rect/text) มาวาดทีหลังตอนถึงส่วนป้ายค่าล่าสุด ใช้ค่าเดียวกันนี้ซ้ำ
    const TAIL_W = Math.round(54 * bodyScale);   // กล่องป้ายค่าท้ายเส้น: กว้าง (เดิม 54)
    const TAIL_H = Math.round(22 * bodyScale);   // สูง (เดิม 22)
    const TAIL_HH = TAIL_H / 2;                  // ครึ่งสูง — แทนค่าคงที่ 11 เดิมที่ผูกกับ height/2
    const TAIL_RX = fs(6 * bodyScale);           // มุมโค้ง (เดิม 6)
    const TAIL_MARGIN = 5;                       // ขอบเหลือหลังกล่อง (66 เดิม = 7+54+5) ไม่ผูกฟอนต์ ไม่สเกล
    const X1 = W - (7 + TAIL_W + TAIL_MARGIN);   // (ดีไซน์เดสก์ท็อปเว้น mR=66 เท่ากันพอดี)
    const TOP = 18;           // เส้น grid บนสุด — ระยะคงที่ ไม่ผูกฟอนต์
    const BASE = H - Math.round(26 * microScale); // เส้นฐาน (ใต้ gridline ล่างสุดครึ่งช่อง) — ที่เหลือเป็นป้ายแกน X

    const lo = Math.min(...values), hi = Math.max(...values);
    // เลือกขั้นแกน Y แบบ "เลขสวย" ที่เล็กสุดซึ่งครอบข้อมูลได้ใน MAX_SPANS ช่อง
    // ยึด "ทั้งบนและล่าง" (ceil ของค่าสูงสุด กับ floor ของค่าต่ำสุด) — เดิมยึดแต่ด้านบนแล้วนับลงมา
    // เป็นจำนวนช่องตายตัว ทำให้กราฟที่ค่ากระจายกว้าง (เลือกหลายเส้นพร้อมกันแบบ 10b) ได้เส้น grid
    // ติดลบทั้งที่อัตราดอกเบี้ยไม่มีทางติดลบ และเสียพื้นที่กราฟไปครึ่งหนึ่งเปล่า ๆ
    const NICE = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5];
    const MAX_SPANS = 4;   // เส้น grid ไม่เกิน 5 เส้น
    // ปัดขึ้น/ลงแบบเผื่อ epsilon — 0.6/0.1 ในเลขทศนิยมลอยได้ 5.999999999999999 ถ้า floor ตรง ๆ
    // ขอบล่างจะหล่นไปอีกหนึ่งช่องเต็ม ๆ (เจอจริงกับช่วง 0.60–0.85)
    const upN = (v, s) => Math.ceil(v / s - 1e-9);
    const dnN = (v, s) => Math.floor(v / s + 1e-9);
    const step = NICE.find((s) => upN(hi, s) - dnN(lo, s) <= MAX_SPANS) || NICE[NICE.length - 1];
    const top = upN(hi, step) * step;
    // อย่างน้อยหนึ่งช่องเสมอ — ค่าคงที่ทั้งช่วง (hi === lo และหารลงตัว) จะได้ top === bottom
    const bottom = Math.min(dnN(lo, step) * step, top - step);
    const TICKS = Math.round((top - bottom) / step) + 1;
    const GAP = (BASE - TOP) / (TICKS - 1 + 0.5);
    const r2 = (n) => Math.round(n * 100) / 100;   // ตัดเศษทศนิยมลอย ๆ ออกจากพิกัด SVG
    const y = (v) => r2(TOP + (top - v) * (GAP / step));
    // แกน X เป็นสเกลเวลาจริง — ระยะห่างระหว่างจุดสะท้อนจำนวนวันที่ห่างกันจริง ไม่ใช่ลำดับของประกาศ
    // (ประกาศออกถี่/ห่างไม่เท่ากัน ถ้าวางเป็นช่องเท่า ๆ กันจะอ่านความชันของกราฟผิด)
    // ทุกจุดวันเดียวกัน (ต่างกัน 0 ms) ให้ตกกลางกราฟ กันหารด้วยศูนย์
    const times = dates.map((d) => Date.parse(d + 'T00:00:00Z'));
    const t0 = times[0], span = times[times.length - 1] - t0;
    const x = (i) => r2(span > 0 ? X0 + ((times[i] - t0) / span) * (X1 - X0) : (X0 + X1) / 2);

    // ── gridline + ป้ายแกน Y + เส้นฐาน ──
    const grid = add(svg, 'g', { stroke: '#EFECE7', 'stroke-width': '1' });
    const yLab = add(svg, 'g', { fill: '#8A8D93', 'font-size': FS_AXIS, 'text-anchor': 'end' });
    const AXIS_BASELINE = fs(4 * microScale);   // baseline offset ของตัวเลขแกน Y เทียบเส้น grid (เดิม 4)
    for (let i = 0; i < TICKS; i++) {
      const gy = r2(TOP + i * GAP);
      add(grid, 'line', { x1: X0, y1: gy, x2: X1, y2: gy });
      add(yLab, 'text', { x: X0 - 8, y: gy + AXIS_BASELINE }, (top - i * step).toFixed(2));
    }
    add(svg, 'line', { x1: X0, y1: BASE, x2: X1, y2: BASE, stroke: '#E0DDD6', 'stroke-width': '1' });
    // เส้นประแนวตั้งที่จุดล่าสุด — เน้นตำแหน่งประกาศปัจจุบัน
    add(svg, 'line', { x1: X1, y1: 6, x2: X1, y2: BASE, stroke: '#D6D2CA', 'stroke-width': '1', 'stroke-dasharray': '3,4' });

    // ── เส้นแต่ละผลิตภัณฑ์ (เฉพาะที่เลือก) ──
    // ค่าที่ขาดหาย (null) ข้ามไป แล้วลากเชื่อมจุดถัดไป — เหมือน spanGaps เดิม
    const points = (d) => d.data.map((v, i) => (v === null ? null : [x(i), y(v)])).filter(Boolean);

    shown.forEach((s) => {
      const pts = points(s);
      if (!pts.length) return;
      add(svg, 'polyline', {
        points: pts.map((p) => p.join(',')).join(' '),
        fill: 'none', stroke: colorOf(s.idx), 'stroke-width': '2',
        'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      });
      pts.forEach(([px, py]) => add(svg, 'circle', {
        cx: px, cy: py, r: '2.8', fill: '#fff', stroke: colorOf(s.idx), 'stroke-width': '2',
      }));
    });

    // จุดเน้นค่าล่าสุดของเส้นบนสุด — ให้เห็นชัดว่าเป็นอัตราปัจจุบัน (เดิมคำนวณ topIdx/topPts ไว้ข้างบน
    // ตอนยังมีพื้นสีทึบใต้เส้น ตอนนี้ดีไซน์ไม่มี area chart แล้ว เหลือใช้แค่จุดนี้จุดเดียวจึงย้ายมาคำนวณตรงนี้)
    // เลือกจาก "อัตราสุดท้ายสูงสุด" ไม่ใช่เส้นแรก เพราะลำดับเส้นมาจากลำดับ rate_targets ของแต่ละธนาคาร
    const topIdx = shown.reduce((best, s, i) => (lastOf(s.data) > lastOf(shown[best].data) ? i : best), 0);
    const topPts = points(shown[topIdx]);
    if (topPts.length) {
      const [lx, ly] = topPts[topPts.length - 1];
      add(svg, 'circle', { cx: lx, cy: ly, r: '4', fill: colorOf(shown[topIdx].idx), stroke: '#fff', 'stroke-width': '2' });
    }

    // ── ป้ายค่าล่าสุดท้ายเส้น — กล่องขาวกรอบสีเส้นตามดีไซน์ (เดิมเป็นข้อความลอยไม่มีกล่อง) ──
    // เลื่อนหนีกันเองไม่ให้ทับเหมือนเดิม แต่ MIN_GAP ต้องเผื่อความสูงกล่อง 22px (เดิมพอแค่ 14 เพราะเป็นบรรทัดข้อความเปล่า)
    const tails = shown
      .map((s) => {
        const last = lastOf(s.data);
        return last === null ? null : { v: last, y: y(last), color: colorOf(s.idx) };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);
    const MIN_GAP = TAIL_H + 2;   // เดิม 24 = 22 (สูงกล่อง) + 2 (ช่องว่าง) — ผูกสูตรกันหลุดจากกันเมื่อกล่องย่อ
    tails.forEach((t, i) => {
      // ty คือจุดกึ่งกลางกล่องแล้ว (เดิม t.y + 4 คือ baseline ของข้อความลอย) — ฐานจึงเปลี่ยนจาก t.y+4 เป็น t.y
      t.ty = i === 0 ? t.y : Math.max(t.y, tails[i - 1].ty + MIN_GAP);
    });
    // กันกล่องของเส้นบนสุด/ล่างสุดล้นขอบ SVG — ทำหลังจัดกันทับเสร็จเท่านั้น ไม่งั้นชนกับตัวจัดกันทับข้างบน
    // 11 เดิม = ครึ่งสูงกล่อง (22/2) — แทนด้วย TAIL_HH ให้ตามกล่องที่ย่อไปด้วย
    tails.forEach((t) => { t.ty = Math.min(Math.max(t.ty, TOP + TAIL_HH), BASE - TAIL_HH); });
    const tailG = add(svg, 'g');
    const TAIL_BASELINE = fs(4.5 * bodyScale);   // baseline offset ของตัวเลขในกล่อง เทียบกึ่งกลางกล่อง (เดิม 4.5)
    tails.forEach((t) => {
      add(tailG, 'rect', {
        x: X1 + 7, y: t.ty - TAIL_HH, width: TAIL_W, height: TAIL_H, rx: TAIL_RX,
        fill: '#fff', stroke: t.color, 'stroke-opacity': '0.35',
      });
      add(tailG, 'text', {
        x: X1 + 7 + TAIL_W / 2, y: t.ty + TAIL_BASELINE, 'text-anchor': 'middle',
        'font-size': FS_TAIL, 'font-weight': '700', fill: t.color,
      }, t.v.toFixed(2) + '%');
    });

    // ── ป้ายแกน X (วันที่ประกาศ) — บังคับให้มีจุดแรก+จุดสุดท้ายเสมอ ──
    // เลือกด้วย "ระยะห่างเป็นพิกเซล" ไม่ใช่ทุก ๆ n ลำดับ เพราะบนสเกลเวลาจริงประกาศที่ออกติด ๆ กัน
    // ไม่กี่วันจะอยู่เกือบทับกัน (การเว้นตามลำดับจึงยังเลือกป้ายที่ซ้อนกันมาได้)
    // ~ความกว้างป้าย "25 เม.ย. 69" ที่ 11px + ช่องว่าง — เดิม 86 คงที่ สเกลตาม FS_AXIS ให้ตรงป้ายจริง
    const MIN_LABEL_GAP = Math.round(86 * microScale);
    const picked = [];
    labels.forEach((lb, i) => {
      const px = x(i);
      if (i === 0 || i === labels.length - 1 || px - picked[picked.length - 1].px >= MIN_LABEL_GAP) {
        picked.push({ lb, px });
      }
    });
    // จุดสุดท้ายสำคัญกว่า (เป็นประกาศปัจจุบัน) — ถ้าเบียดป้ายก่อนหน้า ตัดป้ายก่อนหน้าทิ้งแทน
    while (picked.length > 2 && picked[picked.length - 1].px - picked[picked.length - 2].px < MIN_LABEL_GAP) {
      picked.splice(picked.length - 2, 1);
    }
    const xLab = add(svg, 'g', { fill: '#8A8D93', 'font-size': FS_AXIS, 'text-anchor': 'middle' });
    const XLAB_OFFSET = Math.round(17 * microScale);   // ระยะจากเส้นฐานถึง baseline ของป้าย (เดิม 17)
    picked.forEach((p) => add(xLab, 'text', { x: p.px, y: BASE + XLAB_OFFSET }, p.lb));

    // ── ป้ายสรุปการเปลี่ยนแปลงครั้งล่าสุด (มุมขวาบนของการ์ด) — เฉพาะเส้นที่กำลังโชว์ ──
    // ไล่จากประกาศล่าสุดย้อนกลับไป หาครั้งแรกที่มีอัตราขยับ แล้วบอกทิศทาง + เดือนของประกาศนั้น
    for (let i = labels.length - 1; i > 0 && badge; i--) {
      const deltas = shown
        .map((s) => (s.data[i] === null || s.data[i - 1] === null ? 0 : s.data[i] - s.data[i - 1]))
        .filter((d) => Math.abs(d) > 1e-9);
      if (!deltas.length) continue;
      const up = deltas.some((d) => d > 0), down = deltas.some((d) => d < 0);
      badge.textContent = (up && down ? 'ปรับอัตรา ' : up ? 'ปรับขึ้น ' : 'ปรับลด ')
        // ตัดวันที่ทิ้ง เหลือ "เม.ย. 69" — label มาจาก thai_date() รูปแบบ "25 เม.ย. 69"
        + labels[i].split(' ').slice(1).join(' ');
      badge.className = 'bd-trend-badge ' + (up && down ? 'mixed' : up ? 'up' : 'down');
      badge.hidden = false;
      break;
    }

    // ── tooltip ตอน hover — จับจุดที่ใกล้เคียงที่สุด (ทั้งแกน x และ y) ──
    // กลไกเดิมคงไว้ทั้งหมด (แผ่นรับเมาส์เต็มกราฟ + หาจุดใกล้สุดด้วยระยะถ่วงแกน y) เปลี่ยนแค่หน้าตา:
    // กล่องดำทึบไม่มีขอบ ตัวหนังสือขาวล้วน (ไม่มีสีเส้น/สีขึ้นลงคั่นกลางบรรทัดค่าเหมือนเดิมอีกต่อไป)
    const tip = add(svg, 'g', { style: 'pointer-events:none', visibility: 'hidden' });
    const tipDot = add(tip, 'circle', { r: '4' });   // ชี้จุดที่กำลังอ่านอยู่ — จำเป็นเพราะเมาส์ไม่ได้อยู่บนจุดจริงเสมอไป
    const tipBox = add(tip, 'rect', { rx: '9', fill: '#17181C' });
    const tipDate = add(tip, 'text', { 'font-size': FS_AXIS, 'font-weight': '600', fill: '#BFC3C9' });
    const tipSw = add(tip, 'rect', { width: '9', height: '9', rx: '2' });   // จุดสีในกล่อง (คนละตัวกับ tipDot ที่ชี้บนกราฟ)
    const tipName = add(tip, 'text', { 'font-size': FS_NAME, 'font-weight': '600', fill: '#fff' });
    const tipVal = add(tip, 'text', { 'font-size': FS_VAL, 'font-weight': '700', fill: '#fff' });
    const tipDelta = add(tip, 'text', { 'font-size': FS_NAME });

    // ── ระยะบรรทัดในกล่อง tooltip (เทียบมุมบนกล่อง by=0) — ผูกกับฟอนต์แต่ละบรรทัดตามบทบาท ──
    // ที่เดสก์ท็อป (bodyScale=microScale=valScale=1) ทุกค่าล่างนี้ลงตัวเท่าเลข hardcode เดิมเป๊ะ:
    // TT_DATE_OFF=19, TT_NAME_OFF=35, TT_SW_OFF=27, TT_VAL_OFF=56, TT_DELTA_OFF=76, bh=86/66
    const TT_DATE_OFF = Math.round(19 * microScale);              // บนกล่อง → บรรทัดวันที่
    const TT_NAME_OFF = TT_DATE_OFF + Math.round(16 * bodyScale); // วันที่ → บรรทัดชื่อ
    const TT_SW_OFF = TT_NAME_OFF - Math.round(8 * bodyScale);    // จุดสี (สูงกว่าบรรทัดชื่อเล็กน้อย)
    const TT_VAL_OFF = TT_NAME_OFF + Math.round(21 * valScale);   // ชื่อ → บรรทัดค่า (ฟอนต์ใหญ่สุด)
    const TT_DELTA_OFF = TT_VAL_OFF + Math.round(20 * valScale);  // ค่า → บรรทัดส่วนต่าง
    const TT_BOTTOM_PAD = Math.round(10 * bodyScale);             // แพดดิ้งใต้บรรทัดสุดท้าย

    const hit = add(svg, 'rect', {
      x: 0, y: 0, width: W, height: H, fill: '#000', 'fill-opacity': '0',
      style: 'cursor:crosshair;pointer-events:all',
    });

    const showTip = (ev) => {
      const box = svg.getBoundingClientRect();
      const mx = ((ev.clientX - box.left) / box.width) * W;
      const my = ((ev.clientY - box.top) / box.height) * H;

      let best = null;
      shown.forEach((s, si) => {
        s.data.forEach((v, i) => {
          if (v === null) return;
          const px = x(i), py = y(v);
          const dist = (px - mx) ** 2 + ((py - my) * 1.6) ** 2;   // ถ่วงแกน y ให้เลือกเส้นที่เมาส์อยู่ใกล้จริง
          if (!best || dist < best.dist) best = { dist, px, py, v, i, si };
        });
      });
      if (!best) return;

      const s = shown[best.si];
      const color = colorOf(s.idx);
      const { name } = splitLabel(s);
      const nameText = s.dep && s.dep.label ? `${name} · ${s.dep.label}` : name;

      // ค่าก่อนหน้า: ไล่ย้อนหาค่า non-null ตัวแรกก่อนจุดนี้ (ข้อมูลจริงมีช่องว่างได้ ต่างจากดีไซน์ที่ข้อมูลเต็มทุกช่อง)
      let prevV = null;
      for (let i = best.i - 1; i >= 0; i--) { if (s.data[i] !== null) { prevV = s.data[i]; break; } }
      const hasDelta = prevV !== null;
      const delta = hasDelta ? best.v - prevV : 0;
      // ไม่มีค่าก่อนหน้าให้เทียบ = ไม่มีบรรทัดส่วนต่าง กล่องเตี้ยลง (เดิม 86/66 คงที่ — ดูสูตร TT_* ด้านบน)
      const bh = (hasDelta ? TT_DELTA_OFF : TT_VAL_OFF) + TT_BOTTOM_PAD;

      tipName.textContent = nameText;
      // 178 คับสำหรับป้ายผู้ฝากยาว ๆ — วัดความยาวจริงหลังตั้งข้อความชื่อแล้วค่อยขยาย เฉพาะเมื่อจำเป็น
      const bw = Math.max(178, 28 + tipName.getComputedTextLength() + 13);

      const cx = best.px, cy = best.py;
      const bx = Math.min(Math.max(cx - bw / 2, 4), W - 4 - bw);
      const by = cy - bh - 14 < 4 ? cy + 14 : cy - bh - 14;

      tipDot.setAttribute('cx', cx); tipDot.setAttribute('cy', cy); tipDot.setAttribute('fill', color);
      tipBox.setAttribute('x', bx); tipBox.setAttribute('y', by);
      tipBox.setAttribute('width', bw); tipBox.setAttribute('height', bh);
      tipDate.setAttribute('x', bx + 13); tipDate.setAttribute('y', by + TT_DATE_OFF);
      tipDate.textContent = labels[best.i] || '';
      tipSw.setAttribute('x', bx + 13); tipSw.setAttribute('y', by + TT_SW_OFF); tipSw.setAttribute('fill', color);
      tipName.setAttribute('x', bx + 28); tipName.setAttribute('y', by + TT_NAME_OFF);
      tipVal.setAttribute('x', bx + 13); tipVal.setAttribute('y', by + TT_VAL_OFF);
      tipVal.textContent = best.v.toFixed(2) + '%';

      if (hasDelta) {
        tipDelta.setAttribute('x', bx + 13);
        tipDelta.setAttribute('y', by + TT_DELTA_OFF);
        if (Math.abs(delta) < 1e-9) {
          tipDelta.setAttribute('font-weight', '500'); tipDelta.setAttribute('fill', '#9B9EA4');
          tipDelta.textContent = 'ไม่เปลี่ยนจากครั้งก่อน';
        } else if (delta > 0) {
          tipDelta.setAttribute('font-weight', '600'); tipDelta.setAttribute('fill', '#3FB37F');
          tipDelta.textContent = `▲ +${delta.toFixed(2)}% จากครั้งก่อน`;
        } else {
          tipDelta.setAttribute('font-weight', '600'); tipDelta.setAttribute('fill', '#F0917C');
          tipDelta.textContent = `▼ ${delta.toFixed(2)}% จากครั้งก่อน`;
        }
      } else {
        tipDelta.textContent = '';
      }

      tip.setAttribute('visibility', 'visible');
    };

    hit.addEventListener('mousemove', showTip);
    hit.addEventListener('mouseleave', () => tip.setAttribute('visibility', 'hidden'));
  };

  const renderAll = (spec) => {
    currentView = computeView(spec);
    renderSide();
    renderChart();
  };

  // ── แผงขวา: ล้างการเลือก + เรียงลำดับ ──
  clearBtn.addEventListener('click', () => {
    visible.clear();
    renderSide();
    renderChart();
  });
  sortSel.addEventListener('change', () => { sortMode = sortSel.value; renderSide(); });

  // ── ชิปช่วงเวลาใต้กราฟ (3 เดือน / 6 เดือน / ปีปัจจุบัน / 1 ปี / ทั้งหมด) ──
  const specOf = (btn) => (btn.dataset.range === 'ytd' ? 'ytd'
    : Number(btn.dataset.months) === 0 ? 'all' : Number(btn.dataset.months));
  const rangeBtns = document.querySelectorAll('.bd-trend-range button');
  rangeBtns.forEach((btn) => {
    const spec = specOf(btn);
    if (spec !== 'all' && computeView(spec).labels.length < 2) btn.disabled = true;
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      rangeBtns.forEach((b) => b.classList.remove('on'));
      btn.classList.add('on');
      renderAll(spec);
    });
  });

  // เริ่มต้นที่ปุ่มซึ่งมีคลาส .on อยู่แล้วในเทมเพลต ("ปีปัจจุบัน" ตาม 10b)
  // ธนาคารที่มีประกาศในช่วงนั้นไม่ถึง 2 ครั้ง ปุ่มนั้นจะโดน disable ไปแล้วข้างบน — ถอยไปใช้ "ทั้งหมด"
  // ไม่งั้นกราฟจะเปิดมาว่างเปล่าโดยที่ปุ่มที่ค้าง .on อยู่ก็กดไม่ได้
  const allBtn = document.querySelector('.bd-trend-range button[data-months="0"]');
  let initialBtn = document.querySelector('.bd-trend-range button.on');
  if (!initialBtn || initialBtn.disabled) {
    if (initialBtn) initialBtn.classList.remove('on');
    initialBtn = allBtn;
    if (initialBtn) initialBtn.classList.add('on');
  }
  renderAll(initialBtn ? specOf(initialBtn) : 'all');

  // viewBox ผูกกับขนาดกล่องจริง — ย่อ/ขยายหน้าต่างแล้วต้องวาดใหม่ ไม่งั้นกราฟจะยืดผิดสัดส่วน
  if (window.ResizeObserver) {
    let pending = false, lastW = plotBox.clientWidth, lastH = plotBox.clientHeight;
    new ResizeObserver(() => {
      if (plotBox.clientWidth === lastW && plotBox.clientHeight === lastH) return;
      lastW = plotBox.clientWidth; lastH = plotBox.clientHeight;
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; renderChart(); });
    }).observe(plotBox);
  }

  // ── ดาวน์โหลด CSV ของเส้นที่เลือกไว้เท่านั้น (ตามดีไซน์ — เดิมส่งออกทุกอัตราไม่ว่าจะติ๊กไว้หรือไม่) ──
  // สองโหมด: "รายวัน" ไล่ทุกวันตามปฏิทิน (step function ของค่าล่าสุดที่ประกาศ) กับ "เฉพาะการเปลี่ยนแปลง"
  // มีเฉพาะแถววันที่ประกาศจริงที่ค่าขยับ — ปุ่มถูก disable ไปแล้วตอนไม่มีเส้นเลือกเลย (renderSide())
  // จึงไม่ต้องเช็คซ้ำในนี้ (ปุ่ม disabled ไม่ยิง click อยู่แล้ว)
  const dlModeSel = document.getElementById('trend-dl-mode');
  if (dlBtn) {
    const cell = (v) => {
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    const pad2 = (n) => String(n).padStart(2, '0');
    const isoOf = (dt) => `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`;
    const parseIso = (iso) => {
      const [y, m, d] = iso.split('-').map(Number);
      return new Date(Date.UTC(y, m - 1, d));
    };
    // จับคู่ series ข้ามอาร์เรย์ (currentView.series ↔ allSeries) ด้วย idx เท่านั้น ห้ามใช้ตำแหน่งในอาร์เรย์
    const allByIdx = new Map(allSeries.map((s) => [s.idx, s]));

    dlBtn.addEventListener('click', () => {
      const mode = dlModeSel ? dlModeSel.value : 'daily';
      const sel = currentView.series.filter((s) => visible.has(s.idx));
      const head = ['วันที่', ...sel.map((s) => s.label)];
      const startIso = currentView.dates[0];
      let rows, endIso;

      if (mode === 'change') {
        // มีเฉพาะแถวที่เส้นใดเส้นหนึ่งขยับ (เริ่มด้วย prev = null ทุกเส้น → แถวแรกของช่วงถูกเขียนเสมอ)
        rows = [];
        const prev = sel.map(() => null);
        currentView.dates.forEach((d, i) => {
          const vals = sel.map((s) => (s.data[i] === undefined ? null : s.data[i]));
          const changed = vals.some((v, k) => v !== null && (prev[k] === null || Math.abs(v - prev[k]) > 1e-9));
          if (changed) rows.push([d, ...vals.map((v) => (v === null ? '' : v.toFixed(2)))]);
          vals.forEach((v, k) => { if (v !== null) prev[k] = v; });
        });
        endIso = rows.length ? rows[rows.length - 1][0] : startIso;
      } else {
        // รายวัน: อัตราที่ประกาศครั้งล่าสุดยังมีผลใช้อยู่จนถึงวันนี้ — ไล่ทุกวันตามปฏิทินจากวันเริ่มช่วงที่เลือก
        // ถึง max(วันนี้, วันประกาศล่าสุด) กันตารางขาดแถวถ้าประกาศล่าสุดลงวันที่ล่วงหน้า (effective date อนาคตมีจริงได้)
        const todayIso = isoOf(new Date());
        const lastIso = allDates[allDates.length - 1];
        const endDate = todayIso > lastIso ? todayIso : lastIso;

        // carry-forward ต่อเส้นครั้งเดียวก่อนวนวัน (ไม่สแกนย้อนหลังซ้ำทุกวัน) — หาจาก allSeries/allDates
        // ไม่ใช่ currentView เพื่อให้อัตราที่ประกาศก่อนวันเริ่มช่วงไหลเข้ามาเป็นค่าตั้งต้นได้
        const carried = sel.map((s) => {
          const full = allByIdx.get(s.idx).data;
          const out = new Array(full.length);
          let cur = null;
          full.forEach((v, i) => { if (v !== null) cur = v; out[i] = cur; });
          return out;
        });
        const ptr = sel.map(() => 0);   // เดินตัวชี้ไปข้างหน้าเรื่อย ๆ พอ (allDates กับวันปฏิทินไล่จากอดีตไปอนาคตทั้งคู่)
        rows = [];
        const endD = parseIso(endDate);
        for (let d = parseIso(startIso); d <= endD; d.setUTCDate(d.getUTCDate() + 1)) {
          const iso = isoOf(d);
          const vals = carried.map((out, k) => {
            while (ptr[k] + 1 < allDates.length && allDates[ptr[k] + 1] <= iso) ptr[k] += 1;
            return allDates[ptr[k]] <= iso ? out[ptr[k]] : null;
          });
          rows.push([iso, ...vals.map((v) => (v === null ? '' : v.toFixed(2)))]);
        }
        endIso = endDate;
      }

      // ﻿ (BOM) — ไม่งั้น Excel บน Windows อ่านภาษาไทยใน CSV เป็นตัวขยะ
      const csv = '﻿' + [head, ...rows].map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${dlBtn.dataset.code}_rates_${startIso}_${endIso}_${mode}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
})();

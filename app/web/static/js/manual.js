(() => {
  const saveBtn = document.getElementById('save-manual');
  if (!saveBtn) return;
  const code = saveBtn.dataset.code;
  const msgEl = document.getElementById('msg');
  const monthSelect = document.getElementById('manual-month-select');

  function setMsg(cls, text) {
    if (msgEl) msgEl.innerHTML = `<div class="notice ${cls}">${text}</div>`;
  }

  // เก็บเฉพาะช่องที่ค่าเปลี่ยนจริง (value !== data-orig) — ใช้ทั้งตอนบันทึกและตอนเช็คว่ามี edit ค้างไหม
  function collectChanges() {
    const inputs = document.querySelectorAll('#manual-table input[data-date]');
    const payload = {};
    let changedCount = 0;
    inputs.forEach((inp) => {
      const orig = inp.dataset.orig || '';
      const cur = inp.value.trim();
      if (cur === orig) return;
      const date = inp.dataset.date;
      const key = inp.dataset.key;
      payload[date] = payload[date] || {};
      payload[date][key] = cur === '' ? null : cur;   // ว่าง = ลบ override
      changedCount++;
    });
    return { payload, changedCount };
  }

  let dirty = false;
  document.querySelectorAll('#manual-table input[data-date]').forEach((inp) => {
    inp.addEventListener('input', () => { dirty = collectChanges().changedCount > 0; });
  });

  window.addEventListener('beforeunload', (e) => {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = '';
  });

  if (monthSelect) {
    const initialMonth = monthSelect.value;
    monthSelect.addEventListener('change', () => {
      if (dirty && !confirm('มีช่องที่แก้ไขแล้วยังไม่ได้บันทึก — เปลี่ยนเดือนตอนนี้จะทำให้ค่าที่แก้หายไป ต้องการเปลี่ยนต่อหรือไม่?')) {
        monthSelect.value = initialMonth;
        return;
      }
      dirty = false;
      location.href = `/bank/${code}/manual?month=${encodeURIComponent(monthSelect.value)}`;
    });
  }

  // รอ backfill ที่ server สั่งให้ตอนบันทึกจบก่อนค่อยรีโหลด — เดิมรีโหลดหลัง 1.5 วิ แบบตายตัว
  // ซึ่งมักเร็วกว่างานจริง (subprocess เพิ่งสตาร์ท) หน้าจึงถูกวาดใหม่จาก CSV ก้อนเดิม = เห็นค่าเก่า
  // (ยอมแพ้หลัง MAX_WAIT แล้วรีโหลดอยู่ดี — ค่าที่กรอกเองแสดงได้จาก manual.json ตั้งแต่ยังไม่ rebuild)
  const POLL_MS = 1500;
  const MAX_WAIT_MS = 120000;

  async function jobStatus() {
    try {
      return await (await fetch('/api/run/status')).json();
    } catch (e) {
      return null;
    }
  }

  // prevStarted = เวลาเริ่มงานล่าสุด "ก่อน" กดบันทึก — ใช้แยกว่างานที่เห็นเป็นงานของเราหรืองานเก่า
  // (จำเป็นเพราะ backfill ที่ cache hit ทุกไฟล์อาจจบก่อน poll รอบแรกด้วยซ้ำ)
  async function reloadWhenJobDone(prevStarted) {
    const deadline = Date.now() + MAX_WAIT_MS;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      const job = await jobStatus();
      if (!job) break;                                   // เช็คสถานะไม่ได้ → รีโหลดไปเลย
      if (job.running) continue;
      if (job.started !== prevStarted) break;            // งานของเราจบแล้ว → CSV ใหม่พร้อม
    }
    location.reload();
  }

  saveBtn.addEventListener('click', async () => {
    const { payload, changedCount } = collectChanges();
    if (!changedCount) {
      setMsg('err', 'ไม่มีช่องที่แก้ไข');
      return;
    }

    saveBtn.disabled = true;
    setMsg('ok', '⏳ กำลังบันทึก...');
    const before = await jobStatus();
    const prevStarted = before ? before.started : null;
    try {
      const res = await fetch(`/api/manual/${code}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg('err', body.detail || 'บันทึกไม่สำเร็จ');
        saveBtn.disabled = false;
        return;
      }
      dirty = false;
      if (body.backfill_started === false) {
        // สล็อตงานเดียว: มีงานอื่นค้างอยู่ → CSV ยังไม่อัปเดตจนกว่าจะ backfill รอบถัดไป
        // (ค่าที่กรอกเองบันทึกลง manual.json แล้ว และหน้านี้แสดงให้เห็นตั้งแต่ยังไม่ rebuild)
        setMsg('ok', `บันทึกแล้ว ${body.changed} ช่อง — แต่มีงานอื่นกำลังรันอยู่ ` +
                     'ระบบยังไม่ได้สร้าง CSV ใหม่ ให้กด "เติมข้อมูลย้อนหลัง" ในหน้าธนาคารอีกครั้งเมื่องานนั้นเสร็จ');
        setTimeout(() => location.reload(), 2500);
        return;
      }
      setMsg('ok', `บันทึกแล้ว ${body.changed} ช่อง — กำลัง rebuild ข้อมูล (ใช้ cache จึงเร็วมาก)...`);
      reloadWhenJobDone(prevStarted);
    } catch (e) {
      setMsg('err', 'เชื่อมต่อไม่ได้');
      saveBtn.disabled = false;
    }
  });
})();

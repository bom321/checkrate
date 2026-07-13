// overview.js — ตัวกรองเดือน (สรุปผลการรัน + reload หลังรันเสร็จ ย้ายไปอยู่ใน run.js
// เพราะหน้า bank detail ใช้ร่วมกัน — ทั้งสองหน้าโชว์แค่สรุป ไม่โชว์ log ดิบ ให้ไปดูที่หน้า Log แทน)
(function () {
  const monthSel = document.getElementById('month-select');
  if (monthSel) {
    monthSel.addEventListener('change', () => {
      if (monthSel.value) location.href = '/?month=' + monthSel.value;
    });
  }
})();

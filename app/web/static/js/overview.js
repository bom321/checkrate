// overview.js — รีโหลดหน้าหลังรันเสร็จเพื่อดึงข้อมูลล่าสุด
(function () {
  window.addEventListener('checkrate:run-finished', () => {
    setTimeout(() => location.reload(), 800);
  });
})();

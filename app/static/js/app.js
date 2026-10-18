// Minimal interactivity: no-op beyond placeholder; kept for future enhancements.
document.addEventListener('DOMContentLoaded', function () {
  // auto-dismiss alerts after 5s
  document.querySelectorAll('.alert').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 5000);
  });
});

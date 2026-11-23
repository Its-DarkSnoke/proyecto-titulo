(() => {
  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-app-back]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const previousPage = document.referrer;
    if (!previousPage || window.history.length < 2) return;

    try {
      const previous = new URL(previousPage);
      if (previous.origin === window.location.origin && previous.href !== window.location.href) {
        event.preventDefault();
        window.history.back();
      }
    } catch (_) {
      // Si no se puede validar el historial, se usa el destino local del enlace.
    }
  });
})();
